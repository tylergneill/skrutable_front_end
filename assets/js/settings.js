// Shared sidebar settings functions.
// Expects these globals from the including page:
//   currentAction, currentAvoidVirama, currentPreservePunctuation, currentPreserveCompoundHyphens

function getSidebarSettings() {
	return {
		from_scheme: document.getElementById("from_scheme").value,
		to_scheme: document.getElementById("to_scheme").value,
		resplit_option: document.getElementById("resplit_option").value,
		splitter_model: document.getElementById("splitter_model_sidebar").value,
		weights: document.getElementById("weights").checked,
		morae: document.getElementById("morae").checked,
		gaRas: document.getElementById("gaRas").checked,
		alignment: document.getElementById("alignment").checked,
	};
}

function saveSettingsToSession() {
	var s = getSidebarSettings();
	var fd = new FormData();
	fd.append("skrutable_action", currentAction);
	fd.append("from_scheme", s.from_scheme);
	fd.append("to_scheme", s.to_scheme);
	fd.append("resplit_option", s.resplit_option);
	fd.append("splitter_model", s.splitter_model);
	fd.append("preserve_punctuation", currentPreservePunctuation);
	fd.append("preserve_compound_hyphens", currentPreserveCompoundHyphens);
	if (s.weights) fd.append("scan_detail", "weights");
	if (s.morae) fd.append("scan_detail", "morae");
	if (s.gaRas) fd.append("scan_detail", "gaRas");
	if (s.alignment) fd.append("scan_detail", "alignment");
	fetch("/api/save-settings", { method: "POST", body: fd });
}

function syncHiddenInputs() {
	var s = getSidebarSettings();
	document.getElementById("hidden_action").value = currentAction;
	document.getElementById("hidden_from_scheme").value = s.from_scheme;
	document.getElementById("hidden_to_scheme").value = s.to_scheme;
	document.getElementById("hidden_resplit_option").value = s.resplit_option;
	document.getElementById("hidden_splitter_model").value = s.splitter_model;
	document.getElementById("hidden_preserve_punctuation").value = currentPreservePunctuation;
	document.getElementById("hidden_preserve_compound_hyphens").value = currentPreserveCompoundHyphens;

	var container = document.getElementById("hidden_scan_detail_container");
	container.innerHTML = "";
	["weights", "morae", "gaRas", "alignment"].forEach(function(id) {
		if (document.getElementById(id).checked) {
			var inp = document.createElement("input");
			inp.type = "hidden";
			inp.name = "scan_detail";
			inp.value = id;
			container.appendChild(inp);
		}
	});
}

function swapSchemeSelects() {
	var from = document.getElementById("from_scheme");
	var to = document.getElementById("to_scheme");
	if (to.value !== "IASTREDUCED") {
		var tmp = from.value;
		from.value = to.value;
		to.value = tmp;
	}
}

function onInputToggle(mode) {
	var textBtn = document.getElementById("toggle_text");
	var fileBtn = document.getElementById("toggle_file");
	var fileButtons = document.getElementById("file_input_buttons");
	if (mode === "file") {
		textBtn.classList.remove("active");
		fileBtn.classList.add("active");
		fileButtons.style.display = "";
	} else {
		fileBtn.classList.remove("active");
		textBtn.classList.add("active");
		fileButtons.style.display = "none";
		// On upload page, navigate back to workbench
		if (window.location.pathname === "/upload_file") {
			window.location.href = "/";
		}
	}
}

function initSidebarFromSession(config) {
	if (config.from_scheme) document.getElementById("from_scheme").value = config.from_scheme;
	if (config.to_scheme) document.getElementById("to_scheme").value = config.to_scheme;
	if (config.resplit_option) document.getElementById("resplit_option").value = config.resplit_option;
	if (config.splitter_model) document.getElementById("splitter_model_sidebar").value = config.splitter_model;
	if (config.weights !== undefined) document.getElementById("weights").checked = config.weights;
	if (config.morae !== undefined) document.getElementById("morae").checked = config.morae;
	if (config.gaRas !== undefined) document.getElementById("gaRas").checked = config.gaRas;
	if (config.alignment !== undefined) document.getElementById("alignment").checked = config.alignment;
}
