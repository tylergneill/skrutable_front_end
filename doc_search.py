import math
import numpy as np
from collections import OrderedDict, Counter
from copy import copy
from fastdist import fastdist

# get theta data
with open('theta.tsv','r') as f_in:
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
with open('phi.csv','r') as f_in:
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

def format_doc_search_results(results_dict):
	results_HTML = "<ol>%s</ol>"
	list_contents = ''.join( ["<li>%s:%f</li>" % (id, results_dict[id]) for id in results_dict.keys()] )
	return results_HTML % list_contents

def compare_by_topic(query_id):
	N = 10 # number of closest docs to find
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
	results_HTML = format_doc_search_results(results_dict)
	return results_HTML
