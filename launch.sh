#!/bin/bash
export FLASK_APP=flask_app.py
export PORT=5012

for arg in "$@"; do
	case "$arg" in
		--scan-profiling) export SKRUTABLE_DEBUG_TIMING=1 ;;
	esac
done

python -m flask --debug run --port=$PORT