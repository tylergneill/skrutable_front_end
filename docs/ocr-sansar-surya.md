# Two new OCR options: Sansar OCR 2B and Surya (Datalab)

Experimental branch. The `/ocr` page now offers four providers instead of two:

| Provider | Where it runs | Key | Header/footer filter | Streams by |
|---|---|---|---|---|
| Google Cloud Vision | Google (hosted) | user's own, in the form | no | one request |
| Sarvam Vision | Sarvam (hosted) | user's own, in the form | yes | 10-page chunks |
| **Surya (Datalab)** | Datalab (hosted) | user's own Datalab key, in the form | yes | 10-page chunks |
| **Sansar OCR 2B** | a server you run | none | no | 1 page at a time |

Both new options follow the Sarvam pattern in `ocr_service.py`: a `stream_*_ocr()`
generator that yields `(chunk_index, total_chunks, chunk_texts)`, plus a `run_*_ocr()`
wrapper that joins the chunks. `/ocr/stream` now picks the generator by `ocr_provider`
(missing `ocr_provider` still means Sarvam, so old clients keep working), and the
browser uses the same streaming, progress bar and resume-after-drop code for all three
chunked providers.

## What changed

- `ocr_service.py`
  - `_pdf_chunks()`: the PDF-splitting loop that was inside `stream_sarvam_ocr`, pulled
    out so Sarvam and Surya share it. Sarvam's behaviour is unchanged.
  - Surya section: `stream_surya_ocr` / `run_surya_ocr`, Datalab's async convert API
    (submit, poll `request_check_url`, read JSON). JSON keeps one `Page` block per page
    with typed children, which gives us page labels and lets us drop `PageHeader`,
    `PageFooter` and `Footnote` blocks when the filter box is ticked.
  - Sansar section: `stream_sansar_ocr` / `run_sansar_ocr`. Renders each PDF page with
    pypdfium2, prepares it exactly as the model was trained (trim margins, fit to
    ≤ 1.8 MP, sides divisible by 32), and sends it with the model's fixed prompt to an
    OpenAI-compatible `/chat/completions` endpoint.
- `flask_app.py`: shared form parsing (`_ocr_options_from_form`), per-provider file tags
  and out-of-credit messages; `/ocr` and `/ocr/stream` dispatch to all four providers.
- `templates/ocr.html`: two new provider buttons, a Datalab key field and mode menu, a
  Sansar note; the Sarvam-only stream code is now `runStreamingOcr(provider, ...)`.
- `assets/js/ocr_pricing.js`: Datalab's per-mode rates for the cost line.
- `requirements.in` / `.txt`: `pypdfium2` (renders PDF pages; Apache/BSD, wheels include
  PDFium, no system packages), `pillow`, and `numpy` (already present via skrutable, now
  declared because the Sansar code uses it directly).

## Surya via Datalab

You need a Datalab API key (datalab.to; free credit each month, no card). Paste it into
the key field on `/ocr`, the same way as a Sarvam key. Nothing to configure on the server.

- **Mode** (`lite`, `fast`, `balanced`, `accurate`): Datalab's speed/accuracy/price tier,
  $0.375 to $7.50 per 1,000 pages. `balanced` is the default because it's Datalab's.
- Datalab has **no model selector**: the mode decides which of its models run, so this is
  "Datalab's Surya-based pipeline", not a pinned Surya checkpoint. If you want Surya itself,
  pinned, the alternative is `pip install surya-ocr` locally (not wired in here).
- Free tier allows 10 requests a minute; on HTTP 429 the adapter waits 60 s and retries.
- Optional env var: `DATALAB_PAGES_PER_REQUEST` (default 10).

## Sansar via a local llama.cpp server

Sansar has no hosted API, so you run the model yourself and point Skrutable at it with
`SANSAR_SERVER_URL`. Without that variable the Sansar button doesn't appear at all, which
is what the public site should do unless it gets a GPU box. The address deliberately
can't be typed into the form: that would let any visitor make the server fetch any URL.

On a Mac (Metal) or plain CPU:

```bash
brew install llama.cpp
# Downloads the Q8_0 GGUF (~2.1 GB) and, normally, its vision projector (mmproj) too.
# --jinja is needed so the request can switch the model's "thinking" off, as in training.
# -c 8192 leaves room for ~1,800 image tokens plus up to 3,072 output tokens.
llama-server -hf mradermacher/sansar-ocr-2b-GGUF:Q8_0 --jinja -c 8192 --port 8080
```

If the server starts without image support (it logs that no mmproj was loaded), download
the model and the `mmproj-Q8_0` file from that repo and pass them explicitly:
`llama-server -m <model>.gguf --mmproj <mmproj>.gguf --jinja -c 8192 --port 8080`.

On an NVIDIA GPU, vLLM serves the original weights instead:

```bash
vllm serve MuseMesh/sansar-ocr-2b --served-model-name sansar-ocr-2b --max-model-len 8192 --port 8080
```

Then run Skrutable against it:

```bash
./launch.sh --sansar        # or: make launch-sansar
# open http://127.0.0.1:5012/ocr and pick "Sansar OCR 2B"
```

`--sansar` sets `SANSAR_SERVER_URL` to `http://127.0.0.1:8080/v1` unless you've already set
it to something else. Sansar is meant as a local-only option: the Dockerfiles never set the
variable, so skrutable.info never shows it.

Optional env vars:

| Variable | Default | Meaning |
|---|---|---|
| `SANSAR_SERVER_URL` | unset (option hidden) | base URL ending in `/v1` |
| `SANSAR_MODEL` | `sansar-ocr-2b` | model name sent in the request (vLLM checks it; llama-server ignores it) |
| `SANSAR_RENDER_DPI` | `200` | PDF render resolution before the 1.8 MP fit |
| `SANSAR_TIMEOUT` | `600` | seconds to wait for one page |

Things to know:

- Printed Devanagari Sanskrit only; two-column pages and tables can come out in the wrong
  order (model card).
- On hard pages the model can repeat a line until it hits the 3,072-token cap, or invent
  text on blank pages. The adapter logs a warning for the first case ("hit max_tokens" or
  "many repeated lines") but leaves the text as returned.
- Quantization may cost a little accuracy. Q8_0 is the safe start; compare a few pages
  against vLLM/bf16 if it matters.
- Weights are CC BY-NC 4.0 (non-commercial; credit "Sansar, Muse Mesh Private Limited").
  `_sansar_trim_margins` and `_sansar_fit_pixels` are adapted from the card's `ocr_page.py`
  (Apache-2.0).

## Not done yet

- No changelog entry in `templates/updates.html`, and `ocr_instructions.html` (FAQ, cost
  calculator, side-by-side) still only covers GCV and Sarvam.
- Datalab's prices aren't in the daily price check (`.github/scripts/check_ocr_prices.py`).
- `bulk_vision_runner.py` is still GCV-only.
