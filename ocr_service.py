from natsort import natsorted
from pathlib import Path
import uuid, json, os, tempfile, time
import base64, io, logging, math, re, unicodedata
from html.parser import HTMLParser
import requests
from google.cloud import storage, vision
from sarvamai import SarvamAI
from sarvamai.errors import TooManyRequestsError
from pypdf import PdfReader, PdfWriter

BUCKET = os.getenv("GCS_BUCKET", "vision_multilang_ocr")   # set via env
PROJECT = os.getenv("GCP_PROJECT", "sanskrit-ocr-219110") # set via env

logger = logging.getLogger(__name__)

def page_label(n: int, page_number_start: int = 1, page_number_step: int = 1) -> int:
    """Printed page number for the n-th page (1-based) of the PDF."""
    return page_number_start + (n - 1) * page_number_step

def run_google_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True, page_number_start: int = 1, page_number_step: int = 1) -> tuple:
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
                page_text = f"\n=== {page_label(i, page_number_start, page_number_step)} ===\n{page_text}"

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

def _sarvam_pages_to_texts(results: dict, page_offset: int, include_page_numbers: bool, filter_headers_footers: bool, page_number_start: int = 1, page_number_step: int = 1) -> list:
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
            page_text = f"\n=== {page_label(page_offset + i, page_number_start, page_number_step)} ===\n{page_text}"
        texts.append(page_text)
    return texts

def _run_sarvam_ocr_chunk(client, api_key: str, chunk_path: Path, page_offset: int, include_page_numbers: bool, filter_headers_footers: bool, page_number_start: int = 1, page_number_step: int = 1) -> list:
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
    return _sarvam_pages_to_texts(resp.json(), page_offset, include_page_numbers, filter_headers_footers, page_number_start, page_number_step)

def run_sarvam_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True, filter_headers_footers: bool = True, page_number_start: int = 1, page_number_step: int = 1) -> tuple:
    """Submit PDF to Sarvam Vision, return (text, page_count). Splits into chunks if > 10 pages."""
    all_texts = []
    for _, _, chunk_texts in stream_sarvam_ocr(pdf_path, api_key, include_page_numbers, filter_headers_footers,
                                               page_number_start=page_number_start, page_number_step=page_number_step):
        all_texts.extend(chunk_texts)
    return "\n".join(all_texts), len(all_texts)

def stream_sarvam_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True, filter_headers_footers: bool = True, start_page: int = 1, page_number_start: int = 1, page_number_step: int = 1):
    """Generator: yields (chunk_index, total_chunks, chunk_texts) as each chunk completes.

    start_page (1-based) skips earlier pages, so a client whose connection dropped can
    resume. chunk_index and total_chunks always count from page 1 of the whole PDF.
    page_number_start/page_number_step only change the printed "=== N ===" labels.
    """
    client = SarvamAI(api_subscription_key=api_key)
    for i, total_chunks, chunk_start, chunk_path in _pdf_chunks(pdf_path, SARVAM_PAGE_LIMIT, start_page):
        chunk_texts = _run_sarvam_ocr_chunk(client, api_key, chunk_path, chunk_start, include_page_numbers, filter_headers_footers,
                                            page_number_start, page_number_step)
        yield i, total_chunks, chunk_texts


def _pdf_chunks(pdf_path: Path, chunk_size: int, start_page: int = 1):
    """Generator: split a PDF into temporary chunk PDFs of at most chunk_size pages.

    Yields (chunk_index, total_chunks, chunk_start, chunk_path), where chunk_start is the
    0-based index of the chunk's first page in the whole PDF. As in the Sarvam stream,
    chunk_index and total_chunks always count from page 1, even when start_page (1-based)
    skips earlier pages to resume a dropped stream. Each chunk file is deleted once the
    caller moves on to the next one (the temp dir goes when the generator finishes).
    """
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    total_chunks = (total_pages + chunk_size - 1) // chunk_size
    first = max(start_page, 1) - 1

    with tempfile.TemporaryDirectory() as chunk_dir:
        for chunk_start in range(first, total_pages, chunk_size):
            i = chunk_start // chunk_size + 1
            chunk_end = min(chunk_start + chunk_size, total_pages)
            writer = PdfWriter()
            for p in range(chunk_start, chunk_end):
                writer.add_page(reader.pages[p])
            chunk_path = Path(chunk_dir) / f"chunk_{chunk_start}.pdf"
            with open(chunk_path, "wb") as f:
                writer.write(f)
            yield i, total_chunks, chunk_start, chunk_path


# =====================================================================================
# Surya, via Datalab's hosted API
# =====================================================================================
#
# Datalab (the company behind Surya and Marker) sells hosted conversion at
# POST https://www.datalab.to/api/v1/convert. It is asynchronous: the POST returns a
# request_check_url, which we poll until status == "complete". There is no model selector;
# `mode` (lite / fast / balanced / accurate) trades cost for accuracy, and Datalab decides
# which of its models (Surya OCR, Chandra, ...) run underneath. So "Surya" here means
# "Datalab's Surya-based pipeline", not a guaranteed specific checkpoint.
#
# We ask for JSON output rather than markdown, because the JSON keeps one block per page
# (block_type "Page") with typed children (Text, SectionHeader, PageHeader, PageFooter,
# Footnote, Table, ...). That gives us page boundaries for the "=== N ===" labels and lets
# the existing "filter headers and footers" option work the same way it does for Sarvam.
#
# Like Sarvam, the user brings their own API key in the form; nothing is stored.

DATALAB_CONVERT_URL = "https://www.datalab.to/api/v1/convert"
DATALAB_MODES = ("lite", "fast", "balanced", "accurate")
DATALAB_DEFAULT_MODE = "balanced"  # Datalab's own REST default and recommendation
# Pages sent per convert request. Datalab accepts up to 7,000, but small chunks let the
# browser show progress and resume a dropped stream, exactly as with Sarvam's 10-page limit.
DATALAB_PAGE_LIMIT = int(os.getenv("DATALAB_PAGES_PER_REQUEST", "10"))
DATALAB_POLL_TIMEOUT = 1100   # seconds per chunk; stays under gunicorn's 1200 s
DATALAB_RATE_LIMIT_WAIT = 60  # seconds to back off on HTTP 429 (Datalab's own sample code)
DATALAB_MAX_429_RETRIES = 5
# Block types dropped when "filter headers and footers" is on (mirrors Sarvam's
# header / footer / footnote layout tags).
DATALAB_EXCLUDED_BLOCKS = {"PageHeader", "PageFooter", "Footnote"}


class _HtmlToText(HTMLParser):
    """Collect the visible text of a small HTML fragment, one line per block-level element.

    Datalab's JSON gives each leaf block as HTML (e.g. "<p>...</p>", "<h2>...</h2>").
    <math> content (KaTeX source) is kept as plain text; images are ignored.
    """
    _BREAK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"}

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).split("\n"))
        return "\n".join(line for line in lines if line)


def _html_to_text(html: str) -> str:
    parser = _HtmlToText()
    parser.feed(html or "")
    parser.close()
    return parser.text()


def _datalab_block_texts(block: dict, excluded: set) -> list:
    """Plain-text lines for one Datalab JSON block, recursing into child blocks.

    Container blocks (Page, ListGroup, ...) carry <content-ref> placeholders in their own
    html, so their text comes from their children. Tables are flattened with the same
    ' | ' row format used for Sarvam tables.
    """
    block_type = block.get("block_type", "")
    if block_type in excluded:
        return []
    html = block.get("html") or ""
    if block_type == "Table" and "<t" in html:
        flat = _TableFlattener()
        flat.feed(html)
        if flat.rows:
            return flat.rows
    children = block.get("children") or []
    if children:
        return [t for child in children for t in _datalab_block_texts(child, excluded)]
    text = _html_to_text(html)
    return [text] if text else []


def _datalab_pages_to_texts(doc, page_offset: int, include_page_numbers: bool, filter_headers_footers: bool,
                            page_number_start: int = 1, page_number_step: int = 1) -> list:
    """Convert Datalab's JSON output (one chunk) into a list of page text strings."""
    if isinstance(doc, str):
        doc = json.loads(doc)
    pages = [b for b in (doc or {}).get("children") or [] if b.get("block_type") == "Page"]
    if not pages:
        # Fail loudly rather than return one unlabeled blob: the page labels would be wrong.
        raise RuntimeError("Datalab returned no Page blocks; its JSON layout differs from what this adapter expects")
    excluded = DATALAB_EXCLUDED_BLOCKS if filter_headers_footers else set()
    texts = []
    for i, page in enumerate(pages, start=1):
        page_text = unicodedata.normalize("NFC", "\n".join(_datalab_block_texts(page, excluded)))
        if include_page_numbers:
            page_text = f"\n=== {page_label(page_offset + i, page_number_start, page_number_step)} ===\n{page_text}"
        texts.append(page_text)
    return texts


def _datalab_request(method: str, url: str, **kwargs) -> requests.Response:
    """requests.request with Datalab's error cases mapped to the messages Flask shows.

    HTTP 429 (free tier: 10 requests/minute) is retried after a pause. A 402 (no credit)
    becomes "QUOTA_EXHAUSTED", the same marker Sarvam uses, so the route can say so plainly.
    """
    for _ in range(DATALAB_MAX_429_RETRIES + 1):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code != 429:
            break
        logger.warning("Datalab rate limit hit; waiting %d s", DATALAB_RATE_LIMIT_WAIT)
        time.sleep(DATALAB_RATE_LIMIT_WAIT)
    if resp.status_code == 402:
        raise RuntimeError("QUOTA_EXHAUSTED")
    if resp.status_code in (401, 403):
        raise RuntimeError("Datalab rejected the API key")
    if not resp.ok:
        raise RuntimeError(f"Datalab HTTP {resp.status_code}: {resp.text[:300]}")
    return resp


def _run_surya_ocr_chunk(api_key: str, chunk_path: Path, mode: str, page_offset: int, include_page_numbers: bool,
                         filter_headers_footers: bool, page_number_start: int = 1, page_number_step: int = 1) -> list:
    """Run one chunk PDF through Datalab's convert API, return list of page text strings."""
    headers = {"X-API-Key": api_key}
    with open(chunk_path, "rb") as f:
        submit = _datalab_request(
            "POST", DATALAB_CONVERT_URL, headers=headers, timeout=120,
            files={"file": (chunk_path.name, f, "application/pdf")},
            data={
                "mode": mode,
                "output_format": "json",
                # We only want text: no extracted figures, and no model-written captions
                # for figures, which would otherwise show up as if they were printed text.
                "disable_image_extraction": "true",
                "disable_image_captions": "true",
            },
        ).json()
    if submit.get("success") is False:
        raise RuntimeError(f"Datalab refused the request: {submit.get('error')}")
    check_url = submit["request_check_url"]

    deadline = time.monotonic() + DATALAB_POLL_TIMEOUT
    delay = 1.0
    while True:
        result = _datalab_request("GET", check_url, headers=headers, timeout=120).json()
        if result.get("status") == "complete":
            break
        if result.get("success") is False or result.get("status") == "failed":
            raise RuntimeError(f"Datalab conversion failed: {result.get('error')}")
        if time.monotonic() > deadline:
            raise RuntimeError(f"Datalab request {submit.get('request_id')} timed out")
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)  # most chunks finish within seconds; back off gently
    # A finished job can still be a failure: status "complete" with success false.
    if result.get("success") is False:
        raise RuntimeError(f"Datalab conversion failed: {result.get('error')}")

    doc = result.get("json")
    if doc is None and result.get("result_url"):
        # Large results come back as a signed download link instead of inline.
        # The link authorizes itself, so it is fetched without the API key.
        r = requests.get(result["result_url"], timeout=120)
        r.raise_for_status()
        doc = r.json().get("json")
    texts = _datalab_pages_to_texts(doc, page_offset, include_page_numbers, filter_headers_footers,
                                    page_number_start, page_number_step)
    if result.get("page_count") and result["page_count"] != len(texts):
        logger.warning("Datalab page_count %s but %d Page blocks in JSON", result["page_count"], len(texts))
    return texts


def stream_surya_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True, filter_headers_footers: bool = True,
                     start_page: int = 1, page_number_start: int = 1, page_number_step: int = 1,
                     mode: str = DATALAB_DEFAULT_MODE):
    """Generator: yields (chunk_index, total_chunks, chunk_texts), same contract as stream_sarvam_ocr."""
    if mode not in DATALAB_MODES:
        raise ValueError(f"Unknown Datalab mode {mode!r}; expected one of {DATALAB_MODES}")
    for i, total_chunks, chunk_start, chunk_path in _pdf_chunks(pdf_path, DATALAB_PAGE_LIMIT, start_page):
        chunk_texts = _run_surya_ocr_chunk(api_key, chunk_path, mode, chunk_start, include_page_numbers,
                                           filter_headers_footers, page_number_start, page_number_step)
        yield i, total_chunks, chunk_texts


def run_surya_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True, filter_headers_footers: bool = True,
                  page_number_start: int = 1, page_number_step: int = 1, mode: str = DATALAB_DEFAULT_MODE) -> tuple:
    """Submit PDF to Datalab (Surya), return (text, page_count)."""
    all_texts = []
    for _, _, chunk_texts in stream_surya_ocr(pdf_path, api_key, include_page_numbers, filter_headers_footers,
                                              page_number_start=page_number_start, page_number_step=page_number_step,
                                              mode=mode):
        all_texts.extend(chunk_texts)
    return "\n".join(all_texts), len(all_texts)


# =====================================================================================
# Sansar OCR 2B, via a self-hosted OpenAI-compatible server
# =====================================================================================
#
# sansar-ocr-2b (huggingface.co/MuseMesh/sansar-ocr-2b) is a fine-tune of Qwen3.5-2B for
# printed Devanagari Sanskrit. Nobody hosts it as an API, so it runs on a machine you
# control, behind an OpenAI-compatible chat endpoint: llama.cpp's `llama-server` with the
# GGUF + mmproj files (Mac / CPU), or `vllm serve` (NVIDIA GPU). See docs/ocr-sansar-surya.md.
#
# Skrutable only sends HTTP requests, so torch / transformers never enter its own
# dependencies. The server address comes from the SANSAR_SERVER_URL environment variable
# and never from the form: letting site visitors type an address would let them make this
# server send requests anywhere. With the variable unset, the Sansar option is hidden.
#
# The model reads one page image at a time, so each PDF page is rendered with pypdfium2,
# prepared exactly as in training (trim near-white margins, fit to <= 1.8 MP with sides
# divisible by 32), and sent with the one fixed prompt the model was trained on.
#
# Weights licence: CC BY-NC 4.0 (non-commercial, credit "Sansar, Muse Mesh Private Limited").

SANSAR_PROMPT = ("Transcribe all the text printed on this page exactly as printed, in reading order, line by line. "
                 "Output only the text.")
SANSAR_MAX_PIXELS = 1_800_000
SANSAR_MAX_NEW_TOKENS = 3072
SANSAR_PAGES_PER_CHUNK = 1   # one page per streamed event: local inference is slow per page


def sansar_server_url() -> str:
    """Base URL of the Sansar server, e.g. http://127.0.0.1:8080/v1, or "" when not configured."""
    return os.getenv("SANSAR_SERVER_URL", "").strip().rstrip("/")


def sansar_available() -> bool:
    return bool(sansar_server_url())


# --- page preparation -------------------------------------------------------------
# trim_margins and fit_pixels are adapted from the model card's ocr_page.py
# (Copyright 2026 Muse Mesh Private Limited, Apache License 2.0). The model is sensitive
# to page size, so the client must prepare pages the way training did.

def _sansar_trim_margins(im, pad: int = 24, thr_delta: int = 60):
    """Crop near-white outer margins (a dark scanner border counts as content and stays)."""
    import numpy as np
    g = im.convert("L")
    small = g.resize((max(1, g.width // 4), max(1, g.height // 4)))   # work at 1/4 size for speed
    a = np.asarray(small).astype(int)
    paper = np.percentile(a, 90)            # brightness of the paper
    ink = a < paper - thr_delta             # anything clearly darker than paper is "ink"
    rows = np.where(ink.mean(1) > 0.003)[0]
    cols = np.where(ink.mean(0) > 0.003)[0]
    if len(rows) < 2 or len(cols) < 2:
        return im                           # blank-ish page: leave it alone
    y0, y1, x0, x1 = rows[0] * 4, (rows[-1] + 1) * 4, cols[0] * 4, (cols[-1] + 1) * 4
    if (x1 - x0) * (y1 - y0) < 0.15 * im.width * im.height:
        return im                           # crop would be suspiciously small: don't trust it
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))


def _sansar_fit_pixels(im, max_pixels: int = SANSAR_MAX_PIXELS, min_side: int = 64, mult: int = 32):
    """Resize (aspect kept) so width x height <= max_pixels and both sides are multiples of 32."""
    from PIL import Image
    w, h = im.size
    s = min(1.0, math.sqrt(max_pixels / (w * h)))
    nw, nh = max(min_side, int(w * s) // mult * mult), max(min_side, int(h * s) // mult * mult)
    if (nw, nh) != (w, h):
        im = im.resize((nw, nh), Image.LANCZOS if s < 1 else Image.BICUBIC)
    return im


def _sansar_prepare_page(im):
    """PIL image -> the RGB image the model was trained on."""
    return _sansar_fit_pixels(_sansar_trim_margins(im.convert("RGB")))


def _render_pdf_pages(pdf_path: Path, first: int, last: int, dpi: int):
    """Generator: PIL images of PDF pages first..last-1 (0-based), rendered at `dpi`.

    200 dpi is plenty: an A4 page is then ~3.9 MP, which fit_pixels shrinks to 1.8 MP anyway.
    """
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for p in range(first, last):
            page = pdf[p]
            try:
                yield page.render(scale=dpi / 72).to_pil()
            finally:
                page.close()
    finally:
        pdf.close()


# --- one page ----------------------------------------------------------------------

def _looks_looped(text: str, threshold: float = 0.3) -> bool:
    """The card's known failure mode: the same line repeated until the token cap."""
    lines = [line for line in text.splitlines() if line.strip()]
    return len(lines) > 10 and 1 - len(set(lines)) / len(lines) > threshold


def _sansar_transcribe(image, page_number: int) -> str:
    """Send one prepared page to the Sansar server and return its text (NFC, lines joined by \\n)."""
    base_url = sansar_server_url()
    buf = io.BytesIO()
    _sansar_prepare_page(image).save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    body = {
        "model": os.getenv("SANSAR_MODEL", "sansar-ocr-2b"),  # llama-server ignores it; vLLM needs the served name
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": SANSAR_PROMPT},
        ]}],
        "temperature": 0,                 # greedy decoding, as on the model card
        "max_tokens": SANSAR_MAX_NEW_TOKENS,
        # Qwen3.5 chat template: thinking off, matching training. llama-server honours this
        # only when started with --jinja; vLLM honours it by default.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        r = requests.post(f"{base_url}/chat/completions", json=body,
                          timeout=float(os.getenv("SANSAR_TIMEOUT", "600")))
    except requests.ConnectionError:
        raise RuntimeError(f"Could not reach the Sansar server at {base_url}. Is it running?") from None
    if not r.ok:
        raise RuntimeError(f"Sansar server HTTP {r.status_code}: {r.text[:300]}")
    choice = r.json()["choices"][0]
    text = choice["message"].get("content") or ""
    # In case a server applies the template with thinking on anyway, drop the (empty) think block.
    text = re.sub(r"^\s*<think>.*?</think>\s*", "", text, flags=re.S)
    text = unicodedata.normalize("NFC", text.strip())
    # The two failure modes VLMs have and GCV/Sarvam don't. We only log them, so the
    # output stays plain OCR text; a later diff against GCV/Sarvam will show the damage.
    if choice.get("finish_reason") == "length":
        logger.warning("Sansar: page %d hit max_tokens (possible repetition loop)", page_number)
    elif _looks_looped(text):
        logger.warning("Sansar: page %d has many repeated lines (possible loop)", page_number)
    return text


# --- whole PDF -----------------------------------------------------------------------

def stream_sansar_ocr(pdf_path: Path, include_page_numbers: bool = True, start_page: int = 1,
                      page_number_start: int = 1, page_number_step: int = 1):
    """Generator: yields (chunk_index, total_chunks, chunk_texts), same contract as stream_sarvam_ocr.

    No API key: the server is whatever SANSAR_SERVER_URL points to. No header/footer filter
    either, since the model returns plain text (the card says it often drops running heads
    and footnotes by itself, but not reliably).
    """
    if not sansar_available():
        raise RuntimeError("Sansar OCR is not configured on this server (SANSAR_SERVER_URL is unset)")
    dpi = int(os.getenv("SANSAR_RENDER_DPI", "200"))
    total_pages = len(PdfReader(str(pdf_path)).pages)
    size = SANSAR_PAGES_PER_CHUNK
    total_chunks = (total_pages + size - 1) // size
    first = max(start_page, 1) - 1
    for chunk_start in range(first, total_pages, size):
        chunk_end = min(chunk_start + size, total_pages)
        texts = []
        for n, image in enumerate(_render_pdf_pages(pdf_path, chunk_start, chunk_end, dpi), start=chunk_start + 1):
            page_text = _sansar_transcribe(image, n)
            if include_page_numbers:
                page_text = f"\n=== {page_label(n, page_number_start, page_number_step)} ===\n{page_text}"
            texts.append(page_text)
        yield chunk_start // size + 1, total_chunks, texts


def run_sansar_ocr(pdf_path: Path, include_page_numbers: bool = True,
                   page_number_start: int = 1, page_number_step: int = 1) -> tuple:
    """OCR a PDF with the local Sansar server, return (text, page_count)."""
    all_texts = []
    for _, _, chunk_texts in stream_sansar_ocr(pdf_path, include_page_numbers,
                                               page_number_start=page_number_start, page_number_step=page_number_step):
        all_texts.extend(chunk_texts)
    return "\n".join(all_texts), len(all_texts)
