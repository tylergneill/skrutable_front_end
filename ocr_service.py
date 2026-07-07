from natsort import natsorted
from pathlib import Path
import uuid, json, os, zipfile, tempfile
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

    operation = client_vis.async_batch_annotate_files(requests=[request])
    operation.result(timeout=420)

    # Avoid e.g. 1, 10, 11, sorting problem
    blobs = natsorted(bucket.list_blobs(prefix=f"{job_id}/ocr/"), key=lambda b: b.name)

    texts = []
    for i, blob in enumerate(blobs, start=1):
        data = json.loads(blob.download_as_text())["responses"][0]
        page_text = data.get("fullTextAnnotation", {}).get("text", "")

        if include_page_numbers:
            page_text = f"\n=== {i} ===\n{page_text}"

        texts.append(page_text)

    final_output = "\n".join(texts)
    page_count = len(texts)

    bucket.delete_blobs(list(bucket.list_blobs(prefix=job_id)))

    return final_output, page_count

SARVAM_PAGE_LIMIT = 10

def _run_sarvam_ocr_chunk(client, chunk_path: Path, page_offset: int, include_page_numbers: bool, filter_headers_footers: bool) -> list:
    """Run Sarvam OCR on a single chunk PDF, return list of page text strings."""
    try:
        job = client.document_intelligence.create_job(language="sa-IN", output_format="md")
    except TooManyRequestsError as e:
        body = getattr(e, "body", {}) or {}
        err = (body.get("error") or {}) if isinstance(body, dict) else {}
        code = err.get("code", "")
        if code == "insufficient_quota_error" or "credits" in err.get("message", "").lower():
            raise RuntimeError("QUOTA_EXHAUSTED") from None
        raise RuntimeError(f"Sarvam API rate limit: {err.get('message') or str(e)}") from None
    job.upload_file(str(chunk_path))
    job.start()
    job.wait_until_complete()

    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "output.zip"
        job.download_output(str(zip_path))
        with zipfile.ZipFile(zip_path) as zf:
            json_names = natsorted([n for n in zf.namelist() if n.endswith(".json")])
            texts = []
            for i, name in enumerate(json_names, start=1):
                data = json.loads(zf.read(name))
                blocks = sorted(data.get("blocks", []), key=lambda b: b.get("reading_order", 0))
                excluded = {"header", "footnote"} if filter_headers_footers else set()
                page_text = "\n".join(
                    b["text"] for b in blocks
                    if b.get("layout_tag") not in excluded
                )
                if include_page_numbers:
                    page_text = f"\n=== {page_offset + i} ===\n{page_text}"
                texts.append(page_text)
    return texts

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
            chunk_texts = _run_sarvam_ocr_chunk(client, chunk_path, chunk_start, include_page_numbers, filter_headers_footers)
            yield i, total_chunks, chunk_texts
