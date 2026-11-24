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
from decimal import Decimal

KNOWN = {
    "gcv_document_text": {"price": "1.50", "currency": "USD", "unit": "1000 pages"},
    "sarvam_vision":     {"price": "0.5",  "currency": "INR", "unit": "page"},
}

GCV_URL    = "https://cloud.google.com/vision/pricing"
SARVAM_URL = "https://docs.sarvam.ai/api-reference-docs/pricing"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; skrutable-price-check/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_tags(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def diagnose(html, needle):
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    title = title.group(1).strip() if title else "(none)"
    text = strip_tags(html)
    i = text.lower().find(needle.lower())
    snippet = text[i:i + 200] if i >= 0 else "(needle not found)"
    return f"len={len(html)}, title={title!r}, snippet={snippet!r}"


def check_gcv(html):
    # Match on tag-stripped text so attribute/whitespace changes in the table don't break parsing.
    # Google redesigned the page (Oct 2026) with a tiered layout; the old table is kept as a fallback.
    # Either way we want the 1,001-5M tier price:
    #   tiered: Document Text Detection 0 count to 1,000 count $0.00 (Free) 1,000 count to 5,000,000 count $1.50 ...
    #   old:    Document Text Detection | Free | $1.50 | $0.60
    m = re.search(
        r'Document Text Detection (?:Free|.{0,100}?1,000 count to 5,000,000 count) \$([\d.]+)',
        strip_tags(html), re.IGNORECASE
    )
    if not m:
        return None, ("parse failure: could not find Document Text Detection row; "
                      + diagnose(html, "Document Text Detection"))
    return m.group(1), None


def check_sarvam(html):
    # Sarvam renamed the row (Nov 2026) from "Document Digitization API" to:
    #   Document AI: Parse | ₹0.50 | ₹0.50 | ₹0.50   (pay-as-you-go, Pro, Growth)
    # We take the first price after the label, i.e. pay-as-you-go.
    # The old regex, anchored on "Document Digitization API" with a lazy .*?, latched onto a
    # leftover mention of the legacy endpoint and read the Pro plan fee "₹9,999" as "9".
    # Guards against that: the gap between label and price is capped and may not contain
    # another ₹, and the price allows thousands commas so a ₹9,999 can never be cut to 9.
    pattern = r'Document AI: Parse[^₹]{0,80}?₹\s*([\d,]+(?:\.\d+)?)'
    # Prefer tag-stripped text (cells become space-separated); fall back to raw HTML
    # in case the table only exists inside an embedded JS/JSON payload.
    m = re.search(pattern, strip_tags(html), re.IGNORECASE) or re.search(pattern, html, re.IGNORECASE)
    if not m:
        return None, ("parse failure: could not find Document AI: Parse row; "
                      + diagnose(html, "Document AI: Parse"))
    return m.group(1).replace(",", ""), None


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

    if Decimal(price) != Decimal(known["price"]):
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
