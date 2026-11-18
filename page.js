if(localStorage.getItem('theme')==='dark')document.documentElement.setAttribute('data-theme','dark');

(function() {
	var toggle = document.getElementById('dark-mode-toggle');
	function applyTheme(dark) {
		document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
		toggle.innerHTML = dark ? '&#9788;' : '&#9790;';
		toggle.title = dark ? 'Toggle light mode' : 'Toggle dark mode';
	}
	applyTheme(localStorage.getItem('theme') === 'dark');
	toggle.addEventListener('click', function(e) {
		e.preventDefault();
		var isDark = document.documentElement.getAttribute('data-theme') !== 'dark';
		localStorage.setItem('theme', isDark ? 'dark' : 'light');
		applyTheme(isDark);
	});
})();


(function() {
	var link = document.getElementById('example-link');
	var current = parseInt(new URLSearchParams(window.location.search).get('example')) || 0;
	var next = current >= 3 ? 1 : current + 1;
	link.href = '/?example=' + next;
	link.textContent = 'ex' + next;
	link.title = 'example ' + next;
})();


function downloadOcrText() {
  const text = document.getElementById("ocrText").value;
  const provider = document.getElementById("ocr_provider_input").value;
  let dlName;
  if (STREAMING_PROVIDERS.includes(provider) && window._streamDlFilename) {
    dlName = window._streamDlFilename;
  } else {
    const originalFile = fileInput.files[0] || window.selectedPdfFile;
    const baseName = originalFile ? originalFile.name.replace(/\.pdf$/i, '') : 'ocr_result';
    dlName = `${baseName}-skrutable-${PROVIDER_TAGS[provider]}-ocr.txt`;
  }
  const blob = new Blob([text], { type: 'text/plain' });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = dlName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) {
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  } else {
    return (bytes / 1024).toFixed(2) + " KB";
  }
}

const dz = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInputPdf');
dz.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (file) {
    dz.innerHTML = `${file.name}<br>(${formatBytes(file.size)})`;
  }
});
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
dz.addEventListener('drop', e => {
  e.preventDefault(); dz.classList.remove('dragover');
  if (e.dataTransfer.files.length) {
    window.selectedPdfFile = e.dataTransfer.files[0];
    dz.innerHTML = `${window.selectedPdfFile.name}<br>(${formatBytes(window.selectedPdfFile.size)})`;
  }
});

// Start/step fields only matter when page numbers are added
function syncPageNumberingFields() {
  const on = document.getElementById("includePageNumbers").checked;
  document.getElementById("pageNumberingFields").style.display = on ? "block" : "none";
}
document.getElementById("includePageNumbers").addEventListener("change", syncPageNumberingFields);
syncPageNumberingFields();

// Providers whose results arrive chunk by chunk over /ocr/stream (Google uses one /ocr request)
const STREAMING_PROVIDERS = ["sarvam", "surya", "sansar"];
// Tag used in download filenames; matches OCR_PROVIDER_TAGS in flask_app.py
const PROVIDER_TAGS = {
  google: "cloud-vision",
  sarvam: "sarvam-vision",
  surya:  "surya-datalab",
  sansar: "sansar-ocr-2b",
};
// Toggle button / settings section ids per provider. The Sansar ones exist only when the
// server has SANSAR_SERVER_URL set, hence the null checks below.
const PROVIDER_IDS = {
  google: ["providerGoogle", "googleKeySection"],
  sarvam: ["providerSarvam", "sarvamKeySection"],
  surya:  ["providerSurya",  "suryaKeySection"],
  sansar: ["providerSansar", "sansarKeySection"],
};
// Providers whose output knows which blocks are headers/footers
const HEADER_FOOTER_PROVIDERS = ["sarvam", "surya"];

function setProvider(provider) {
  for (const [name, [buttonId, sectionId]] of Object.entries(PROVIDER_IDS)) {
    const button = document.getElementById(buttonId);
    const section = document.getElementById(sectionId);
    if (button) button.classList.toggle("active", name === provider);
    if (section) section.style.display = name === provider ? "" : "none";
  }
  document.getElementById("ocr_provider_input").value = provider;
  document.getElementById("filterHeadersFootersOption").style.display =
    HEADER_FOOTER_PROVIDERS.includes(provider) ? "" : "none";
}

const progressBar = document.getElementById("progressBar");
const progressContainer = document.getElementById("progressContainer");

// Cost line below the result — wording/links match the cost section of ocr_instructions.html;
// rates and links come from /assets/js/ocr_pricing.js
function showCostEstimate(provider, pageCount, inrToUsd) {
  if (!pageCount) return;
  const extLinkIcon = document.getElementById("extLinkIconTemplate").innerHTML;
  const rateLink = OCR_PRICING[provider] && OCR_PRICING[provider].rateLabel ? ocrRateLink(provider, extLinkIcon) : "";
  let html;
  if (provider === "surya") {
    const mode = document.getElementById("datalabMode").value;
    const cost = suryaCostUsd(pageCount, mode);
    const costStr = cost < 0.01 ? cost.toFixed(4) : cost.toFixed(2);
    html = `Pages processed: ${pageCount} — estimated cost: $${costStr} (= ${pageCount} pages × ${suryaRateLink(mode, extLinkIcon)}, ${mode} mode; ${suryaDataSharingRateLabel(mode)} if you let Datalab train on your data; Datalab's free monthly credit applies first)`;
  } else if (provider === "sansar") {
    html = `Pages processed: ${pageCount} — no per-page charge (runs on this site's own Sansar server)`;
  } else if (provider === "sarvam") {
    const inr = sarvamCostInr(pageCount);
    if (inrToUsd) {
      html = `Pages processed: ${pageCount} — estimated cost: $${(inr * inrToUsd).toFixed(2)} (= ${pageCount} pages × ${rateLink} × ${fxRateLink(inrToUsd, extLinkIcon)})`;
    } else {
      html = `Pages processed: ${pageCount} — estimated cost: ₹${inr.toFixed(2)} (= ${pageCount} pages × ${rateLink})`;
    }
  } else {
    const cost = googleCostUsd(pageCount);
    const costStr = cost < 0.01 ? cost.toFixed(4) : cost.toFixed(2);
    html = `Pages processed: ${pageCount} — estimated cost: $${costStr} (= ${pageCount} pages × ${rateLink}; the first 1,000 pages per month are free)`;
  }
  document.getElementById("pagesProcessed").innerHTML = html;
}

function estimateProgress(file) {
  const minimumTimeEstimate = 25000
  const estimatedPages = Math.max(1, Math.floor(file.size / (1024 * 100)));
  const estimatedTime = minimumTimeEstimate + Math.max(0, estimatedPages - 1) * 1000;
  const startTime = Date.now();

  progressContainer.style.display = "block";
  progressBar.style.width = "0%";
  progressBar.textContent = "0%";
  progressBar.setAttribute("aria-valuenow", "0");
  progressBar.classList.remove("zoom-bounce", "error-state", "progress-bar-striped", "active");
  progressBar.style.backgroundColor = "steelblue";

  const interval = setInterval(() => {
    const elapsed = Date.now() - startTime;
    const progress = Math.min(99, (elapsed / estimatedTime) * 100);
    const display = Math.floor(progress);
    progressBar.style.width = `${display}%`;
    progressBar.textContent = display >= 99 ? "99%..." : `${display}%`;
    progressBar.setAttribute("aria-valuenow", display);
  }, 300);

  return interval;
}

function clearOcrResult() {
  const resultContainer = document.getElementById("ocrResultContainer");
  const resultVisible = getComputedStyle(resultContainer).display !== "none";
  const progressContainer = document.getElementById("progressContainer");

  if (!resultVisible) return;

  const textArea = document.getElementById("ocrText");
  const text = textArea?.value?.trim();

  if (text) {
    const confirmClear = confirm("Clear the current OCR result?");
    if (!confirmClear) return;
    streamRunId++;  // stop any streaming run still in progress or reconnecting
    resultContainer.style.display = "none";
    progressContainer.style.display = "none";
    document.getElementById("pagesProcessed").textContent = "";
  }
}

document.getElementById("startOcr").addEventListener("click", async function () {
  const progressContainer = document.getElementById("progressContainer");
  const progressVisible = getComputedStyle(progressContainer).display !== "none";
  const resultContainer = document.getElementById("ocrResultContainer");

  if (progressVisible) {
    const confirmed = confirm("A task may already be in progress or completed. Clear and start a new one?");
    if (!confirmed) return;
    resultContainer.style.display = "none";
    progressContainer.style.display = "none";
  }

  const bytes_per_mb = 1024 * 1024;
  const max_mb = 128;
  const max_bytes = max_mb * bytes_per_mb;

  const pdfFile = fileInput.files[0] || window.selectedPdfFile;
  if (!pdfFile) return alert("Please upload a PDF.");

  if (pdfFile.size > max_bytes) {
    alert(`File is ${(pdfFile.size/1048576).toFixed(1)} MB; limit is ${max_bytes/1048576} MB.`);
    return;
  }

  const provider = document.getElementById("ocr_provider_input").value;
  const keyInput = document.getElementById(provider + "ApiKey");  // none for Sansar
  const apiKey = keyInput ? keyInput.value : "";
  if (keyInput && !apiKey) return alert("API key is required.");

  const includePageNumbers   = document.getElementById("includePageNumbers").checked;
  const filterHeadersFooters = document.getElementById("filterHeadersFooters").checked;

  const pageNumberStart = Number(document.getElementById("pageNumberStart").value || 1);
  const pageNumberStep  = Number(document.getElementById("pageNumberStep").value || 1);
  if (includePageNumbers) {
    if (!Number.isInteger(pageNumberStart)) return alert("Starting page number must be a whole number.");
    if (!Number.isInteger(pageNumberStep) || pageNumberStep < 1) return alert("Page numbers must count by a whole number of 1 or more.");
  }

  const formData = new FormData();
  formData.append("pdf_file", pdfFile);
  formData.append("ocr_provider", provider);
  formData.append("api_key", apiKey);
  formData.append("include_page_numbers", includePageNumbers ? "yes" : "no");
  formData.append("filter_headers_footers", filterHeadersFooters ? "yes" : "no");
  formData.append("page_number_start", String(pageNumberStart));
  formData.append("page_number_step", String(pageNumberStep));
  if (provider === "surya") formData.append("datalab_mode", document.getElementById("datalabMode").value);

  progressBar.style.width = "0%";
  progressBar.textContent = "0%";
  progressBar.setAttribute("aria-valuenow", 0);
  progressBar.classList.add("progress-bar-striped", "active");
  progressBar.classList.remove("zoom-bounce", "error-state");

  if (STREAMING_PROVIDERS.includes(provider)) {
    // Discrete chunk-based progress: bar advances only as chunks return.
    progressContainer.style.display = "block";
    progressBar.style.backgroundColor = "steelblue";
    progressBar.textContent = "uploading…";
    await runStreamingOcr(provider, formData);
  } else {
    const interval = estimateProgress(pdfFile);
    await runGoogleOcr(formData, interval, pdfFile);
  }
});

// Bumped on every new run or clear, so a stale run (e.g. one waiting to
// reconnect) stops instead of writing into the new one's result.
let streamRunId = 0;

// Retries allowed in a row without receiving any new chunk before giving up
const STREAM_MAX_RETRIES = 8;

function setProgressError(label) {
  progressBar.classList.add("error-state");
  progressBar.classList.remove("progress-bar-striped", "active");
  progressBar.textContent = label;
  progressBar.style.width = "100%";
  progressBar.setAttribute("aria-valuenow", 100);
}

// Wait until the browser reports a network connection, then delayMs more
function waitForReconnect(delayMs) {
  return new Promise(function (resolve) {
    function go() { setTimeout(resolve, delayMs); }
    if (navigator.onLine) go();
    else window.addEventListener("online", go, { once: true });
  });
}

// Runs a chunked provider (Sarvam, Surya or Sansar) over /ocr/stream, resuming after drops.
async function runStreamingOcr(provider, formData) {
  const runId      = ++streamRunId;
  const ocrText    = document.getElementById("ocrText");
  const resultBox  = document.getElementById("ocrResultContainer");
  let accumulatedText = "";
  let pagesDone    = 0;   // pages received so far; a resume starts after these
  let dlFilename   = null;
  let retries      = 0;

  // FX rate for the running Sarvam cost estimate; chunks take minutes, so this
  // resolves well before the first one (₹ fallback covers the rare miss)
  let fxRate = null;
  if (provider === "sarvam") fetchInrToUsd().then(function (rate) { fxRate = rate; });

  // Sansar streams one page per chunk, so say "page" rather than "chunk" in the bar
  const unit = provider === "sansar" ? "page" : "chunk";

  // One request to /ocr/stream, starting after pagesDone.
  // Returns "done" or "error", or "dropped" if the connection was lost.
  async function streamOnce() {
    formData.set("start_page", String(pagesDone + 1));

    let res;
    try {
      res = await fetch("/ocr/stream", { method: "POST", body: formData });
    } catch (err) {
      console.warn("runStreamingOcr: request failed", err);
      return "dropped";
    }

    if (!res.ok) {
      const errText = await res.text();
      console.error("runStreamingOcr: HTTP", res.status, errText);
      setProgressError(res.status === 413 ? errText : "Error");
      return "error";
    }

    if (runId !== streamRunId) return "error";
    progressBar.classList.remove("error-state");
    progressBar.classList.add("progress-bar-striped", "active");
    progressBar.textContent = pagesDone ? `resumed at page ${pagesDone + 1}…` : "processing…";

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) return "dropped";  // stream ended without a "done" event
        if (runId !== streamRunId) { reader.cancel(); return "error"; }
        buf += decoder.decode(value, { stream: true });

        const lines = buf.split("\n");
        buf = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let evt;
          try { evt = JSON.parse(line.slice(6)); } catch { continue; }

          if (evt.type === "chunk") {
            retries = 0;
            pagesDone = evt.pages;
            const pct = Math.round((evt.index / evt.total) * 100);
            progressBar.style.width   = `${pct}%`;
            progressBar.textContent   = `${pct}% (${unit} ${evt.index}/${evt.total})`;
            progressBar.setAttribute("aria-valuenow", pct);

            if (accumulatedText) accumulatedText += "\n";
            accumulatedText += evt.text;
            ocrText.value = accumulatedText;

            if (resultBox.style.display === "none" || resultBox.style.display === "") {
              resultBox.style.display = "block";
            }

            showCostEstimate(provider, evt.pages || 0, fxRate);
          } else if (evt.type === "done") {
            dlFilename = evt.filename || null;
            showCostEstimate(provider, evt.pages || 0, evt.inr_to_usd || fxRate);
            return "done";
          } else if (evt.type === "error") {
            setProgressError(evt.status === 402 ? "No API credits" : "Error");
            alert(evt.message);
            return "error";
          }
        }
      }
    } catch (err) {
      console.warn("runStreamingOcr: connection lost", err);
      return "dropped";
    }
  }

  while (true) {
    const result = await streamOnce();
    if (runId !== streamRunId) return;
    if (result === "error") return;
    if (result === "done") break;

    // dropped: keep what we have and resume after the last page received
    if (++retries > STREAM_MAX_RETRIES) {
      setProgressError(`Connection lost at page ${pagesDone} — partial result below`);
      return;
    }
    setProgressError(`Connection lost at page ${pagesDone} — reconnecting…`);
    await waitForReconnect(Math.min(2000 * 2 ** (retries - 1), 30000));
    if (runId !== streamRunId) return;
    progressBar.textContent = `re-uploading to resume at page ${pagesDone + 1}…`;
  }

  progressBar.classList.remove("error-state");
  progressBar.style.width = "100%";
  progressBar.textContent = "100%";
  progressBar.setAttribute("aria-valuenow", 100);
  progressBar.classList.remove("progress-bar-striped", "active");
  progressBar.classList.remove("zoom-bounce");
  void progressBar.offsetWidth;
  progressBar.classList.add("zoom-bounce");

  if (dlFilename) window._streamDlFilename = dlFilename;

  resultBox.classList.remove("animate-zoom");
  void resultBox.offsetWidth;
  resultBox.classList.add("animate-zoom");
}

async function runGoogleOcr(formData, interval, pdfFile) {
  try {
    const res = await fetch("/ocr", { method: "POST", body: formData });

    if (!res.ok) {
      clearInterval(interval);

      if (res.status === 413) {
        const msg = await res.text();
        progressBar.classList.add("error-state");
        progressBar.textContent  = msg;
        progressBar.style.width  = "100%";
        progressBar.setAttribute("aria-valuenow", 100);
        alert(msg);
        return;
      }

      const errText = await res.text();
      throw new Error(`OCR request failed: ${errText}`);
    }

    clearInterval(interval);
    let display = parseFloat(progressBar.style.width);

    const fillInterval = setInterval(() => {
      display += 2;
      if (display >= 100) {
        display = 100;
        clearInterval(fillInterval);
        progressBar.style.width = "100%";
        progressBar.textContent = "100%";
        progressBar.setAttribute("aria-valuenow", 100);
        progressBar.classList.remove("progress-bar-striped", "active");
        progressBar.classList.remove("zoom-bounce");
        void progressBar.offsetWidth;
        progressBar.classList.add("zoom-bounce");
      } else {
        progressBar.style.width = `${display}%`;
        progressBar.textContent = `${Math.floor(display)}%`;
        progressBar.setAttribute("aria-valuenow", Math.floor(display));
      }
    }, 30);

    const pageCount = parseInt(res.headers.get("X-Pages-Processed") || "0", 10);
    showCostEstimate("google", pageCount, null);

    const raw = await res.text();
    const text = raw.replace(/<[^>]*>/g, '');
    const resultBox = document.getElementById("ocrResultContainer");

    setTimeout(() => {
      document.getElementById("ocrText").value = text;
      resultBox.style.display = "block";
      resultBox.classList.remove("animate-zoom");
      void resultBox.offsetWidth;
      resultBox.classList.add("animate-zoom");
    }, 700);

  } catch (err) {
    clearInterval(interval);
    console.error("runGoogleOcr: error", err);
    progressBar.classList.add("error-state");
    progressBar.textContent = "Error";
    progressBar.setAttribute("aria-valuenow", 100);
    progressBar.style.width = "100%";
    progressBar.classList.remove("progress-bar-striped", "active");
  }
}

function copyOcrText() {
  const btn = document.getElementById("copyButton");
  const textArea = document.getElementById("ocrText");
  navigator.clipboard.writeText(textArea.value).then(() => {
    const originalText = btn.textContent;
    btn.textContent = "Copied!";
    btn.disabled = true;

    setTimeout(() => {
      btn.textContent = originalText;
      btn.disabled = false;
    }, 1200);
  });
}

let currentFontSize = 20;

function changeFontSize(delta) {
  const textArea = document.getElementById("ocrText");
  if (!textArea || textArea.offsetParent === null) return;
  currentFontSize += delta;
  textArea.style.fontSize = `${currentFontSize}px`;
}

function setFontSize(size) {
  const textArea = document.getElementById("ocrText");
  if (textArea) {
    textArea.style.fontSize = `${size}px`;
  }
}
