// Single source of truth for OCR pricing shown in the UI (ocr.html result line
// and ocr_instructions.html cost section/calculator).
// When a confirmed provider price change comes in via the daily check
// (.github/scripts/check_ocr_prices.py), update both the KNOWN dict there and
// the values here.

var OCR_PRICING = {
  sarvam: {
    inrPerPage: 0.50,
    rateLabel: "₹0.50/page",
    pricingUrl: "https://www.sarvam.ai/api-pricing",
  },
  google: {
    usdPerPage: 0.0015,
    rateLabel: "$1.50 / 1,000 pages",
    pricingUrl: "https://cloud.google.com/vision/pricing",
    freePagesPerMonth: 1000,
  },
  // Datalab (Surya) bills per page by mode. Not yet covered by the daily price check
  // in .github/scripts/check_ocr_prices.py. Rates read from datalab.to/pricing, Nov 2026.
  surya: {
    usdPer1000PagesByMode: { lite: 0.375, fast: 1.0, balanced: 3.0, accurate: 7.5 },
    pricingUrl: "https://www.datalab.to/pricing",
    freeCreditUsdPerMonth: 10,   // $20 with a work email
  },
  // Sansar runs on a self-hosted server: no per-page price.
  fxApiUrl: "https://api.frankfurter.dev/v1/latest?from=INR&to=USD",
  fxInfoUrl: "https://www.frankfurter.dev",
};

// Resolves to the INR→USD rate, or null on failure.
function fetchInrToUsd() {
  return fetch(OCR_PRICING.fxApiUrl)
    .then(function (r) { return r.json(); })
    .then(function (data) { return data.rates.USD; })
    .catch(function () { return null; });
}

// '<a ...>₹0.50/page<svg .../></a>' — provider rate linked to its pricing page.
function ocrRateLink(provider, extLinkIcon) {
  var p = OCR_PRICING[provider];
  return '<a href="' + p.pricingUrl + '" target="_blank">' + p.rateLabel + (extLinkIcon || "") + '</a>';
}

// '<a ...>$0.0107/₹<svg .../></a>' — INR→USD exchange rate linked to frankfurter.dev.
function fxRateLink(inrToUsd, extLinkIcon) {
  return '<a href="' + OCR_PRICING.fxInfoUrl + '" target="_blank">$' + inrToUsd.toFixed(4) + '/₹' + (extLinkIcon || "") + '</a>';
}

function sarvamCostInr(pages) {
  return pages * OCR_PRICING.sarvam.inrPerPage;
}

function googleCostUsd(billablePages) {
  return billablePages * OCR_PRICING.google.usdPerPage;
}

// '$3.00 / 1,000 pages' for a Datalab mode, linked to Datalab's pricing page.
function suryaRateLink(mode, extLinkIcon) {
  var p = OCR_PRICING.surya;
  var label = "$" + p.usdPer1000PagesByMode[mode].toFixed(2) + " / 1,000 pages";
  return '<a href="' + p.pricingUrl + '" target="_blank">' + label + (extLinkIcon || "") + '</a>';
}

function suryaCostUsd(pages, mode) {
  return pages * OCR_PRICING.surya.usdPer1000PagesByMode[mode] / 1000;
}
