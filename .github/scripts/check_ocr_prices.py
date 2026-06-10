#!/usr/bin/env python3
"""
Check OCR per-page prices for Google Cloud Vision and Sarvam Vision.
Exits nonzero if any price differs from the known-good values,
triggering a GitHub Actions failure email.
"""

import re
import sys
import urllib.request
import urllib.error

KNOWN = {
    "gcv_document_text": {"price": "1.50", "currency": "USD", "unit": "1000 pages"},
    "sarvam_vision":     {"price": "0.5",  "currency": "INR", "unit": "page"},
}

GCV_URL    = "https://cloud.google.com/vision/pricing"
SARVAM_URL = "https://docs.sarvam.ai/api-reference-docs/pricing"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; skrutable-price-check/1.0)"}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def check_gcv(html):
    m = re.search(
        r'Document Text Detection.*?<td[^>]*>Free</td>\s*<td[^>]*>\$([\d.]+)</td>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return None, "parse failure: could not find Document Text Detection row"
    return m.group(1), None


def check_sarvam(html):
    # Matches the table row: Document Digitization API | ₹0.5 | per page
    m = re.search(r'Document Digitization API.*?₹([\d.]+).*?per page', html, re.DOTALL | re.IGNORECASE)
    if not m:
        # fallback: look for escaped version in JS bundle
        m = re.search(r'Document Digitization API.*?₹([\d.]+)', html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None, "parse failure: could not find Sarvam Vision pricing row"
    return m.group(1), None


alerts = []

for provider, check_fn, url in [
    ("gcv_document_text", check_gcv,    GCV_URL),
    ("sarvam_vision",     check_sarvam, SARVAM_URL),
]:
    known = KNOWN[provider]
    try:
        html = fetch(url)
    except urllib.error.URLError as e:
        alerts.append(f"FETCH FAILURE [{provider}]: {url} — {e}")
        continue

    price, err = check_fn(html)
    if err:
        alerts.append(f"PARSE FAILURE [{provider}]: {err} (source: {url})")
        continue

    if price != known["price"]:
        alerts.append(
            f"PRICE CHANGE [{provider}]: was {known['currency']} {known['price']}"
            f" / {known['unit']}, now {known['currency']} {price} / {known['unit']}"
            f" (source: {url})"
        )
    else:
        print(f"OK [{provider}]: {known['currency']} {price} / {known['unit']}")

if alerts:
    print("\n--- ALERTS ---")
    for a in alerts:
        print(a)
    sys.exit(1)
