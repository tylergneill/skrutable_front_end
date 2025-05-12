from pathlib import Path
import uuid, json, os
from google.cloud import storage, vision

BUCKET = os.getenv("GCS_BUCKET", "vision_multilang_ocr")   # set via env
PROJECT = os.getenv("GCP_PROJECT", "sanskrit-ocr-219110") # set via env

def run_google_ocr(pdf_path: Path, api_key: str) -> str:
    """Upload PDF, run async Vision OCR, return concatenated text."""
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

    texts = []
    for blob in bucket.list_blobs(prefix=f"{job_id}/ocr/"):
        data = json.loads(blob.download_as_text())["responses"][0]
        texts.append(data.get("fullTextAnnotation", {}).get("text", ""))

    bucket.delete_blobs(list(bucket.list_blobs(prefix=job_id)))

    return "\n".join(texts)
