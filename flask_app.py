from flask import Flask, redirect, render_template, request, url_for, session
from flask import make_response

from skrutable.transliteration import Transliterator
from skrutable.scansion import Scanner
from skrutable.meter_identification import MeterIdentifier
from skrutable.meter_patterns import meter_melodies
from skrutable.splitter.wrapper import Splitter

T = Transliterator()
S = Scanner()
MI = MeterIdentifier()
Spl = Splitter()

def parse_complex_resplit_option(complex_resplit_option):
	if complex_resplit_option[-len('_keep_mid'):] == '_keep_mid':
		resplit_keep_midpoint = True
		resplit_option = complex_resplit_option[:-len('_keep_mid')]
	else:
		resplit_keep_midpoint = False
		resplit_option = complex_resplit_option
	return resplit_option, resplit_keep_midpoint

app = Flask(__name__)
app.config["DEBUG"] = True
app.config["SECRET_KEY"] = "asdlkvumnxlapoiqyernxnfjtuzimzjdhryien"

select_element_names = [
	"skrutable_action",
	"text_input", "text_output",
	"from_scheme", "to_scheme",
	"resplit_option"
	]
checkbox_element_names = [
	"weights", "morae", "gaRas",
	"alignment"
	]
melody_variable_names = [
	"meter_label", "melody_options"
	]
session_variable_names = (
	select_element_names +
	checkbox_element_names +
	melody_variable_names
	)

def process_form(form):

   # first do values of "select" elements
	for var_name in select_element_names:
		session[var_name] = request.form[var_name]

	# then do values of "checkbox" elements
	scan_detail_option_choices = request.form.getlist("scan_detail")
	for var_name in checkbox_element_names:
		if var_name in scan_detail_option_choices:
			session[var_name] = 1
		else:
			session[var_name] = 0

	session.modified = True

@app.route("/testMelody", methods=["GET", "POST"])
def testMelody():

	# just in case, make sure all keys in session
	for var_name in session_variable_names:
		if var_name not in session:
			reset_variables()

	if request.method == "GET":

		return render_template(
			"testMelody.html",
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

			session["meter_label"] = ""
			session["melody_options"] = []


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

			session["meter_label"] = ""
			session["melody_options"] = []


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
				session["meter_label"] = ""
				session["melody_options"] = []

		session.modified = True

		return redirect(url_for('testMelody'))

@app.route("/", methods=["GET", "POST"])
def index():

	# just in case, make sure all keys in session
	for var_name in session_variable_names:
		if var_name not in session:
			reset_variables()

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
			resplit_option=session["resplit_option"]
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

		session.modified = True

		return redirect(url_for('index'))


@app.route("/wholeFile", methods=["POST"])
def wholeFile():

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
			from datetime import datetime, date
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
				prsrv_punc=True
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
	return render_template("scanGRETILresults.html",
	parent_dir = "https://raw.githubusercontent.com/tylergneill/skrutable_front_end/main/assets/meter_analyses/",
    dir1 = "1_input_raw",
    dir2 = "2_input_cleaned",
    dir3 = "3_output_raw",
    dir4 = "4_output_cleaned",
    dir5 = "5_tallies",
    dir6 = "6_notes"
	)

@app.route('/ChicagoApteIAST')
def chicago_apte_iast():
	iast_query = request.args.get('query')
	dev_query = T.transliterate(iast_query, from_scheme='IAST', to_scheme='DEV')
	# remove final Devanagari virāma(s) (U+094d)
	while dev_query[-1] == chr(0x94d): dev_query = dev_query[:-1]
	chicago_url = "http://dsal.uchicago.edu/cgi-bin/app/apte_query.py?qs=%s&searchhws=yes&matchtype=default" % dev_query
	return redirect(chicago_url)
