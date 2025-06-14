#!/bin/bash
export FLASK_APP=flask_app.py
export PORT=4999
flask --debug run --port=$PORT