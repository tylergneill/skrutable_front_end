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
