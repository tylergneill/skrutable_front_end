import logging
import os
import re
import requests
import sys
import tempfile
import time
from urllib.parse import quote
from datetime import datetime, date
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, Request, session, send_from_directory, \
	make_response, g, url_for
from requests.exceptions import HTTPError
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadGateway, RequestEntityTooLarge

from ocr_service import run_google_ocr

from skrutable import __version__ as BACK_END_VERSION
from skrutable.transliteration import Transliterator
from skrutable.scansion import Scanner
from skrutable.meter_identification import MeterIdentifier
from skrutable.meter_patterns import meter_melodies
from skrutable.splitting import Splitter

# overcome issue with Werkzeug 3.1 where max_form_memory_size default 500 KB causes 413 Request Entity Too Large

MAX_CONTENT_LENGTH_MB = 128
MB_SIZE = 1024 * 1024

class CustomRequest(Request):
    max_form_memory_size = MAX_CONTENT_LENGTH_MB * MB_SIZE

class CustomFlask(Flask):
    request_class = CustomRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = CustomFlask(__name__)
app.config["DEBUG"] = True
app.config["SECRET_KEY"] = "asdlkvumnxlapoiqyernxnfjtuzimzjdhryien" # for session, no actual need for secrecy
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH_MB * MB_SIZE

# for serving static files from assets folder
@app.route('/assets/<path:name>')
def serve_files(name):
	return send_from_directory('assets', name)

# Skrutable main objects
T = Transliterator()
S = Scanner()
MI = MeterIdentifier()
Spl = Splitter()

# --- Pure helper functions (no session, no g, no Flask) ---

def do_transliterate(input_text, from_scheme, to_scheme, avoid_virama_indic_scripts=True):
	return T.transliterate(
		input_text,
		from_scheme=from_scheme,
		to_scheme=to_scheme,
		avoid_virama_indic_scripts=avoid_virama_indic_scripts,
	)

def do_scan(input_text, from_scheme, show_weights, show_morae, show_gaRas, show_alignment):
	V = S.scan(input_text, from_scheme=from_scheme)
	return V.summarize(
		show_weights=show_weights,
		show_morae=show_morae,
		show_gaRas=show_gaRas,
		show_alignment=show_alignment,
		show_label=False,
	)

def do_identify_meter(input_text, from_scheme, resplit_option, show_weights, show_morae, show_gaRas, show_alignment):
	"""Returns (summary_text, meter_label_hk, melody_options_list)."""
	r_o, r_k_m = parse_complex_resplit_option(resplit_option)
	V = MI.identify_meter(
		input_text,
		resplit_option=r_o,
		resplit_keep_midpoint=r_k_m,
		from_scheme=from_scheme,
	)
	summary = V.summarize(
		show_weights=show_weights,
		show_morae=show_morae,
		show_gaRas=show_gaRas,
		show_alignment=show_alignment,
		show_label=True,
	)
	short_meter_label = V.meter_label[:V.meter_label.find(' ')]
	if short_meter_label in meter_melodies:
		meter_label_hk = T.transliterate(short_meter_label, from_scheme='IAST', to_scheme='HK')
		melody_options_list = meter_melodies[short_meter_label]
	else:
		meter_label_hk = ""
		melody_options_list = []
	return summary, meter_label_hk, melody_options_list, V

def do_split(input_text, from_scheme, to_scheme, splitter_model="dharmamitra_2024_sept",
			 preserve_compound_hyphens=True, preserve_punctuation=True, avoid_virama_indic_scripts=True):
	IAST_input = T.transliterate(input_text, from_scheme=from_scheme, to_scheme='IAST')
	split_result = Spl.split(
		IAST_input,
		splitter_model=splitter_model,
		preserve_compound_hyphens=preserve_compound_hyphens,
		preserve_punctuation=preserve_punctuation,
	)
	result = T.transliterate(
		split_result,
		from_scheme='IAST',
		to_scheme=to_scheme,
		avoid_virama_indic_scripts=avoid_virama_indic_scripts,
	)
	# TODO: Remove once 2018 splitter server restored
	if split_result.startswith("The server for the 2018 model is temporarily down"):
		result = split_result
	return result

# variable names for flask.session() object
SELECT_ELEMENT_NAMES = [
	"skrutable_action",
	"from_scheme", "to_scheme",
	"resplit_option",
	]
CHECKBOX_ELEMENT_NAMES = [
	"weights", "morae", "gaRas",
	"alignment",
	]
melody_variable_names = [
	"meter_label", "melody_options"
	]
extra_option_names = [
	"avoid_virama_indic_scripts",
	# "avoid_virama_non_indic_scripts",  # TODO: enable later
	# "include_single_pada",  # TODO: enable later
	"preserve_compound_hyphens",
	"preserve_punctuation",
	"splitter_model",
]
SESSION_VARIABLE_NAMES = (
	SELECT_ELEMENT_NAMES +
	CHECKBOX_ELEMENT_NAMES +
	melody_variable_names +
	extra_option_names
	)

def find_front_end_version():
	base_dir = os.path.dirname(os.path.abspath(__file__))
	version_file_path = os.path.join(base_dir, 'VERSION')
	with open(version_file_path, 'r', encoding='utf8') as file:
		# Assuming the __version__ line is the first line
		return file.readline().strip().split('=')[1].strip().replace("'", "").replace('"', '')

FRONT_END_VERSION = find_front_end_version()

# for updating session variables and input
def process_form(form):

	# get text input
	g.text_input = form.get('text_input', '')

	# first do values of "select" elements (i.e. dropdowns)
	for var_name in SELECT_ELEMENT_NAMES:
		# print(var_name, request.form[var_name])
		session[var_name] = form[var_name]

	# then do values of "checkbox" elements for scansion detail
	scan_detail_option_choices = request.form.getlist("scan_detail")
	for var_name in CHECKBOX_ELEMENT_NAMES:
		if var_name in scan_detail_option_choices:
			session[var_name] = 1
		else:
			session[var_name] = 0

	# extra options passed as hidden inputs from JS/localStorage
	for var_name in extra_option_names:
		if var_name in form:
			val = form[var_name]
			if val in ("true", "True", "1"):
				session[var_name] = 1
			elif val in ("false", "False", "0"):
				session[var_name] = 0
			else:
				session[var_name] = val

	session.modified = True

# for meter-id resplit option, which has two parts
def parse_complex_resplit_option(complex_resplit_option):
	if complex_resplit_option.endswith('_keep_mid'):
		resplit_keep_midpoint = True
		resplit_option = complex_resplit_option[:-len('_keep_mid')]
	else:
		resplit_keep_midpoint = False
		resplit_option = complex_resplit_option
	return resplit_option, resplit_keep_midpoint

def _init_session_defaults():
	"""Set all session keys to their defaults (used by upload_file flow)."""
	defaults = {
		"skrutable_action": "",
		"from_scheme": "IAST", "to_scheme": "IAST",
		"weights": 1, "morae": 1, "gaRas": 1, "alignment": 1,
		"resplit_option": "resplit_lite_keep_mid",
		"meter_label": "", "melody_options": [],
		"avoid_virama_indic_scripts": 1,
		"preserve_compound_hyphens": 1,
		"preserve_punctuation": 1,
		"splitter_model": "dharmamitra_2024_sept",
	}
	for k, v in defaults.items():
		session.setdefault(k, v)
	session.modified = True

def ensure_keys():
	# just in case, make sure all keys in session
	for var_name in SESSION_VARIABLE_NAMES:
		if var_name not in session:
			_init_session_defaults()
			return

@app.errorhandler(413)
def request_entity_too_large(error):
	if request.path.startswith('/api/') and \
			request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
		return jsonify({"error": str(error)}), 413
	return render_template('errors/413.html', max_size=MAX_CONTENT_LENGTH_MB), 413

@app.errorhandler(415)
def unsupported_media_type(error):
	if request.path.startswith('/api/'):
		return jsonify({"error": "Received neither form nor json input."}), 415
	return str(error), 415

@app.errorhandler(500)
def internal_server_error(error):
	context = {
		'path': request.path,
		'method': request.method,
	}

	if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
		return jsonify({"error": "Internal server error"}), 500
	return render_template('errors/500.html', **context), 500

@app.errorhandler(502)
def bad_gateway_error(error):
	context = {
		'path': request.path,
		'method': request.method,
	}

	if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
		return jsonify({"error": "Bad gateway"}), 502
	return render_template('errors/502.html', **context), 502

MAIN_DEFAULTS = {
	"skrutable_action": "",
	"from_scheme": "IAST",
	"to_scheme": "IAST",
	"weights": 1,
	"morae": 1,
	"gaRas": 1,
	"alignment": 1,
	"resplit_option": "resplit_lite_keep_mid",
	"meter_label": "",
	"melody_options": [],
}

@app.route("/", methods=["GET"])
def index():

	ensure_keys()

	# Build template vars from session, falling back to MAIN_DEFAULTS
	session_kwargs = {k: session.get(k, MAIN_DEFAULTS.get(k)) for k in MAIN_DEFAULTS}
	# Also include extra settings from session
	for k in extra_option_names:
		if k in session:
			session_kwargs[k] = session[k]

	example_num = request.args.get("example")
	if example_num and example_num in EXAMPLES:
		ex = EXAMPLES[example_num]
		return render_template(
			'main.html',
			text_input=ex["text_input"],
			text_output=ex["text_output"],
			**{**session_kwargs, **{k: ex[k] for k in ex if k in MAIN_DEFAULTS}},
		)
	return render_template(
		'main.html',
		text_input="",
		text_output="",
		**session_kwargs,
	)


@app.route("/upload_file", methods=["GET", "POST"])
def upload_file():

	ensure_keys()

	# GET: display upload form with current session settings
	if request.method == "GET":
		session_kwargs = {k: session[k] for k in session if k in SESSION_VARIABLE_NAMES}
		return render_template(
			"upload_file.html",
			**session_kwargs,
		)

	# POST from main page sidebar: save settings, redirect to GET
	if request.form and not request.files:
		process_form(request.form)
		return redirect(url_for("upload_file"))

	# POST with file: process and return download
	if request.files:

		# sync sidebar settings into session
		if request.form:
			process_form(request.form)

		# take in and read file
		input_file = request.files["input_file"]
		input_fn = input_file.filename
		input_data = input_file.stream.read().decode('utf-8')
		g.text_input = input_data

		# carry out chosen action

		if session["skrutable_action"] == "transliterate":

			output_data = do_transliterate(
				input_data,
				from_scheme=session["from_scheme"],
				to_scheme=session["to_scheme"],
				avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
			)
			output_fn_suffix = '_transliterated'

		elif session["skrutable_action"] == "identify meter":

			starting_time = datetime.now().time()

			verses = input_data.splitlines() # during post \n >> \r\n
			output_data = ''
			for verse in verses:

				summary, meter_label_hk, melody_options_list, V = do_identify_meter(
					verse,
					from_scheme=session['from_scheme'],
					resplit_option=session["resplit_option"],
					show_weights=session["weights"],
					show_morae=session["morae"],
					show_gaRas=session["gaRas"],
					show_alignment=session["alignment"],
				)

				output_data += V.text_raw + '\n\n' + summary + '\n'

			ending_time = datetime.now().time()

			delta = datetime.combine(date.today(), ending_time) - datetime.combine(date.today(), starting_time)
			duration_secs = delta.seconds + delta.microseconds / 1000000
			output_data += "samāptam: %d padyāni, %f kṣaṇāḥ" % ( len(verses), duration_secs )

			output_fn_suffix = '_meter_identified'

		elif session["skrutable_action"] == "split":

			try:
				output_data = do_split(
					input_data,
					from_scheme=session["from_scheme"],
					to_scheme=session["to_scheme"],
					splitter_model=session["splitter_model"],
					preserve_compound_hyphens=session["preserve_compound_hyphens"],
					preserve_punctuation=session["preserve_punctuation"],
					avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
				)
			except HTTPError as e:
				status = e.response.status_code if e.response is not None else 502
				if status == 413:
					raise BadGateway("Upstream service returned 413 Request Entity Too Large")
					# TODO: have Skrutable backend handle batching to relieve burden on upstream server
				else:
					raise BadGateway(f"Upstream splitting service returned {status}. "
						"The service may be temporarily unavailable.")

			output_fn_suffix = '_split'

		# prepare and return output file

		stem, _, ext = input_fn.rpartition('.')
		if not stem:
			stem, ext = ext, 'txt'
		output_fn = f"{stem}{output_fn_suffix}.{ext}"

		# ASCII fallback for Content-Disposition, plus RFC 5987 filename* for UTF-8
		ascii_fn = secure_filename(output_fn) or f"skrutable_result{output_fn_suffix}.{ext}"
		utf8_fn = quote(output_fn)

		response = make_response(output_data)
		response.headers["Content-Disposition"] = (
			f"attachment; filename=\"{ascii_fn}\"; filename*=UTF-8''{utf8_fn}"
		)
		return response

@app.route("/ocr", methods=["GET", "POST"])
def ocr():
	if request.method == "GET":
		return render_template("ocr.html", max_size=MAX_CONTENT_LENGTH_MB)

	# Log detailed job stats to learn about usage
	ip = request.headers.get('X-Forwarded-For', request.remote_addr)
	logger.info("Client IP: %s", ip)
	try:
		geo = requests.get(f"http://ip-api.com/json/{ip}?fields=country,regionName,city,query").json()
		logger.info("Geo info %s:", geo)
	except Exception as e:
		logger.error("Geo lookup failed: %s", e)
	start_time = time.time()
	logger.info("Received OCR request at %s", start_time)
	logger.info("Request method: %s", request.method)
	logger.info("Request content-type: %s", request.content_type)
	logger.info("Request content length: %s", request.content_length)
	if 'pdf_file' in request.files:
		f = request.files.get("pdf_file")
		logger.info("Filename: %s", f.filename)
		logger.info("MIME: %s", f.mimetype)
		logger.info("Size (bytes): %s", len(f.read()))
		f.seek(0)
	else:
		logger.error("No file in request.files")

	# ---------- POST ----------
	api_key   = request.form.get("google_api_key", "").strip()
	pdf_file  = request.files.get("pdf_file")

	include_page_numbers = request.form.get("include_page_numbers") == "yes"

	if not api_key or not pdf_file:
		return "PDF and API key are required.", 400

	with tempfile.TemporaryDirectory() as td:
		pdf_path = Path(td) / secure_filename(pdf_file.filename)
		pdf_file.save(pdf_path)

		try:
			ocr_text = run_google_ocr(pdf_path, api_key, include_page_numbers)
		except Exception as exc:
			import traceback
			trace = traceback.format_exc()
			logger.error("OCR failed: %s", exc)
			logger.error("trace: %s", trace)
			return f"OCR failed: {exc}\n\n{trace}", 500

	response = make_response(ocr_text)
	response.headers["Content-Type"] = "text/plain; charset=utf-8"

	if request.form.get("display_inline") != "yes":
		response.headers["Content-Disposition"] = "attachment; filename=ocr_output.txt"

	end_time = time.time()
	logger.info("Completed OCR request at %s", end_time)
	elapsed = end_time - start_time
	logger.info("Total OCR roundtrip time: %.3f seconds", elapsed)

	return response

@app.route("/ocr_instructions")
def ocr_instructions():
    return render_template("ocr_instructions.html", max_size=MAX_CONTENT_LENGTH_MB)

@app.route('/api', methods=["GET"])
def api_landing():
	return render_template("api.html",
		back_end_version=BACK_END_VERSION,
		front_end_version=FRONT_END_VERSION,
	)

def _coerce_bool(value):
	"""Convert string booleans to real booleans, pass through others."""
	if isinstance(value, str):
		if value.lower() == 'true':
			return True
		elif value.lower() == 'false':
			return False
	return value

def api_response(result_text, **extra_fields):
	"""Content-negotiate: JSON if Accept header requests it, plain text otherwise."""
	if "application/json" in (request.headers.get("Accept") or ""):
		payload = {"result": result_text, **extra_fields}
		return jsonify(payload)
	return result_text

def get_inputs(required_args, request, optional_args=None):

	if required_args[0] != "input_text":
		return "The variable input_text should always be first in required_arg_list"

	json_data = request.get_json(silent=True)
	if not (request.form or json_data):
		return "Received neither form nor json input."

	data_source = dict(request.form or json_data)
	error_msg = (
		"Couldn't get all fields:\n" +
		f"required_args: {required_args}\n" +
		f"request.files {request.files}\n" +
  		"data_source (" + ("json" if json_data else "form") + f") {data_source}"
	)

	try:
		if request.files:
			input_file = request.files["input_file"]
			if input_file.content_length and input_file.content_length > MAX_CONTENT_LENGTH_MB * MB_SIZE:
				raise RequestEntityTooLarge(f"Upload exceeds {MAX_CONTENT_LENGTH_MB} MB limit")
			input_text = input_file.stream.read().decode('utf-8')
		else: # should all be in either form or json
			input_text = data_source["input_text"]
	except:
		return error_msg

	inputs = {"input_text": input_text}

	for arg in required_args[1:]:

		if arg not in data_source:
			return error_msg

		inputs[arg] = _coerce_bool(data_source[arg])

	# optional args: use default if not provided
	if optional_args:
		for arg, default in optional_args.items():
			if arg in data_source:
				inputs[arg] = _coerce_bool(data_source[arg])
			else:
				inputs[arg] = default

	return inputs

@app.route('/api/save-settings', methods=["POST"])
def api_save_settings():
	ensure_keys()
	form = request.form
	for var_name in extra_option_names:
		if var_name in form:
			val = form[var_name]
			if val in ("true", "True", "1"):
				session[var_name] = 1
			elif val in ("false", "False", "0"):
				session[var_name] = 0
			else:
				session[var_name] = val
	session.modified = True
	return jsonify({"ok": True})

@app.route('/api/transliterate', methods=["GET", "POST"])
def api_transliterate():

	# assume that GET request is person surfing in browser
	if request.method == "GET":
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": "This endpoint accepts POST requests only."}), 405
		return render_template("errors/POSTonly.html")

	inputs = get_inputs(
		["input_text", "from_scheme", "to_scheme"],
		request,
		optional_args={"avoid_virama_indic_scripts": True},
	)
	if isinstance(inputs, str):
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": inputs}), 400
		return inputs # == error_msg

	result = do_transliterate(
		inputs["input_text"],
		from_scheme=inputs["from_scheme"],
		to_scheme=inputs["to_scheme"],
		avoid_virama_indic_scripts=inputs["avoid_virama_indic_scripts"],
	)
	return api_response(result)

@app.route('/api/scan', methods=["GET", "POST"])
def api_scan():

	if request.method == "GET":
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": "This endpoint accepts POST requests only."}), 405
		return render_template("errors/POSTonly.html")

	inputs = get_inputs(
		[	"input_text",
			"from_scheme",
			"show_weights",
			"show_morae",
			"show_gaRas",
			"show_alignment"
		],
		request
	)
	if isinstance(inputs, str):
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": inputs}), 400
		return inputs # == error_msg

	result = do_scan(
		inputs["input_text"],
		from_scheme=inputs["from_scheme"],
		show_weights=inputs["show_weights"],
		show_morae=inputs["show_morae"],
		show_gaRas=inputs["show_gaRas"],
		show_alignment=inputs["show_alignment"],
	)

	return api_response(result)

@app.route('/api/identify-meter', methods=["GET", "POST"])
def api_identify_meter():

	if request.method == "GET":
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": "This endpoint accepts POST requests only."}), 405
		return render_template("errors/POSTonly.html")

	inputs = get_inputs(
		[	"input_text",
			"from_scheme",
			"show_weights",
			"show_morae",
			"show_gaRas",
			"show_alignment",
			"resplit_option"
		],
		request
	)

	if isinstance(inputs, str):
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": inputs}), 400
		return inputs # == error_msg

	summary, meter_label_hk, melody_options_list, V = do_identify_meter(
		inputs["input_text"],
		from_scheme=inputs["from_scheme"],
		resplit_option=inputs["resplit_option"],
		show_weights=inputs["show_weights"],
		show_morae=inputs["show_morae"],
		show_gaRas=inputs["show_gaRas"],
		show_alignment=inputs["show_alignment"],
	)

	return api_response(summary, meter_label=meter_label_hk, melody_options=melody_options_list)


@app.route('/api/split', methods=["GET", "POST"])
def api_split():

	if request.method == "GET":
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": "This endpoint accepts POST requests only."}), 405
		return render_template("errors/POSTonly.html")

	inputs = get_inputs(
		["input_text", "from_scheme", "to_scheme"],
		request,
		optional_args={
			"splitter_model": "dharmamitra_2024_sept",
			"preserve_compound_hyphens": True,
			"preserve_punctuation": True,
			"avoid_virama_indic_scripts": True,
		},
	)

	if isinstance(inputs, str):
		if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
			return jsonify({"error": inputs}), 400
		return inputs # == error_msg

	try:
		result = do_split(
			inputs["input_text"],
			from_scheme=inputs["from_scheme"],
			to_scheme=inputs["to_scheme"],
			splitter_model=inputs["splitter_model"],
			preserve_compound_hyphens=inputs["preserve_compound_hyphens"],
			preserve_punctuation=inputs["preserve_punctuation"],
			avoid_virama_indic_scripts=inputs["avoid_virama_indic_scripts"],
		)
	except HTTPError as e:
		status = e.response.status_code if e.response is not None else 502
		model = inputs["splitter_model"]
		return jsonify({"error": f"Upstream splitting service ({model}) returned {status}. "
			"The service may be temporarily unavailable. "
			"You can try again later or switch to a different splitter model in Settings."}), 502

	return api_response(result)


@app.route('/reset')
def reset_variables():
	session.clear()
	return redirect("/")

# Example data (used both server-side and passed to JS)
EXAMPLES = {
	"1": {
		"text_input": "dharmakṣetre kurukṣetre samavetā yuyutsavaḥ /\nmāmakāḥ pāṇḍavāś caiva kim akurvata sañjaya //",
		"text_output": "धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः /\nमामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय //",
		"from_scheme": "IAST", "to_scheme": "DEV",
		"skrutable_action": "transliterate",
		"meter_label": "", "melody_options": [],
	},
	"2": {
		"text_input": "धात्वर्थं बाधते कश्चित् कश्चित् तमनुवर्तते |\nतमेव विशिनष्ट्यन्य उपसर्गगतिस्त्रिधा ||",
		"text_output": "gggglggl    {m: 14}    [8: mrgl]\ngglllglg    {m: 12}    [8: tslg]\nlglllggl    {m: 11}    [8: jsgl]\nllgllglg    {m: 11}    [8: sslg]\n\n    dhā    tva  rthaṃ     bā    dha     te     ka    ści\n      g      g      g      g      l      g      g      l\n    tka    ści    tta     ma     nu     va    rta     te\n      g      g      l      l      l      g      l      g\n     ta     me     va     vi     śi     na   ṣṭya    nya\n      l      g      l      l      l      g      g      l\n      u     pa     sa    rga     ga     ti   stri    dhā\n      l      l      g      l      l      g      l      g\n\nanuṣṭubh (1,2: pathyā, 3,4: pathyā)",
		"from_scheme": "DEV", "to_scheme": "IAST",
		"skrutable_action": "identify meter",
		"meter_label": "anuSTubh",
		"melody_options": ["Madhura Godbole", "H.V. Nagaraja Rao", "Shatavadhani Ganesh", "Diwakar Acarya"],
	},
	"3": {
		"text_input": "तव करकमलस्थां स्फाटिकीमक्षमालां , नखकिरणविभिन्नां दाडिमीबीजबुद्ध्या |\nप्रतिकलमनुकर्षन्येन कीरो निषिद्धः , स भवतु मम भूत्यै वाणि ते मन्दहासः ||",
		"text_output": "tava kara kamala sthām sphāṭikīm akṣa mālām , nakha kiraṇa vibhinnām dāḍimī bīja buddhyā |\npratikalam anukarṣan yena kīraḥ niṣiddhaḥ , sa bhavatu mama bhūtyai vāṇi te manda hāsaḥ ||",
		"from_scheme": "DEV", "to_scheme": "IAST",
		"skrutable_action": "split",
		"meter_label": "",
		"melody_options": [],
	},
}

# Backward-compat redirects for old example URLs
@app.route('/ex1')
def ex1():
	return redirect("/?example=1")

@app.route('/ex2')
def ex2():
	return redirect("/?example=2")

@app.route('/ex3')
def ex3():
	return redirect("/?example=3")

@app.route('/about')
def about_page():
	return render_template(
		"about.html",
		back_end_version=BACK_END_VERSION,
		front_end_version=FRONT_END_VERSION,
	)

@app.route('/help')
def help_page():
	return render_template("help.html")

@app.route('/upload_file_help')
def upload_file_help_page():
	return render_template("upload_file_help.html")

@app.route('/settings')
def settings_page():
	ensure_keys()
	session_kwargs = {k: session[k] for k in extra_option_names if k in session}
	return render_template("settings.html", **session_kwargs)

@app.route('/updates')
def updates_page():
	return render_template("updates.html")

@app.route('/scanGRETIL')
def scanGRETIL_page():
	return render_template("scanGRETIL.html")

@app.route('/scanGRETILresults')
def scanGRETILresults_page():
	return render_template(	"scanGRETILresults.html",
		parent_dir = "https://raw.githubusercontent.com/tylergneill/skrutable_front_end/main/assets/meter_analyses/",
		dir1 = "1_input_raw",
		dir2 = "2_input_cleaned",
		dir3 = "3_output_raw",
		dir4 = "4_output_cleaned",
		dir5 = "5_tallies",
		dir6 = "6_notes"
		)

@app.route('/reciters')
def reciters_page():
	return render_template("reciters.html")

def prep_Apte_query(IAST_string):
	dev_query = T.transliterate(IAST_string, from_scheme='IAST', to_scheme='DEV')
	while dev_query[-1] == chr(0x94d): dev_query = dev_query[:-1] # remove final Devanagari virāma(s) (U+094d)
	chicago_url = "https://dsal.uchicago.edu/cgi-bin/app/apte_query.py?qs=%s&searchhws=yes&matchtype=default" % dev_query
	return chicago_url

@app.route('/ChicagoApteIAST') # hidden endpoint
def chicago_apte_iast():
	iast_query = request.args.get('query')
	chicago_url = prep_Apte_query(iast_query)
	return redirect(chicago_url)

if __name__ == '__main__':
    app.run(debug=True, port=5012)