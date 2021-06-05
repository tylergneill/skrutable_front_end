import math
import os
import json
import re
import numpy as np
from collections import OrderedDict, Counter
from copy import copy
from fastdist import fastdist

CURRENT_FOLDER = os.path.dirname(os.path.abspath(__file__))
def load_dict_from_json(relative_path_fn):
	json_full_fn = os.path.join(CURRENT_FOLDER, relative_path_fn)
	with open(json_full_fn,'r') as f_in:
		loaded_dict = json.loads( f_in.read() )
	return loaded_dict

# get theta data
theta_fn = 'theta.tsv'
theta_fn_full_path = os.path.join(CURRENT_FOLDER, theta_fn)
with open(theta_fn_full_path,'r') as f_in:
    theta_data = f_in.read()
theta_data = theta_data.replace('*','') # very hacky, should be cleaned in data itself
theta_rows = theta_data.split('\n')
theta_rows.pop(-1); # blank final row
theta_rows.pop(0); # header row with topic abbreviations
theta_rows.pop(0); # useless "!ctsdata" second header row

# from theta data, get doc ids, doc full-text, and theta numbers
doc_ids = []
doc_fulltext = OrderedDict() # e.g. doc_fulltext[DOC_ID]
thetas = {} # e.g. theta[DOC_ID]
for row in theta_rows:
    cells = row.split('\t') # must have been converted to TSV first!
    doc_id, doc_text, theta_values = cells[1], cells[2], cells[3:]
    # don't need cells[0] which would be doc_num
    doc_ids.append(doc_id)
    doc_fulltext[doc_id] = doc_text
    thetas[doc_id] = [ float(th) for th in theta_values ]

with open('assets/pramanaNLP/doc_id_list.txt','w') as f_out:
	f_out.write('\n'.join(doc_ids))

# overall corpus string and list of all words
corpus_words_string = ' '.join( doc_fulltext.values() )
corpus_words_string.replace('  ',' ');
corpus_words_list = corpus_words_string.split()
corpus_vocab = list(set(corpus_words_list))
corpus_vocab.sort()
corpus_vocab_reduced = copy(corpus_vocab)

# create word frequency dictionary for words in entire corpus
freq_w = Counter(corpus_words_list)

# load phi data
phi_fn = 'phi.csv'
phi_fn_full_path = os.path.join(CURRENT_FOLDER, phi_fn)
with open(phi_fn_full_path,'r') as f_in:
    phi_data = f_in.read()
phi_data = phi_data.replace('"','') # I think this here but not for theta because of way theta TSV was re-exported
phi_rows = phi_data.split('\n')
phi_rows.pop(-1); # blank final row
phi_rows.pop(0);

# store phi data
phis = {} # e.g., phis[WORD][TOPIC_NUM-1] = P(w|t) conditional probability
for row in phi_rows:
    cells = row.split(',')
    word, phi_values = cells[0], cells[1:]
    phis[word] = [ float(ph) for ph in phi_values ]

# exclude words
stopwords = ['iti', 'na', 'ca', 'api', 'eva', 'tad', 'tvāt', 'tat', 'hi', 'ādi', 'tu', 'vā'] # used in topic modeling
error_words = [':', '*tat', 'eva*', '*atha', ')'] # fix in the data!
corpus_vocab_reduced = [
    word
    for word in corpus_vocab
        if not (word in (stopwords + error_words) or freq_w[word] < 3)
]

# prepare supplementary dicts

# doc_links
doc_links = {}
doc_links[doc_ids[0]] = {'prev': doc_ids[len(doc_ids)-1], 'next': doc_ids[1]}
for i in range(1, len(doc_ids)-1):
	doc_links[doc_ids[i]] = {'prev': doc_ids[i-1], 'next': doc_ids[i+1]}
doc_links[doc_ids[len(doc_ids)-1]] = {'prev': doc_ids[len(doc_ids)-2], 'next': doc_ids[0]}

text_abbrev2fn = load_dict_from_json("assets/pramanaNLP/text_abbreviations.json")
with open("assets/pramanaNLP/corpus_texts.txt", 'w') as f_out:
	f_out.write('\n'.join([abbrv+'\t'+fn for (abbrv, fn) in text_abbrev2fn.items()]))

section_labels = load_dict_from_json("assets/pramanaNLP/section_labels.json")

doc_original_fulltext = load_dict_from_json("assets/pramanaNLP/doc_original_fulltext.json")

def make_hit_link(doc_id):
	hit_link = "<a href='doc_search?doc_id_input=%s'>%s</a>" % (doc_id, doc_id)
	return hit_link

def parse_complex_doc_id(doc_id):
# returns only first original doc id from any resizing modifications
	txt_abbr = doc_id[:doc_id.find('_')]
	# local_doc_id = doc_id[doc_id.find('_'):]
	# import pdb; pdb.set_trace()
	local_doc_id = re.search('[^_\^:]+', doc_id[doc_id.find('_')+1:]).group()
	return txt_abbr, local_doc_id

def format_doc_search_results(query_id, results_dict):
	results_HTML = ""
	results_HTML += """<br><br><h1>%s <small>(%s)</small></h1>""" % (query_id, section_labels[query_id])
	results_HTML += """<div class="row">"""

	browse_button_template = """
<div class="col-md-2">
<form method="get" action="doc_search">
	<input type="hidden" name="doc_id_input" value="%s" />
	<input type="submit" class="btn btn-block btn-primary" value="%s" />
</form>
</div>
"""
	prev_button = browse_button_template % (doc_links[query_id]['prev'], "<< " + doc_links[query_id]['prev'])
	results_HTML += prev_button
	next_button = browse_button_template % (doc_links[query_id]['next'], doc_links[query_id]['next'] + " >>")
	results_HTML += next_button

	results_HTML += """</div>
<div class="row">
<div class="col-md-6">
"""
	# results_HTML = "<h2>Doc “%s”</h2><br><br>" % (query_id)
	results_HTML += "<h2>original text</h2><br><br>"
	results_HTML += "<p>%s</p><br><br>" % doc_original_fulltext[query_id]
	results_HTML += """
</div>
<div class="col-md-6">
"""
	results_HTML += "<h2>segmented text</h2><br><br>"
	results_HTML += "<p>%s</p><br><br>" % doc_fulltext[query_id]

	results_HTML += """
</div>
<div class="row">
<div class="col-md-4">
"""
	results_HTML += "<h2>Doc “%s” Topic Plot</h2><br><br>" % (query_id)
	relative_path_to_plot_pngs = "/assets/pramanaNLP/doc_plot_pngs/"
	plot_png_fn = "%s.png" % query_id
	plot_png_full_fn = os.path.join(relative_path_to_plot_pngs, plot_png_fn)
	results_HTML += """<img id="plot" src="%s" alt="oops" width="400" height="280">""" % plot_png_full_fn

	results_HTML += """
</div>
<div class="col-md-4">
"""
	list_contents = ''.join( ["<p>%s (%.2f) (<a href='textViewer?text_abbrv=%s#%s' target='textViewer%s' %s>textView</a>)</p>" % (make_hit_link(id), results_dict[id], *parse_complex_doc_id(id), *parse_complex_doc_id(id)) for id in results_dict.keys()] )
	results_HTML += "<h2>Similar Docs by Topic for %s</h2><br>%s" % (query_id, list_contents)
	results_HTML += """
</div>"""

	return results_HTML

def compare_by_topic(query_id):
	N = 500 # number of closest docs to find
	query_vector = np.array(thetas[query_id])
	topic_similiarity_score = {} # e.g. topic_similiarity_score[DOC_ID] = FLOAT
	topic_candidate_vectors = []
	for doc_id in doc_ids:
	    candidate_vector = np.array(thetas[doc_id]) # dimensionality = k, number of topics
	    topic_candidate_vectors.append(candidate_vector)
	    topic_similiarity_score[doc_id] = fastdist.cosine(query_vector, candidate_vector)
	sorted_results = sorted(topic_similiarity_score.items(), key=lambda item: item[1], reverse=True)
	ids_for_closest_N_docs_by_topics = [ res[0] for res in sorted_results[:N+1] ][1:] # omit first which is query itself
	results_dict = {doc_id:topic_similiarity_score[doc_id] for doc_id in ids_for_closest_N_docs_by_topics}
	# result_dict = { id_1: score_1, id_2: score_2, ...}
	results_HTML = format_doc_search_results(query_id, results_dict)
	return results_HTML

def prepare_text_view(text_abbreviation):

	# use text_abbreviation to read in text string
	text_fn = text_abbrev2fn[text_abbreviation] + '.txt'
	relative_path_to_text = "assets/pramanaNLP/texts"
	text_full_fn = os.path.join(CURRENT_FOLDER, relative_path_to_text, text_fn)

	with open(text_full_fn,'r') as f_in:
		text_string = f_in.read()

	# wrap in <div>
	text_HTML = "<div>%s</div>" % text_string

	# use re to wrap {...} content in <h1> and [...] in <h2>
	# for each, also make content into id attribute for tag (>> # link)
	text_HTML = re.sub("{([^}]*?)}", "<h1 id='\\1'>\\1<h1>", text_HTML)
	text_HTML = re.sub("\[([^\]]*?)\]", "<h2 id='\\1'>\\1<h2>", text_HTML)

	# (possibly escape characters like tab, <>, etc.)

	return text_HTML
