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

import IR_tools

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
	"alignment"
	]
melody_variable_names = [
	"meter_label", "melody_options"
	]
vatayana_variable_names = [
	"topic_weights",
	"topic_labels",
	]
session_variable_names = (
	select_element_names +
	checkbox_element_names +
	melody_variable_names +
	vatayana_variable_names
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
	session["doc_id"] = ""; session["doc_id_1"] = ""; session["doc_id_2"] = "",
	session["text_abbreviation_input"] = ""
	session["local_doc_id"] = ""
	session["topic_weights"] = IR_tools.topic_weights_default.tolist()
	session["topic_labels"] = IR_tools.topic_interpretations
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
	return render_template(	"scanGRETILresults.html",
		parent_dir = "https://raw.githubusercontent.com/tylergneill/skrutable_front_end/main/assets/meter_analyses/",
	    dir1 = "1_input_raw",
	    dir2 = "2_input_cleaned",
	    dir3 = "3_output_raw",
	    dir4 = "4_output_cleaned",
	    dir5 = "5_tallies",
	    dir6 = "6_notes"
		)

def prep_Apte_query(IAST_string):
	dev_query = T.transliterate(IAST_string, from_scheme='IAST', to_scheme='DEV')
	while dev_query[-1] == chr(0x94d): dev_query = dev_query[:-1] # remove final Devanagari virāma(s) (U+094d)
	chicago_url = "http://dsal.uchicago.edu/cgi-bin/app/apte_query.py?qs=%s&searchhws=yes&matchtype=default" % dev_query
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

@app.route('/vatayana')
def vatayana_main():
	return render_template("vatayana.html",
	page_subtitle="🪟"
	)

@app.route('/topicExplore')
def vatayana_topic_explore():

	relative_path_to_LDAvis_HTML_fn = "assets/vatayana/ldavis_prepared_50.html"
	LDAvis_HTML_full_fn = os.path.join(CURRENT_FOLDER, relative_path_to_LDAvis_HTML_fn)
	with open(LDAvis_HTML_full_fn, 'r') as f_in:
		LDAvis_HTML = html.unescape(f_in.read())

	return render_template("vatayana-topicExplore.html",
	page_subtitle="topicExplore",
	LDAvis_HTML=LDAvis_HTML
	)

@app.route('/docExplore', methods=["GET", "POST"])
def vatayana_doc_explore():

	ensure_keys()

	if request.method == "POST" or 'doc_id' in request.args:

		if 'doc_id' in request.form:
			doc_id = request.form.get("doc_id")
		elif 'doc_id' in request.args:
			doc_id = request.args.get("doc_id")

		valid_doc_ids = IR_tools.doc_ids
		if doc_id in valid_doc_ids:
			output_HTML = IR_tools.get_closest_docs(
				doc_id,
				topic_weights=session['topic_weights'],
				topic_labels=session['topic_labels']
				)
		else:
			output_HTML = "<br><p>Please enter valid doc ids like " + str(IR_tools.ex_doc_ids)[1:-1] + " etc.</p><p>See <a href='assets/vatayana/doc_id_list.txt' target='_blank'>doc id list</a> and <a href='assets/vatayana/corpus_texts.txt' target='_blank'>corpus text list</a> for hints to get started.</p>"

		return render_template(	"vatayana-docExplore.html",
								page_subtitle="docExplore",
								doc_id=doc_id,
								doc_explore_output=output_HTML
								)

	else: # request.method == "GET" or URL query malformed

		return render_template(	"vatayana-docExplore.html",
								page_subtitle="docExplore",
								doc_id="",
								doc_explore_output=""
								)

@app.route('/docCompare', methods=["GET", "POST"])
def vatayana_doc_compare():

	ensure_keys()

	if request.method == "POST" or 'doc_id_1' in request.args:

		doc_id_1 = doc_id_2 = ""
		if 'doc_id_1' in request.form:
			doc_id_1 = request.form.get("doc_id_1")
			doc_id_2 = request.form.get("doc_id_2")
		elif 'doc_id_1' in request.args:
			doc_id_1 = request.args.get("doc_id_1")
			doc_id_2 = request.args.get("doc_id_2")

		valid_doc_ids = IR_tools.doc_ids
		sim_btn_left = sim_btn_right = ""
		if doc_id_1 == doc_id_2:
			output_HTML = "<br><p>Those are the same, please enter two different doc ids to compare.</p>"
		elif doc_id_1 in valid_doc_ids and doc_id_2 in valid_doc_ids:
			# output_HTML = "<br><p>Good, those are valid.</p>"
			output_HTML, sim_btn_left, sim_btn_right = IR_tools.compare_doc_pair(
				doc_id_1,
				doc_id_2,
				topic_weights=session['topic_weights'],
				topic_labels=session['topic_labels']
				)
		else:
			output_HTML = "<br><p>Please enter two valid doc ids like " + str(IR_tools.ex_doc_ids)[1:-1] + " etc.</p><p>See <a href='assets/vatayana/doc_id_list.txt' target='_blank'>doc id list</a> and <a href='assets/vatayana/corpus_texts.txt' target='_blank'>corpus text list</a> for hints to get started.</p>"

		return render_template(	"vatayana-docCompare.html",
								page_subtitle="docCompare",
								doc_id_1=doc_id_1,
								doc_id_2=doc_id_2,
								activate_similar_link_buttons_left=sim_btn_left,
								activate_similar_link_buttons_right=sim_btn_right,
								doc_compare_output=output_HTML
								)

	else: # request.method == "GET" or URL query malformed

		return render_template(	"vatayana-docCompare.html",
								page_subtitle="docCompare",
								doc_id_1="",
								doc_id_2="",
								doc_explore_output=""
								)

@app.route('/textView', methods=["GET", "POST"])
def vatayana_text_view():

	if request.method == "POST" or 'text_abbrv' in request.args:

		if 'text_abbreviation_input' in request.form:
			text_abbreviation_input = request.form.get("text_abbreviation_input")
		elif 'text_abbrv' in request.args:
			text_abbreviation_input = request.args.get("text_abbrv")

		# can't render this properly at all yet
		local_doc_id=''
		if 'local_doc_id' in request.form:
			local_doc_id = request.form.get("local_doc_id")
		elif 'doc_id' in request.args:
			local_doc_id = request.args.get("doc_id")

		text_title = ""
		valid_text_abbrvs = list(IR_tools.text_abbrev2fn.keys())
		disallowed_fulltexts = IR_tools.disallowed_fulltexts
		if text_abbreviation_input in disallowed_fulltexts:
			text_HTML = "<br><p>sorry, fulltext is not available for these texts at present: " + str(disallowed_fulltexts)[1:-1] + " (see <a href='https://github.com/tylergneill/pramana-nlp/tree/master/data_prep/1_etext_originals' target='_blank'>note</a> for more info)</p>"
		elif text_abbreviation_input in valid_text_abbrvs:
			text_title = IR_tools.text_abbrev2fn[text_abbreviation_input]
			text_HTML = IR_tools.get_text_view(text_abbreviation_input)
		else:
			text_HTML = "<br><p>Please enter valid doc ids like " + str(IR_tools.ex_doc_ids)[1:-1] + " etc.</p><p>See <a href='assets/vatayana/doc_id_list.txt' target='_blank'>doc id list</a> and <a href='assets/vatayana/corpus_texts.txt' target='_blank'>corpus text list</a> for hints to get started.</p>"

		return render_template("vatayana-textView.html",
		page_subtitle="textView",
		text_title=text_title,
		text_HTML=text_HTML
		)

	else: # request.method == "GET" or no URL params

		return render_template(	"vatayana-textView.html",
								page_subtitle="textView",
								text_abbreviation="",
								local_doc_id="",
								text_HTML=""
								)

@app.route('/BrucheionAlign')
def vatayana_Brucheion_align():

	relative_path_to_assets = "assets"
	full_path_to_assets = os.path.join(CURRENT_FOLDER, relative_path_to_assets)

	relative_path_to_Brucheion_HTML_body_fn = "assets/vatayana/Brucheion.html"
	Brucheion_HTML_body_full_fn = os.path.join(CURRENT_FOLDER, relative_path_to_Brucheion_HTML_body_fn)
	with open(Brucheion_HTML_body_full_fn, 'r') as f_in:
		Brucheion_HTML_body = html.unescape(f_in.read())

	return render_template(	"vatayana-BrucheionAlign.html",
							assets_path=relative_path_to_assets,
							# page_subtitle="alignFancy",
							Brucheion_HTML_body=Brucheion_HTML_body
							)


@app.route('/topicAdjust', methods=["GET", "POST"])
def vatayana_topic_adjust():

	ensure_keys()

	if request.method == "POST":

		topic_weight_input = []
		topic_label_input = []
		for key, val in request.form.items():
			if key == "topic_wt_slider_all":
				topic_weight_input = list(IR_tools.new_full_vector( IR_tools.K, float(val) ))
				topic_label_input = session["topic_labels"]
			elif key.startswith("topic_wt_slider_"):
				topic_weight_input.append(float(val)) # not sure why 1s come back as int
			elif key.startswith("topic_label_"):
				topic_label_input.append(val)

		session["topic_weights"] = topic_weight_input
		session["topic_labels"] = topic_label_input

	else:
		pass

	topicAdjustOutput_HTML = IR_tools.format_topic_adjust_output(
		topic_weight_input=session["topic_weights"],
		topic_label_input=session["topic_labels"]
		)

	return render_template(	"vatayana-topicAdjust.html",
							page_subtitle="topicAdjust",
							topicAdjustOutput_HTML=topicAdjustOutput_HTML
							)
