from natsort import natsorted
from pathlib import Path
import uuid, json, os, zipfile, tempfile
from google.cloud import storage, vision
from sarvamai import SarvamAI

BUCKET = os.getenv("GCS_BUCKET", "vision_multilang_ocr")   # set via env
PROJECT = os.getenv("GCP_PROJECT", "sanskrit-ocr-219110") # set via env

def run_google_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True) -> tuple:
    """Upload PDF, run async Vision OCR, return (text, page_count)."""
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

def run_sarvam_ocr(pdf_path: Path, api_key: str, include_page_numbers: bool = True) -> tuple:
    """Submit PDF to Sarvam Vision, return (text, page_count)."""
    client = SarvamAI(api_subscription_key=api_key)
    job = client.document_intelligence.create_job(language="sa-IN", output_format="md")
    job.upload_file(str(pdf_path))
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
                page_text = "\n".join(
                    b["text"] for b in blocks
                    if b.get("layout_tag") not in ("header", "footnote")
                )
                if include_page_numbers:
                    page_text = f"\n=== {i} ===\n{page_text}"
                texts.append(page_text)

    return "\n".join(texts), len(json_names)
