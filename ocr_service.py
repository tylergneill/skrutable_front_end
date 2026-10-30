from natsort import natsorted
from pathlib import Path
import uuid, json, os, tempfile, time
from html.parser import HTMLParser
import requests
from google.cloud import storage, vision
from sarvamai import SarvamAI
from sarvamai.errors import TooManyRequestsError
from pypdf import PdfReader, PdfWriter

BUCKET = os.getenv("GCS_BUCKET", "vision_multilang_ocr")   # set via env
PROJECT = os.getenv("GCP_PROJECT", "sanskrit-ocr-219110") # set via env

def run_google_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True) -> tuple:
    """Upload PDF, run async Vision OCR, return (text, page_count).

    Note: Google Vision's block_type enum has no HEADER/FOOTER values (only TEXT, TABLE,
    PICTURE, RULER, BARCODE), so header/footer filtering is not possible here.
    """
    client_vis   = vision.ImageAnnotatorClient(client_options={"api_key": api_key})
    client_store = storage.Client(project=PROJECT)

    bucket  = client_store.bucket(BUCKET)
    job_id  = uuid.uuid4().hex
    blob_in = bucket.blob(f"{job_id}/{pdf_path.name}")
    blob_in.upload_from_filename(pdf_path)
    blob_in.make_public()

    gcs_src  = f"gs://{BUCKET}/{job_id}/{pdf_path.name}"
    gcs_dest = f"gs://{BUCKET}/{job_id}/ocr/"

    request = vision.AsyncAnnotateFileRequest(
        input_config = vision.InputConfig(
            gcs_source = vision.GcsSource(uri=gcs_src),
            mime_type  = "application/pdf",
        ),
        features      = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)],
        output_config = vision.OutputConfig(
            gcs_destination = vision.GcsDestination(uri=gcs_dest),
            batch_size      = 1,
        ),
    )

    try:
        operation = client_vis.async_batch_annotate_files(requests=[request])
        # Must stay under gunicorn's 1200s request timeout (see Dockerfile)
        operation.result(timeout=1100)

        # Avoid e.g. 1, 10, 11, sorting problem
        blobs = natsorted(bucket.list_blobs(prefix=f"{job_id}/ocr/"), key=lambda b: b.name)

        texts = []
        for i, blob in enumerate(blobs, start=1):
            data = json.loads(blob.download_as_text())["responses"][0]
            page_text = data.get("fullTextAnnotation", {}).get("text", "")

            if include_page_numbers:
                page_text = f"\n=== {i} ===\n{page_text}"

            texts.append(page_text)
    finally:
        # On timeout, Vision keeps writing output after we give up; the nightly
        # bucket-cleaning workflow catches anything written after this point.
        bucket.delete_blobs(list(bucket.list_blobs(prefix=job_id)))

    final_output = "\n".join(texts)
    page_count = len(texts)

    return final_output, page_count

SARVAM_PAGE_LIMIT = 10

SARVAM_RESULTS_URL = "https://api.sarvam.ai/doc-ai/v1/job/{job_id}/results"
SARVAM_TERMINAL_STATUSES = {"completed", "partially_completed", "failed", "rejected"}
SARVAM_POLL_INTERVAL = 2     # seconds
SARVAM_POLL_TIMEOUT = 1200   # seconds, matches gunicorn timeout

class _TableFlattener(HTMLParser):
    """Turn an HTML <table> into plain lines: cells joined by ' | ', one line per row."""
    def __init__(self):
        super().__init__()
        self.rows, self._cells, self._buf = [], None, []
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._cells = []
        elif tag in ("td", "th"):
            self._buf = []
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cells is not None:
            self._cells.append(" ".join("".join(self._buf).split()))
        elif tag == "tr" and self._cells is not None:
            if any(self._cells):
                self.rows.append(" | ".join(self._cells))
            self._cells = None
    def handle_data(self, data):
        self._buf.append(data)

def _block_text(block: dict) -> str:
    """Block text; Document AI returns HTML <table> markup for table blocks, so flatten it."""
    text = block.get("text", "")
    if block.get("layout_tag") == "table" and "<t" in text:
        flat = _TableFlattener()
        flat.feed(text)
        return "\n".join(flat.rows) or text
    return text

def _sarvam_pages_to_texts(results: dict, page_offset: int, include_page_numbers: bool, filter_headers_footers: bool) -> list:
    """Convert a Document AI results JSON into a list of page text strings."""
    excluded = {"header", "footnote", "footer"} if filter_headers_footers else set()
    texts = []
    pages = sorted(results["documents"][0]["pages"], key=lambda pg: pg.get("page_number", 0))
    for i, page in enumerate(pages, start=1):
        blocks = sorted(page.get("blocks", []), key=lambda b: b.get("reading_order", 0))
        page_text = "\n".join(
            _block_text(b) for b in blocks
            if b.get("layout_tag") not in excluded
        )
        if include_page_numbers:
            page_text = f"\n=== {page_offset + i} ===\n{page_text}"
        texts.append(page_text)
    return texts

def _run_sarvam_ocr_chunk(client, api_key: str, chunk_path: Path, page_offset: int, include_page_numbers: bool, filter_headers_footers: bool) -> list:
    """Run Sarvam OCR (Document AI API) on a single chunk PDF, return list of page text strings."""
    try:
        with open(chunk_path, "rb") as f:
            job = client.doc_ai.parse(file=[(chunk_path.name, f, "application/pdf")], language="sa-IN")
    except TooManyRequestsError as e:
        body = getattr(e, "body", {}) or {}
        err = (body.get("error") or {}) if isinstance(body, dict) else {}
        code = err.get("code", "")
        if code == "insufficient_quota_error" or "credits" in err.get("message", "").lower():
            raise RuntimeError("QUOTA_EXHAUSTED") from None
        raise RuntimeError(f"Sarvam API rate limit: {err.get('message') or str(e)}") from None

    deadline = time.monotonic() + SARVAM_POLL_TIMEOUT
    while True:
        status = client.doc_ai.get_status(job.job_id).status
        if status in SARVAM_TERMINAL_STATUSES:
            break
        if time.monotonic() > deadline:
            raise RuntimeError(f"Sarvam OCR job {job.job_id} timed out")
        time.sleep(SARVAM_POLL_INTERVAL)
    if status in ("failed", "rejected"):
        raise RuntimeError(f"Sarvam OCR job {status}")

    # Raw HTTP: client.doc_ai.get_results() raises a pydantic ValidationError in sarvamai 0.1.40
    # because the response has type "digitise", which the SDK's tagged union does not know.
    resp = requests.get(
        SARVAM_RESULTS_URL.format(job_id=job.job_id),
        params={"format": "json"},
        headers={"api-subscription-key": api_key},
        timeout=120,
    )
    resp.raise_for_status()
    return _sarvam_pages_to_texts(resp.json(), page_offset, include_page_numbers, filter_headers_footers)

def run_sarvam_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True, filter_headers_footers: bool = True) -> tuple:
    """Submit PDF to Sarvam Vision, return (text, page_count). Splits into chunks if > 10 pages."""
    all_texts = []
    for _, _, chunk_texts in stream_sarvam_ocr(pdf_path, api_key, include_page_numbers, filter_headers_footers):
        all_texts.extend(chunk_texts)
    return "\n".join(all_texts), len(all_texts)

def stream_sarvam_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True, filter_headers_footers: bool = True):
    """Generator: yields (chunk_index, total_chunks, chunk_texts) as each chunk completes."""
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    total_chunks = (total_pages + SARVAM_PAGE_LIMIT - 1) // SARVAM_PAGE_LIMIT
    client = SarvamAI(api_subscription_key=api_key)

    with tempfile.TemporaryDirectory() as chunk_dir:
        for i, chunk_start in enumerate(range(0, total_pages, SARVAM_PAGE_LIMIT), start=1):
            chunk_end = min(chunk_start + SARVAM_PAGE_LIMIT, total_pages)
            writer = PdfWriter()
            for p in range(chunk_start, chunk_end):
                writer.add_page(reader.pages[p])
            chunk_path = Path(chunk_dir) / f"chunk_{chunk_start}.pdf"
            with open(chunk_path, "wb") as f:
                writer.write(f)
            chunk_texts = _run_sarvam_ocr_chunk(client, api_key, chunk_path, chunk_start, include_page_numbers, filter_headers_footers)
            yield i, total_chunks, chunk_texts
