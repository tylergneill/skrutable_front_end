import math
import os
import json
import re
import numpy as np

from collections import OrderedDict, Counter
from fastdist import fastdist
from string import Template

# set up paths and load main output template

CURRENT_FOLDER = os.path.dirname(os.path.abspath(__file__))

def load_dict_from_json(relative_path_fn):
	json_full_fn = os.path.join(CURRENT_FOLDER, relative_path_fn)
	with open(json_full_fn,'r') as f_in:
		loaded_dict = json.loads( f_in.read() )
	return loaded_dict

results_HTML_template_relative_path = 'templates/pramanaNLP-docSearchResultContents.html'
results_HTML_template_fn = os.path.join(CURRENT_FOLDER, results_HTML_template_relative_path)
with open(results_HTML_template_fn,'r') as f_in:
	results_HTML_template = Template(f_in.read())

##########################################################
# on server start, load corpus and statistics into memory
##########################################################

# get theta data
theta_fn = 'theta.tsv'
theta_fn_full_path = os.path.join(CURRENT_FOLDER, theta_fn)
with open(theta_fn_full_path,'r') as f_in:
    theta_data = f_in.read()
theta_data = theta_data.replace('*',''); theta_data = theta_data.replace('=','') # HACK, should be cleaned in data itself
theta_rows = theta_data.split('\n')
theta_rows.pop(-1); # blank final row
theta_rows.pop(0); # unwanted header row with topic abbreviations (store same from phi data)
theta_rows.pop(0); # unwanted second header row with "!ctsdata" and alpha values

# store theta data (doc ids, doc full-text, and theta numbers)
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
num_docs = len(doc_ids)

# save fresh doc_id list to file
doc_id_list_relative_path_fn = 'assets/pramanaNLP/doc_id_list.txt'
doc_id_list_full_fn = os.path.join(CURRENT_FOLDER, doc_id_list_relative_path_fn)
with open(doc_id_list_full_fn,'w') as f_out:
	f_out.write('\n'.join(doc_ids))

# make copies of overall corpus as single long string and as list of all tokens
corpus_long_string = ' '.join( doc_fulltext.values() )
corpus_long_string.replace('  ',' ')
corpus_tokens = corpus_long_string.split()

# create dict of raw word frequencies and sorted vocab list
freq_w = Counter(corpus_tokens)
corpus_vocab = list(freq_w.keys())
corpus_vocab.sort()

# get phi data
phi_fn = 'phi.csv'
phi_fn_full_path = os.path.join(CURRENT_FOLDER, phi_fn)
with open(phi_fn_full_path,'r') as f_in:
    phi_data = f_in.read()
phi_data = phi_data.replace('"','') # I think this here but not for theta because of way theta TSV was re-exported
phi_rows = phi_data.split('\n')
phi_rows.pop(-1); # blank final row

# store phi data  (naive topic labels and phi numbers)
naive_topic_labels = phi_rows.pop(0).split(','); naive_topic_labels.pop(0);
phis = {} # e.g., phis[WORD][TOPIC_NUM-1] = P(w|t) conditional probability
for row in phi_rows:
    cells = row.split(',')
    word, phi_values = cells[0], cells[1:]
    phis[word] = [ float(ph) for ph in phi_values ]

# load three illustrations of topic meaning (topic_top_words, topic_interpretations, topic_wordclouds)

topic_top_words_fn = 'assets/pramanaNLP/topic_top_words.txt'
topic_top_words_fn_full_path = os.path.join(CURRENT_FOLDER, topic_top_words_fn)
with open(topic_top_words_fn_full_path,'r') as f_in:
    topic_top_words = f_in.readlines()

topic_interpretation_fn = 'assets/pramanaNLP/topic_interpretations.txt'
topic_interpretation_fn_full_path = os.path.join(CURRENT_FOLDER, topic_interpretation_fn)
with open(topic_interpretation_fn_full_path,'r') as f_in:
    topic_interpretations = f_in.readlines()

topic_wordclouds_relative_path = 'assets/pramanaNLP/topic_wordclouds' # only relative for src
topic_wordclouds_full_path = os.path.join(CURRENT_FOLDER, topic_wordclouds_relative_path)
topic_wordcloud_fns = [ os.path.join(topic_wordclouds_full_path, img_fn)
							for img_fn in os.listdir(topic_wordclouds_full_path)
							if os.path.isfile(os.path.join(topic_wordclouds_full_path, img_fn))
							and img_fn != '.DS_Store'
						]
topic_wordcloud_fns.sort()

# count each term's document frequency
docs_containing = {} # e.g. docs_containing[WORD] = INT for each word in vocab
for doc_id in doc_ids:
    doc_text = doc_fulltext[doc_id]
    doc_tokens = doc_text.split()
    doc_unique_words = list(set(doc_tokens))
    for word in doc_unique_words:
        # increment docs_containing tally
        if word in docs_containing:
            docs_containing[word] += 1
        else:
            docs_containing[word] = 1

# calculate inverse document frequencies (idf)
IDF = {} # e.g. IDF[WORD] = FLOAT for each word in vocab
for word in corpus_vocab:
    IDF[word] = math.log(num_docs / docs_containing[word])

# prepare list of stopwords (and temporarily also other error-words to exclude)
stopwords = ['iti', 'na', 'ca', 'api', 'eva', 'tad', 'tvāt', 'tat', 'hi', 'ādi', 'tu', 'vā'] # used in topic modeling
# NB: stopwords are those entirely excluded from topic modeling, such that they have no associated phi numbers
error_words = [':', '*tat', 'eva*', '*atha', ')'] # should fix in the data!

# prepare corpus_vocab_reduced to use for high-dimensional document vectors

too_rare_doc_freq_cutoff = 0.002 # larger cutoff is more exclusive
too_common_doc_freq_cutoff = 0.27 # smaller cutoff is more exclusive
# e.g. for reducing 79606 > 12967 for 20k-doc corpus, use (0.0003, 0.27); for > 1330, use (0.005, 0.27)

corpus_vocab_reduced = [
    word
    for word in corpus_vocab
        if not (word in stopwords + error_words
                or docs_containing[word]/num_docs < too_rare_doc_freq_cutoff
                or docs_containing[word]/num_docs > too_common_doc_freq_cutoff)
]
# old version based on overall word freqs and only further excluding rare words
# corpus_vocab_reduced = [
#     word
#     for word in corpus_vocab
#         if not (word in (stopwords + error_words) or freq_w[word] < 3)
# ]

# prepare dict of doc_links
doc_links = {} # e.g. doc_links[DOC_ID]['prev'] = another DOC_ID string
doc_links[doc_ids[0]] = {'prev': doc_ids[len(doc_ids)-1], 'next': doc_ids[1]}
for i in range(1, len(doc_ids)-1):
	doc_links[doc_ids[i]] = {'prev': doc_ids[i-1], 'next': doc_ids[i+1]}
doc_links[doc_ids[len(doc_ids)-1]] = {'prev': doc_ids[len(doc_ids)-2], 'next': doc_ids[0]}

# load lookup table of filenames by conventional text abbreviation
text_abbrev2fn = load_dict_from_json("assets/pramanaNLP/text_abbreviations.json")
# e.g. text_abbrev2fn[TEXT_ABBRV] = STRING

# save fresh corpus text list to file
corpus_texts_list_relative_path_fn = 'assets/pramanaNLP/corpus_texts.txt'
corpus_texts_list_full_fn = os.path.join(CURRENT_FOLDER, corpus_texts_list_relative_path_fn)
with open(corpus_texts_list_full_fn,'w') as f_out:
	f_out.write('\n'.join([abbrv+'\t'+fn for (abbrv, fn) in text_abbrev2fn.items()]))

# load lookup table of section headers by doc_id
section_labels = load_dict_from_json("assets/pramanaNLP/section_labels.json")
# e.g. section_labels[DOC_ID] = STRING

# load sister dict of doc_fulltext with original punctuation (only some!) and unsplit text
doc_original_fulltext = load_dict_from_json("assets/pramanaNLP/doc_original_fulltext.json")
# e.g. doc_original_fulltext[DOC_ID] = STRING

def parse_complex_doc_id(doc_id):
# NB: returns only first original doc id from any resizing modifications
	first_underscore_pos = doc_id.find('_')
	work_abbrv = doc_id[:first_underscore_pos]
	local_doc_id = re.search('[^_\^:]+', doc_id[first_underscore_pos+1:]).group()
	return work_abbrv, local_doc_id

# handy general function for getting max values of list in descending order
def indices_of_top_N_elements(L, N):
    return sorted(range(len(L)), key=lambda x: L[x], reverse=True)[:N]

# characterize document by (pythonic index!) numbers (INT) for max_N topics over threshold and corresponding percentage (STRING)
# for topic plot caption
def get_top_topic_indices(doc_id, max_N=5, threshold=0.03):
# return list of tuples of type (%d, %s)
    indices_of_dominant_N_topics = indices_of_top_N_elements(L=thetas[doc_id], N=max_N)
    qualifying_indices = [  i
                            for i in indices_of_dominant_N_topics
                            if thetas[doc_id][i] >= threshold
                            ]
    return qualifying_indices

def get_N_candidates_by_topic_similarity(query_id, N=500):
	query_vector = np.array(thetas[query_id])
	topic_similiarity_score = {} # e.g. topic_similiarity_score[DOC_ID] = FLOAT
	topic_candidate_vectors = []
	for doc_id in doc_ids:
		candidate_vector = np.array(thetas[doc_id]) # dimensionality = k, number of topics
		# no need to check if empty, given nature of topic model
		topic_candidate_vectors.append(candidate_vector)
		topic_similiarity_score[doc_id] = fastdist.cosine(query_vector, candidate_vector)
	sorted_results = sorted(topic_similiarity_score.items(), key=lambda item: item[1], reverse=True)
	pruned_results = sorted_results[ 1 : N+1 ] # also omit first which is query itself
	top_N_candidates_score_dict = { res[0]: res[1] for res in pruned_results }
	# e.g. top_N_candidates_score_dict[doc_id_1 STRING] = score_1 FLOAT

	# DEPRECATING...
	# results_HTML = format_doc_search_results(query_id, results_dict)

	return top_N_candidates_score_dict

# set up groups for chronological work prioritization

# pre-Dharmakīrti
period_1_works = ['AP', 'PSV', 'NS', 'SK', 'MS', 'VS', 'MMK', 'ViVy', 'YSBh', 'PDhS', 'YD', 'NPS', 'TriṃśBh', 'NV', 'ViṃśV', 'NBh']

# from Candrakīrti and Dharmakīrti to Prajñākaragupta and Jayarāśi
period_2_works = ['PPad', 'HB', 'NB', 'PV', 'PVSV', 'PVin', 'SAS', 'SP', 'VN', 'NBṬ', 'TUS', 'PSṬ', 'ŚV', 'PVA', 'YD']

# around same time as NBhū, no mutual quoting
period_3_works = ['NBhū', 'VSṬ', 'NyKal', 'NM', 'VyV']

# definitely after NBhū
period_4_works = ['ŚVK', 'AvNir']

# pre-NBhū
preferred_works = period_1_works + period_2_works

def divide_doc_id_list_by_work_priority(list_of_doc_ids_to_prune, priority_works):
	prioritized = []
	secondary = []
	for doc_id in list_of_doc_ids_to_prune:
		if parse_complex_doc_id(doc_id)[0] in priority_works:
			prioritized.append(doc_id)
		else:
			secondary.append(doc_id)
	return prioritized, secondary


# 2) compare by TF.IDF score

# first prepare function for calculating tf.idf vector for any given doc

def get_TF_IDF_vector(doc_id):
	# returns numpy array

	doc_text = doc_fulltext[doc_id]
	doc_words = doc_text.split()
	unique_doc_words = list(set(doc_words))

	total_doc_word_len = len(doc_words)

	TF_IDF_dict = {} # e.g. TF_IDF_dict[WORD] = [FLOAT, FLOAT, FLOAT, FLOAT, ... FLOAT]
	for word in unique_doc_words:
		TF_d_w = doc_words.count(word) / total_doc_word_len
		TF_IDF_dict[word] = TF_d_w * IDF[word]

	TF_IDF_vector = np.zeros( len(corpus_vocab_reduced) )
	# e.g. TF_IDF_vector[WORD] = [0, 0, 0, ... FLOAT, 0, 0, ... FLOAT, 0, ... 0]

	for word in TF_IDF_dict.keys():
		if word in corpus_vocab_reduced:
			i = corpus_vocab_reduced.index(word) # alphabetical index
			TF_IDF_vector[i] = TF_IDF_dict[word]

	return TF_IDF_vector

def rank_N_candidates_by_TF_IDF_similarity(query_id, candidate_ids):

	query_vector = get_TF_IDF_vector(query_id)
	TF_IDF_candidate_vectors = []
	TF_IDF_comparison_scores = {} # e.g. tf_idf_score[DOC_ID] = FLOAT

	for doc_id in candidate_ids:
		candidate_vector = get_TF_IDF_vector(doc_id)
		if np.all(candidate_vector == 0): continue # skip empties to avoid div_by_zero in cosine calculation
		TF_IDF_candidate_vectors.append(candidate_vector)
		TF_IDF_comparison_scores[doc_id] = fastdist.cosine(query_vector, candidate_vector)

	sorted_results = sorted(TF_IDF_comparison_scores.items(), key=lambda item: item[1], reverse=True)
	candidate_ranking_results_dict = { res[0]: res[1] for res in sorted_results }

	# print("mem_size of TF_IDF_candidate_vectors: %s" % f"{ mem_size(TF_IDF_candidate_vectors) :,d}")

	return candidate_ranking_results_dict

# HTML formatting functions

def format_top_topic_summary(doc_id, top_topic_indices):
	top_topic_summary_HTML = "<div class='container'>"
	top_topic_summary_HTML += ''.join(
		[ "<h2><small>{:.1%} <span title='{}'>{}</span> (<a href='topicExplorer#topic={}&lambda=0.8&term=' target='_blank'>#{:02}</a> <a href='{}' target='_wordcloud'>☁️</a>)</small></h2>".format(
				thetas[doc_id][i],
				topic_top_words[i],
				topic_interpretations[i],
				i+1,
				i+1,
				topic_wordcloud_fns[i]
				)
		for i in top_topic_indices
		] )
	top_topic_summary_HTML += "</div>"
	return top_topic_summary_HTML

def format_docView_link(doc_id):
	# looks like doc_id
	return "<a href='doc_search?doc_id=%s'>%s</a>" % (doc_id, doc_id)

def format_textView_link(doc_id):
	# looks like fixed string "textView"
	work_abbrv, local_doc_id = parse_complex_doc_id(doc_id)
	return "<a href='textViewer?text_abbrv=%s#%s' target='textViewer%s'>textView</a>" % (work_abbrv, local_doc_id, work_abbrv)

def format_similarity_result_columns(priority_results_list_content, secondary_results_list_content):

	# primary
	primary_result_HTML_template = "<p>%s (%.2f, %.2f) (%s)</p>"
	primary_col_HTML = ''.join( [
		primary_result_HTML_template % (
			format_docView_link(doc_id),
			results[0], results[1],
			format_textView_link(doc_id)
			)
		for doc_id, results in priority_results_list_content.items()
		] )

	# secondary
	secondary_result_HTML_template = "<p>%s (%.2f) (%s)</p>"
	secondary_col_HTML = ''.join( [
		secondary_result_HTML_template % (
			format_docView_link(doc_id),
			result,
			format_textView_link(doc_id)
			)
		for doc_id, result in secondary_results_list_content.items()
		] )

	return primary_col_HTML, secondary_col_HTML

# DEPRECATING...
# def format_doc_search_results(query_id, results_dict):
# 	results_HTML = ""
# 	results_HTML += """<br><br><h1>%s <small>(%s)</small></h1>""" % (query_id, section_labels[query_id])
# 	results_HTML += """<div class="row">"""
#
# 	browse_button_template = """
# <div class="col-md-2">
# <form method="get" action="doc_search">
# 	<input type="hidden" name="doc_id_input" value="%s" />
# 	<input type="submit" class="btn btn-block btn-primary" value="%s" />
# </form>
# </div>
# """
# 	prev_button = browse_button_template % (doc_links[query_id]['prev'], "<< " + doc_links[query_id]['prev'])
# 	results_HTML += prev_button
# 	next_button = browse_button_template % (doc_links[query_id]['next'], doc_links[query_id]['next'] + " >>")
# 	results_HTML += next_button
#
# 	results_HTML += """</div>
# <div class="row">
# <div class="col-md-6">
# """
# 	# results_HTML = "<h2>Doc “%s”</h2><br><br>" % (query_id)
# 	results_HTML += "<h2>original text</h2><br><br>"
# 	results_HTML += "<p>%s</p><br><br>" % doc_original_fulltext[query_id]
# 	results_HTML += """
# </div>
# <div class="col-md-6">
# """
# 	results_HTML += "<h2>segmented text</h2><br><br>"
# 	results_HTML += "<p>%s</p><br><br>" % doc_fulltext[query_id]
#
# 	results_HTML += """
# </div>
# <div class="row">
# <div class="col-md-4">
# """
# 	results_HTML += "<h2>Doc “%s” Topic Plot</h2><br><br>" % (query_id)
# 	relative_path_to_plot_pngs = "/assets/pramanaNLP/doc_plot_pngs/"
# 	plot_png_fn = "%s.png" % query_id
# 	plot_png_full_fn = os.path.join(relative_path_to_plot_pngs, plot_png_fn)
# 	results_HTML += """<img id="plot" src="%s" alt="oops" width="400" height="280">""" % plot_png_full_fn
#
# 	results_HTML += """
# </div>
# <div class="col-md-4">
# """
# 	list_contents = ''.join( ["<p>%s (%.2f) (%s)</p>" % (format_docView_link(doc_id), results_dict[doc_id], format_textView_link(doc_id)) for doc_id in results_dict.keys()] )
# 	results_HTML += "<h2>Similar Docs by Topic for %s</h2><br>%s" % (query_id, list_contents)
# 	results_HTML += """
# </div>"""
#
# 	return results_HTML


def get_closest_docs(query_id):

	# get N preliminary candidates by topic score (dimensionality = K, fast)
	N = 750
	preliminary_N_candidates = get_N_candidates_by_topic_similarity(query_id, N)

	# prioritize candidates
	# (for now, just by fixed time periods, later can generalize)
	priority_candidate_ids, secondary_candidate_ids = divide_doc_id_list_by_work_priority( list(preliminary_N_candidates.keys()), preferred_works )
	priority_candidates = { doc_id: preliminary_N_candidates[doc_id] for doc_id in priority_candidate_ids }
	secondary_candidates = { doc_id: preliminary_N_candidates[doc_id] for doc_id in secondary_candidate_ids }

	# further rank priority candidates by tf-idf (dimensionality = len(corpus_vocab_reduced), slow)
	priority_ranked_results = rank_N_candidates_by_TF_IDF_similarity(query_id, priority_candidates)
	priority_ranked_results_complete = {
		k: (priority_candidates[k], v)
		for k,v in priority_ranked_results.items()
	}

	# priority_results_list_content = {'PDhS_175,1_175,4': (0.966843, 0.407301), 'PDhS_255,23_256,3': (0.944751, 0.302680)}
	# secondary_results_list_content = {'NBh_0408,i_0408,iii': 0.971179, 'NS_2.1.1_2.1.6': 0.970547}

	primary_col_HTML, secondary_col_HTML = format_similarity_result_columns(
		priority_ranked_results_complete,
		secondary_candidates
		)
	results_HTML = results_HTML_template.substitute(
						query_id = query_id,
						query_section = section_labels[query_id],
						prev_doc_id = doc_links[query_id]['prev'],
						next_doc_id = doc_links[query_id]['next'],
						query_original_fulltext = doc_original_fulltext[query_id],
						query_segmented_fulltext = doc_fulltext[query_id],
						top_topics_summary=format_top_topic_summary(
							query_id,
							get_top_topic_indices(query_id, max_N=5, threshold=0.03)
							),
						priority_results_list_content = primary_col_HTML,
						secondary_results_list_content = secondary_col_HTML,
						)
	return results_HTML


def format_text_view(text_abbreviation):

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
	# for example, anything tertiary note that begins <s ...> or <S ...> (e.g. 'Seite') will be interpreted as strikethrough

	return text_HTML
