import os
import html
import re

from datetime import datetime, date
from flask import Flask, redirect, render_template, request, url_for, session, send_from_directory, send_file, make_response

from skrutable.transliteration import Transliterator
from skrutable.scansion import Scanner
from skrutable.meter_identification import MeterIdentifier
from skrutable.meter_patterns import meter_melodies
from skrutable.splitter.wrapper import Splitter

app = Flask(__name__)
app.config["DEBUG"] = True
app.config["SECRET_KEY"] = "asdlkvumnxlapoiqyernxnfjtuzimzjdhryien" # for session, no actual need for secrecy

# for serving static files from assets folder
@app.route('/assets/<path:name>')
def serve_files(name):
	return send_from_directory('assets', name)

# attempt at serving entire folder at once (not yet successful)
# @app.route('/assets/')
# def serve_files():
# 	return send_file('assets/index.html')

# this helps app work both publically (e.g. on PythonAnywhere) and locally
CURRENT_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Skrutable main objects
T = Transliterator()
S = Scanner()
MI = MeterIdentifier()
Spl = Splitter()

# variable names for flask.session() object
select_element_names = [
	"skrutable_action",
	"text_input", "text_output",
	"from_scheme", "to_scheme",
	"resplit_option",
	]
checkbox_element_names = [
	"weights", "morae", "gaRas",
	"alignment",
	] # to be extended with corpus text abbreviations for textPrioritize
melody_variable_names = [
	"meter_label", "melody_options"
	]
session_variable_names = (
	select_element_names +
	checkbox_element_names +
	melody_variable_names
	)

# for updating session variables
def process_form(form):

   # first do values of "select" elements (i.e. dropdowns)
	for var_name in select_element_names:
		# print(var_name, request.form[var_name])
		session[var_name] = request.form[var_name]

	# then do values of "checkbox" elements for scansion detail
	scan_detail_option_choices = request.form.getlist("scan_detail")
	for var_name in checkbox_element_names:
		if var_name in scan_detail_option_choices:
			session[var_name] = 1
		else:
			session[var_name] = 0

	session.modified = True
	return

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
	for var_name in session_variable_names:
		if var_name not in session:
			reset_variables()

@app.route("/", methods=["GET", "POST"])
def index():

	ensure_keys()

	if request.method == "GET":

		return render_template(
			"main.html",
			skrutable_action=session["skrutable_action"],
			text_input=session["text_input"], text_output=session["text_output"],
			from_scheme=session["from_scheme"], to_scheme=session["to_scheme"],
			weights=session["weights"],
			morae=session["morae"],
			gaRas=session["gaRas"],
			alignment=session["alignment"],
			resplit_option=session["resplit_option"],
			meter_label=session["meter_label"],
			melody_options=session["melody_options"]
			)

	if request.method == "POST":

		process_form(request.form)

		# carry out chosen action

		if session["skrutable_action"] == "transliterate":

			session["text_output"] = T.transliterate(
				session["text_input"],
				from_scheme=session["from_scheme"],
				to_scheme=session["to_scheme"]
				)

			session["meter_label"] = ""; session["melody_options"] = [] # cancel these

		elif session["skrutable_action"] == "scan":

			V = S.scan(
				session["text_input"] ,
				from_scheme=session["from_scheme"]
				)

			session["text_output"] = V.summarize(
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
				session["text_input"] ,
				resplit_option=r_o,
				resplit_keep_midpoint=r_k_m,
				from_scheme=session["from_scheme"]
				)

			session["text_output"] = V.summarize(
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
					to_scheme='HK'
					)
				session["melody_options"] = meter_melodies[ short_meter_label ]
			else:
				session["meter_label"] = ""; session["melody_options"] = [] # cancel these

		elif session["skrutable_action"] == "split":

			IAST_input = T.transliterate(
				session["text_input"],
				from_scheme=session["from_scheme"],
				to_scheme='IAST'
				)

			split_result = Spl.split(
				IAST_input,
				prsrv_punc=True
				)

			session["text_output"] = T.transliterate(
				split_result,
				from_scheme='IAST',
				to_scheme=session["to_scheme"]
				)

			session["meter_label"] = ""; session["melody_options"] = [] # cancel these

		elif session["skrutable_action"] == "apte links":

			session["meter_label"] = ""; session["melody_options"] = [] # cancel these

			split_text = session["text_input"] # must already be split
			output_HTML = prep_split_output_for_Apte(split_text)
			return render_template(	"main_HTML_output.html",
									skrutable_action=session["skrutable_action"],
									text_input=session["text_input"],
									output_HTML=output_HTML,
									from_scheme=session["from_scheme"], to_scheme=session["to_scheme"],
									weights=session["weights"],
									morae=session["morae"],
									gaRas=session["gaRas"],
									alignment=session["alignment"],
									resplit_option=session["resplit_option"],
									melody_options=session["melody_options"]
									)

		session.modified = True

		return redirect(url_for('index'))


@app.route("/wholeFile", methods=["POST"])
def wholeFile():

	ensure_keys()

	# when form sent from GUI ("whole file" button clicked)
	if request.form != {}:

		process_form(request.form)

		# send onward to upload form
		return render_template(
			"wholeFile.html",
			skrutable_action=session["skrutable_action"],
			text_input=session["text_input"], text_output=session["text_output"],
			from_scheme=session["from_scheme"], to_scheme=session["to_scheme"],
			weights=session["weights"], morae=session["morae"], gaRas=session["gaRas"],
			alignment=session["alignment"],
			resplit_option=session["resplit_option"]
			)

	# when file chosen for upload
	elif request.files != {}:

		# session variables already processed in previous step

		# take in and read file
		input_file = request.files["input_file"]
		input_fn = input_file.filename
		input_data = input_file.stream.read().decode('utf-8')

		# carry out chosen action

		if session["skrutable_action"] == "transliterate":

			output_data = T.transliterate(
				input_data,
				from_scheme=session["from_scheme"],
				to_scheme=session["to_scheme"]
				)

			output_fn_suffix = '_transliterated'

		elif session["skrutable_action"] == "identify meter":

			r_o, r_k_m = parse_complex_resplit_option(
				complex_resplit_option=session["resplit_option"]
				)

			# record starting time

			# now = datetime.now()
			# timestamp1 = now.strftime("%H:%M:%S")
			starting_time = datetime.now().time()

			verses = input_data.splitlines() # during post \n >> \r\n
			output_data = ''
			# output_data = "%s\n\n" % timestamp1
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
				to_scheme='IAST'
				)
			
			split_result = Spl.split(
				IAST_input,
				prsrv_punc=True,
				wholeFile=True
				)

			output_data = T.transliterate(
				split_result,
				from_scheme='IAST',
				to_scheme=session["to_scheme"]
				)

			output_fn_suffix = '_split'

		# prepare and return output file
		output_fn = (	input_fn[:input_fn.find('.')] +
						output_fn_suffix +
						input_fn[input_fn.find('.'):]
					)
		response = make_response( output_data )
		response.headers["Content-Disposition"] = "attachment; filename=%s" % output_fn
		return response

@app.route('/reset')
def reset_variables():
	session["skrutable_action"] = "..."
	session["text_input"] = ""; session["text_output"] = ""
	session["from_scheme"] = "IAST"; session["to_scheme"] = "IAST"
	session["weights"] = 1; session["morae"] = 1; session["gaRas"] = 1
	session["alignment"] = 1
	session["resplit_option"] = "resplit_lite_keep_mid"
	session["meter_label"] = ""
	session["melody_options"] = []
	session.modified = True
	return redirect(url_for('index'))

@app.route('/ex1')
def ex1():
	session["text_input"] = "dharmakṣetre kurukṣetre samavetā yuyutsavaḥ /\nmāmakāḥ pāṇḍavāś caiva kim akurvata sañjaya //"
	session["text_output"] = """धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः /
मामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय //"""
	session["from_scheme"] = "IAST"; session["to_scheme"] = "DEV"
	session["weights"] = 1; session["morae"] = 1; session["gaRas"] = 1
	session["alignment"] = 1
	session["resplit_option"] = "resplit_lite_keep_mid"
	session["skrutable_action"] = "transliterate"
	session.modified = True
	return redirect(url_for('index'))

@app.route('/ex2')
def ex2():
	session["text_input"] = """धात्वर्थं बाधते कश्चित् कश्चित् तमनुवर्तते |
तमेव विशिनष्ट्यन्य उपसर्गगतिस्त्रिधा ||"""
	session["text_output"] = """gggglggl    {m: 14}    [8: mrgl]
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
	return redirect(url_for('index'))

@app.route('/ex3')
def ex3():
	session["text_input"] = """तव करकमलस्थां स्फाटिकीमक्षमालां , नखकिरणविभिन्नां दाडिमीबीजबुद्ध्या |
प्रतिकलमनुकर्षन्येन कीरो निषिद्धः , स भवतु मम भूत्यै वाणि ते मन्दहासः ||"""
	session["text_output"] = """llllllggglgglgg    {m: 22}    [15: nnmyy]
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
	return redirect(url_for('index'))

@app.route('/about')
def about_page():
	return render_template("about.html")

@app.route('/tutorial')
def tutorial_page():
	return render_template("tutorial.html")

@app.route('/next')
def next_page():
	return render_template("next.html")

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
