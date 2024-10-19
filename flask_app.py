import os
import re
import unicodedata

from datetime import datetime, date
from flask import Flask, redirect, render_template, request, url_for, session, send_from_directory, make_response, g
from requests.exceptions import HTTPError
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadGateway

from skrutable import __version__ as BACK_END_VERSION
from skrutable.transliteration import Transliterator
from skrutable.scansion import Scanner
from skrutable.meter_identification import MeterIdentifier
from skrutable.meter_patterns import meter_melodies
from skrutable.splitting import Splitter

app = Flask(__name__)
app.config["DEBUG"] = True
app.config["SECRET_KEY"] = "asdlkvumnxlapoiqyernxnfjtuzimzjdhryien" # for session, no actual need for secrecy
MAX_CONTENT_LENGTH_MB = 64
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH_MB * 1024 * 1024

# for serving static files from assets folder
@app.route('/assets/<path:name>')
def serve_files(name):
	return send_from_directory('assets', name)

# this helps app work both publicly (e.g. on Digital Ocean) and locally
CURRENT_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Skrutable main objects
T = Transliterator()
S = Scanner()
MI = MeterIdentifier()
Spl = Splitter()

# variable names for flask.session() object
SELECT_ELEMENT_NAMES = [
	"skrutable_action",
	"from_scheme", "to_scheme",
	"resplit_option",
	]
CHECKBOX_ELEMENT_NAMES = [
	"weights", "morae", "gaRas",
	"alignment",
	] # to be extended with corpus text abbreviations for textPrioritize
melody_variable_names = [
	"meter_label", "melody_options"
	]
EXTRA_OPTION_NAMES = [
	"avoid_virama_indic_scripts",
	# "avoid_virama_non_indic_scripts",  # TODO: enable later
	# "include_single_pada",  # TODO: enable later
	"preserve_compound_hyphens",
	"preserve_punctuation",
	"splitter_model",
	"is_input_xml",
]
SESSION_VARIABLE_NAMES = (
	SELECT_ELEMENT_NAMES +
	CHECKBOX_ELEMENT_NAMES +
	melody_variable_names +
	EXTRA_OPTION_NAMES
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

	# then do values of "checkbox" elements
	scan_detail_option_choices = form.getlist("scan_detail")
	true_checkboxes = scan_detail_option_choices
	for var_name in CHECKBOX_ELEMENT_NAMES:
		if var_name in true_checkboxes:
			session[var_name] = 1
		else:
			session[var_name] = 0

	session.modified = True

def process_settings_form(form):
	session['avoid_virama_indic_scripts'] = int(form.get('avoid_virama_indic_scripts', None) is not None)
	# session['include_single_pada'] = int(form.get('include_single_pada', None) is not None)  # TODO: enable later
	session['preserve_punctuation'] = int(form.get('preserve_punctuation', None) is not None)
	session['preserve_compound_hyphens'] = int(form.get('preserve_compound_hyphens', None) is not None)
	session['splitter_model'] = form.get('splitter_model', 'dharmamitra_2024_sept')
	session['is_input_xml'] = int(form.get('is_input_xml', None) is not None)
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

def ensure_keys():
	# just in case, make sure all keys in session
	for var_name in SESSION_VARIABLE_NAMES:
		if var_name not in session:
			reset_variables()

@app.errorhandler(413)
def request_entity_too_large(error):
	return render_template('errors/413.html', max_size=MAX_CONTENT_LENGTH_MB), 413

@app.errorhandler(500)
def internal_server_error(error):
	user_session_data = {k: session.get(k) for k in SESSION_VARIABLE_NAMES}
	text_input = g.get("text_input") or ""
	text_output = g.get("text_output") or ""

	context = {
		'path': request.path,
		'method': request.method,
		'text_input_length': len(text_input),
		'text_output_length': len(text_output),
		'text_input': text_input[:1000] + '...' if len(text_input) > 1000 else text_input,
		'text_output': text_output[:1000] + '...' if len(text_output) > 1000 else text_output,
		'user_session_data': user_session_data
	}

	return render_template('errors/500.html', **context), 500

@app.errorhandler(502)
def bad_gateway_error(error):
	user_session_data = {k: session.get(k) for k in SESSION_VARIABLE_NAMES}
	text_input = g.get("text_input") or ""
	text_output = g.get("text_output") or ""

	context = {
		'path': request.path,
		'method': request.method,
		'text_input_length': len(text_input),
		'text_output_length': len(text_output),
		'text_input': text_input[:1000] + '...' if len(text_input) > 1000 else text_input,
		'text_output': text_output[:1000] + '...' if len(text_output) > 1000 else text_output,
		'user_session_data': user_session_data
	}

	return render_template('errors/502.html', **context), 502

@app.route("/", methods=["GET", "POST"])
def index():

	ensure_keys()

	if request.method == "GET":
		session["skrutable_action"] = "..."
		session.modified = True
		return render_template(
			'main.html',
			text_input="",
			text_output="",
			**{k: session[k] for k in session if k in SESSION_VARIABLE_NAMES},
		)

	elif request.method == "POST":

		process_form(request.form)

		# carry out chosen action
		if session["skrutable_action"] == "transliterate":

			g.text_output = T.transliterate(
				g.text_input,
				from_scheme=session["from_scheme"],
				to_scheme=session["to_scheme"],
				avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
				is_input_xml=session["is_input_xml"],
				)

			session["meter_label"] = ""; session["melody_options"] = [] # cancel these

		elif session["skrutable_action"] == "scan":

			V = S.scan(
				g.text_input,
				from_scheme=session["from_scheme"]
				)

			g.text_output = V.summarize(
				show_weights=session["weights"],
				show_morae=session["morae"],
				show_gaRas=session["gaRas"],
				show_alignment=session["alignment"],
				show_label=False
				)

			session["meter_label"] = ""; session["melody_options"] = [] # cancel these

		elif session["skrutable_action"] == "identify meter":

			r_o, r_k_m = parse_complex_resplit_option(
				complex_resplit_option=session["resplit_option"]
				)

			V = MI.identify_meter(
				g.text_input,
				resplit_option=r_o,
				resplit_keep_midpoint=r_k_m,
				from_scheme=session["from_scheme"]
				)

			g.text_output = V.summarize(
				show_weights=session["weights"],
				show_morae=session["morae"],
				show_gaRas=session["gaRas"],
				show_alignment=session["alignment"],
				show_label=True
				)

			short_meter_label = V.meter_label[:V.meter_label.find(' ')]
			if short_meter_label in meter_melodies:
				session["meter_label"] = T.transliterate(
					short_meter_label,
					from_scheme='IAST',
					to_scheme='HK',
					)
				session["melody_options"] = meter_melodies[ short_meter_label ]
			else:
				session["meter_label"] = ""; session["melody_options"] = [] # cancel these

		elif session["skrutable_action"] == "split":

			IAST_input = T.transliterate(
				g.text_input,
				from_scheme=session["from_scheme"],
				to_scheme='IAST',
				is_input_xml=session["is_input_xml"],
				)

			split_result = Spl.split(
				IAST_input,
				splitter_model=session["splitter_model"],
				preserve_compound_hyphens=session['preserve_compound_hyphens'],
				preserve_punctuation=session['preserve_punctuation'],
				is_input_xml=session["is_input_xml"],
				)

			g.text_output = T.transliterate(
				split_result,
				from_scheme='IAST',
				to_scheme=session["to_scheme"],
				avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
				is_input_xml=session["is_input_xml"],
				)

			# TODO: Remove once 2018 splitter server restored
			if split_result.startswith("The server for the 2018 model is temporarily down"):
				g.text_output = split_result

			session["meter_label"] = ""; session["melody_options"] = [] # cancel these

		elif session["skrutable_action"] == "apte links":

			session["meter_label"] = ""; session["melody_options"] = [] # cancel these

			output_HTML = prep_split_output_for_Apte(g.text_input) # must already be split
			return render_template(
				"main_HTML_output.html",
				text_input=g.text_input,
				output_HTML=output_HTML,
				**{k: session[k] for k in session if k in SESSION_VARIABLE_NAMES},
			)

		session.modified = True

		return render_template(
			'main.html',
			text_input=g.text_input,
			text_output=g.text_output,
			**{k: session[k] for k in session if k in SESSION_VARIABLE_NAMES},
		)


@app.route("/whole_file", methods=["POST"])
def whole_file():

	ensure_keys()

	# when form sent from GUI ("whole file" button clicked)
	if request.form != {}:

		process_form(request.form)

		# use bool values for clearer display
		session_kwargs = {k: session[k] for k in session if k in SESSION_VARIABLE_NAMES}
		for k,v in session_kwargs.items():
			if v in [0, 1]:
				session_kwargs[k] = bool(v)

		# send onward to upload form
		return render_template(
			"whole_file.html",
			text_input=g.text_input,
			**session_kwargs,
		)

	# when file chosen for upload
	elif request.files != {}:

		# session variables already processed in previous step

		# take in and read file
		input_file = request.files["input_file"]
		input_fn = input_file.filename
		input_data = input_file.stream.read().decode('utf-8')
		g.text_input = input_data

		# carry out chosen action

		if session["skrutable_action"] == "transliterate":

			output_data = T.transliterate(
				input_data,
				from_scheme=session["from_scheme"],
				to_scheme=session["to_scheme"],
				avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
				is_input_xml=session["is_input_xml"],
				)

			output_fn_suffix = '_transliterated'

		elif session["skrutable_action"] == "identify meter":

			r_o, r_k_m = parse_complex_resplit_option(
				complex_resplit_option=session["resplit_option"],
				)

			# record starting time

			starting_time = datetime.now().time()

			verses = input_data.splitlines() # during post \n >> \r\n
			output_data = ''
			for verse in verses:

				result = MI.identify_meter(
					verse,
					resplit_option=r_o,
					resplit_keep_midpoint=r_k_m,
					from_scheme=session['from_scheme']
					)

				output_data += (
					result.text_raw + '\n\n' +
					result.summarize(
						show_weights=session["weights"],
						show_morae=session["morae"],
						show_gaRas=session["gaRas"],
						show_alignment=session["alignment"],
						show_label=True
						) +
					'\n'
					)

			# record ending time
			ending_time = datetime.now().time()

			# report total duration
			delta = datetime.combine(date.today(), ending_time) - datetime.combine(date.today(), starting_time)
			duration_secs = delta.seconds + delta.microseconds / 1000000
			output_data += "samāptam: %d padyāni, %f kṣaṇāḥ" % ( len(verses), duration_secs )

			output_fn_suffix = '_meter_identified'

		elif session["skrutable_action"] == "split":

			IAST_input = T.transliterate(
				input_data,
				from_scheme=session["from_scheme"],
				to_scheme='IAST',
				is_input_xml=session["is_input_xml"],
				)

			try:
				split_result = Spl.split(
					IAST_input,
					splitter_model=session["splitter_model"],
					preserve_compound_hyphens=session['preserve_compound_hyphens'],
					preserve_punctuation=session['preserve_punctuation'],
					is_input_xml=session["is_input_xml"],
					)
			except HTTPError as e:
				if e.response.status_code == 413:
					raise BadGateway("Upstream service returned 413 Request Entity Too Large")
					# TODO: have Skrutable backend handle batching to relieve burden on upstream server
				else:
					raise

			output_data = T.transliterate(
				split_result,
				from_scheme='IAST',
				to_scheme=session["to_scheme"],
				avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
				is_input_xml=session["is_input_xml"],
				)

			output_fn_suffix = '_split'

		# prepare and return output file

		def remove_diacritics(filename):
			normalized = unicodedata.normalize('NFD', filename)
			without_diacritics = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
			return secure_filename(without_diacritics)

		file_extension = input_fn[input_fn.find('.') + 1:]
		cleaned_input_fn = remove_diacritics(input_fn)
		if cleaned_input_fn == file_extension:
			output_fn = f"skrutable_result{output_fn_suffix}.{file_extension}"
		else:
			output_fn = (	cleaned_input_fn[:input_fn.find('.')] +
							f"{output_fn_suffix}.{file_extension}"
						)

		response = make_response(output_data)
		response.headers["Content-Disposition"] = "attachment; filename=%s" % output_fn
		return response

@app.route('/api', methods=["GET"])
def api_landing():
	return render_template("api.html")

def get_inputs(required_args, request):

	if required_args[0] != "input_text":
		return "The variable input_text should always be first in required_arg_list"

	if not (request.form or request.json):
		return "Received neither form nor json input."

	data_source = dict(request.form or request.json)
	error_msg = (
		"Couldn't get all fields:\n" +
		f"required_args: {required_args}\n" +
		f"request.files {request.files}\n" +
  		"data_source (" + ("json" if request.json else "form") + f") {data_source}"
	)

	try:
		if request.files:
			input_file = request.files["input_file"]
			input_text = input_file.stream.read().decode('utf-8')
		else: # should all be in either form or json
			input_text = data_source["input_text"]
	except:
		return error_msg

	inputs = {"input_text": input_text}

	for arg in required_args[1:]:

		if arg not in data_source:
			return error_msg

		# convert boolean strings to real booleans
		if data_source[arg].lower() == 'true':
			data_source[arg] = True
		elif data_source[arg].lower() == 'false':
			data_source[arg] = False

		inputs[arg] = data_source[arg]

	return inputs

@app.route('/api/transliterate', methods=["GET", "POST"])
def api_transliterate():

	# assume that GET request is person surfing in browser
	if request.method == "GET":
		return render_template("errors/POSTonly.html")

	inputs = get_inputs(["input_text", "from_scheme", "to_scheme"], request)
	if isinstance(inputs, str):
		return inputs # == error_msg

	result = T.transliterate(
		inputs["input_text"],
		from_scheme=inputs["from_scheme"],
		to_scheme=inputs["to_scheme"],
		avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
	)
	return result

@app.route('/api/scan', methods=["GET", "POST"])
def api_scan():

	if request.method == "GET":
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
		return inputs # == error_msg

	V = S.scan(
		inputs["input_text"],
		from_scheme=inputs["from_scheme"],
	)

	result = V.summarize(
		show_weights=inputs["show_weights"],
		show_morae=inputs["show_morae"],
		show_gaRas=inputs["show_gaRas"],
		show_alignment=inputs["show_alignment"],
		show_label=False
	)

	return result

@app.route('/api/identify-meter', methods=["GET", "POST"])
def api_identify_meter():

	if request.method == "GET":
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
		return inputs # == error_msg

	r_o, r_k_m = parse_complex_resplit_option(
		complex_resplit_option=inputs["resplit_option"]
	)

	V = MI.identify_meter(
		inputs["input_text"] ,
		resplit_option=r_o,
		resplit_keep_midpoint=r_k_m,
		from_scheme=inputs["from_scheme"]
	)

	result = V.summarize(
		show_weights=inputs["show_weights"],
		show_morae=inputs["show_morae"],
		show_gaRas=inputs["show_gaRas"],
		show_alignment=inputs["show_alignment"],
		show_label=True
	)

	return result


@app.route('/api/split', methods=["GET", "POST"])
def api_split():

	if request.method == "GET":
		return render_template("errors/POSTonly.html")

	inputs = get_inputs(
		[	"input_text",
			"from_scheme",
			"to_scheme",
		],
		request
	)

	if isinstance(inputs, str):
		return inputs # == error_msg

	IAST_input = T.transliterate(
		inputs["input_text"],
		from_scheme=inputs["from_scheme"],
		to_scheme='IAST',
	)

	split_result = Spl.split(
		IAST_input,
		splitter_model=session["splitter_model"],
		preserve_compound_hyphens=session['preserve_compound_hyphens'],
		preserve_punctuation=session['preserve_punctuation'],
		)

	result = T.transliterate(
		split_result,
		from_scheme='IAST',
		to_scheme=inputs["to_scheme"],
		avoid_virama_indic_scripts=session["avoid_virama_indic_scripts"],
		)

	return result


@app.route('/reset')
def reset_variables():
	session["skrutable_action"] = "..."
	session["from_scheme"] = "IAST"; session["to_scheme"] = "IAST"
	session["weights"] = 1; session["morae"] = 1; session["gaRas"] = 1
	session["alignment"] = 1
	session["resplit_option"] = "resplit_lite_keep_mid"
	session["meter_label"] = ""
	session["melody_options"] = []
	session["avoid_virama_indic_scripts"] = 1
	session["preserve_compound_hyphens"] = 1
	session["preserve_punctuation"] = 1
	session["splitter_model"] = "dharmamitra_2024_sept"
	session["is_input_xml"] = 0
	session.modified = True
	return redirect(url_for('index'))

@app.route('/ex1')
def ex1():
	g.text_input = "dharmakṣetre kurukṣetre samavetā yuyutsavaḥ /\nmāmakāḥ pāṇḍavāś caiva kim akurvata sañjaya //"
	g.text_output = """धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः /
मामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय //"""
	session["from_scheme"] = "IAST"; session["to_scheme"] = "DEV"
	session["weights"] = 1; session["morae"] = 1; session["gaRas"] = 1
	session["alignment"] = 1
	session["resplit_option"] = "resplit_lite_keep_mid"
	session["skrutable_action"] = "transliterate"
	session.modified = True
	return render_template(
		'main.html',
		text_input=g.text_input,
		text_output=g.text_output,
		**{k:session[k] for k in session if k in SESSION_VARIABLE_NAMES},
	)

@app.route('/ex2')
def ex2():
	g.text_input = """धात्वर्थं बाधते कश्चित् कश्चित् तमनुवर्तते |
तमेव विशिनष्ट्यन्य उपसर्गगतिस्त्रिधा ||"""
	g.text_output = """gggglggl	{m: 14}    [8: mrgl]
gglllglg    {m: 12}    [8: tslg]
lglllggl    {m: 11}    [8: jsgl]
llgllglg    {m: 11}    [8: sslg]

    dhā    tva  rthaṃ     bā    dha     te     ka    ści
      g      g      g      g      l      g      g      l
    tka    ści    tta     ma     nu     va    rta     te
      g      g      l      l      l      g      l      g
     ta     me     va     vi     śi     na   ṣṭya    nya
      l      g      l      l      l      g      g      l
      u     pa     sa    rga     ga     ti   stri    dhā
      l      l      g      l      l      g      l      g

anuṣṭubh (1,2: pathyā, 3,4: pathyā)"""
	session["from_scheme"] = "DEV"; session["to_scheme"] = "IAST"
	session["weights"] = 1; session["morae"] = 1; session["gaRas"] = 1
	session["alignment"] = 1
	session["resplit_option"] = "resplit_lite_keep_mid"
	session["skrutable_action"] = "identify meter"
	session["meter_label"] = "anuSTubh"
	session["melody_options"] = ['Madhura Godbole', 'H.V. Nagaraja Rao', 'Shatavadhani Ganesh',  'Diwakar Acarya']
	session.modified = True
	return render_template(
		'main.html',
		text_input=g.text_input,
		text_output=g.text_output,
		**{k: session[k] for k in session if k in SESSION_VARIABLE_NAMES},
	)

@app.route('/ex3')
def ex3():
	g.text_input = """तव करकमलस्थां स्फाटिकीमक्षमालां , नखकिरणविभिन्नां दाडिमीबीजबुद्ध्या |
प्रतिकलमनुकर्षन्येन कीरो निषिद्धः , स भवतु मम भूत्यै वाणि ते मन्दहासः ||"""
	g.text_output = """llllllggglgglgg    {m: 22}    [15: nnmyy]
llllllggglgglgg    {m: 22}    [15: nnmyy]
llllllggglgglgg    {m: 22}    [15: nnmyy]
llllllggglgglgg    {m: 22}    [15: nnmyy]

     ta     va     ka     ra     ka     ma     la  sthāṃ   sphā     ṭi     kī     ma    kṣa     mā    lāṃ
      l      l      l      l      l      l      g      g      g      l      g      g      l      g      g
     na    kha     ki     ra     ṇa     vi    bhi   nnāṃ     dā     ḍi     mī     bī     ja     bu  ddhyā
      l      l      l      l      l      l      g      g      g      l      g      g      l      g      g
    pra     ti     ka     la     ma     nu     ka    rṣa    nye     na     kī     ro     ni     ṣi  ddhaḥ
      l      l      l      l      l      l      g      g      g      l      g      g      l      g      g
     sa    bha     va     tu     ma     ma    bhū   tyai     vā     ṇi     te     ma    nda     hā    saḥ
      l      l      l      l      l      l      g      g      g      l      g      g      l      g      g

mālinī [15: nnmyy]"""
	session["from_scheme"] = "DEV"; session["to_scheme"] = "IAST"
	session["weights"] = 1; session["morae"] = 1; session["gaRas"] = 1
	session["alignment"] = 1
	session["resplit_option"] = "resplit_lite_keep_mid"
	session["skrutable_action"] = "identify meter"
	session["meter_label"] = "mAlinI"
	session["melody_options"] = ['Madhura Godbole', 'Sadananda Das', 'H.V. Nagaraja Rao', 'Shatavadhani Ganesh']
	session.modified = True
	return render_template(
		'main.html',
		text_input=g.text_input,
		text_output=g.text_output,
		**{k: session[k] for k in session if k in SESSION_VARIABLE_NAMES},
	)

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

@app.route('/settings', methods=["GET", "POST"])
def settings_page():
	if request.method == "GET":
		return render_template(
			"settings.html",
			**{k: session[k] for k in session if k in EXTRA_OPTION_NAMES},
		)
	elif request.method == "POST":
		process_settings_form(request.form)
		return render_template(
			"settings.html",
			**{k: session[k] for k in session if k in EXTRA_OPTION_NAMES},
		)

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

def prep_split_output_for_Apte(split_text):
	split_words = split_text.split() # would be nice to retain original whitespace (tab etc.)
	output_HTML = "<p>"
	for word in split_words:
		if re.sub('[,\|।—\?!\.\d\s]', '', word) == "": # expand punctuation set ...
			output_HTML += word + " "
		else:
			output_HTML += "<a href='%s' target='apteTab'>%s</a> " % (prep_Apte_query(word), word)
	output_HTML += "</p>"
	return output_HTML
