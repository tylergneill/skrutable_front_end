#!/bin/bash
export FLASK_APP=flask_app.py
export PORT=5012
export GOOGLE_APPLICATION_CREDENTIALS="$(dirname "$0")/assets/uploader.json"

for arg in "$@"; do
	case "$arg" in
		--scan-profiling) export SKRUTABLE_DEBUG_TIMING=1 ;;
		--no-parallel) export SKRUTABLE_NO_PARALLEL=1 ;;
		--vm-host) HOST=10.211.55.2 ;;
		# Local-only Sansar OCR option: needs a Sansar server already running
		# (see docs/ocr-sansar-surya.md). Never set in the Dockerfiles, so the
		# public site never shows it. An existing SANSAR_SERVER_URL wins.
		--sansar) export SANSAR_SERVER_URL="${SANSAR_SERVER_URL:-http://127.0.0.1:8080/v1}" ;;
	esac
done

# Default to loopback. --vm-host binds only the Parallels Shared Networking
# address so a VM browser can reach the server; deliberately NOT 0.0.0.0,
# which would expose the --debug console to whatever network we're on.
python -m flask --debug run --host="${HOST:-127.0.0.1}" --port=$PORT