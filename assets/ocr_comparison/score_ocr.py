"""Score the two OCR body-text-only outputs against ground_truth.txt.

Computes per-page and total CER (Levenshtein distance at the character level,
whitespace preserved as-is). Run from anywhere: python3 score_ocr.py [--verbose]
"""

import unicodedata
import sys
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent

FILES = {
	"truth": "ground_truth_body_text_only.txt",
	"gcv": "skrutable_cloud_vision_ocr_body_text_only.txt",
	"sarvam": "skrutable_sarvam_vision_ocr_body_text_only.txt",
}

FILES_WS_NORM = {
	"truth": "ground_truth_body_text_only.txt",
	"gcv": "skrutable_cloud_vision_ocr_body_text_only_whitespace_norm.txt",
	"sarvam": "skrutable_sarvam_vision_ocr_body_text_only_whitespace_norm.txt",
}

PAGE_RE = re.compile(r"^===\s*(\d+)\s*===\s*$")

VERBOSE = "--verbose" in sys.argv


def parse_pages(path):
	pages = {}
	current = None
	for line in path.read_text(encoding="utf-8").splitlines():
		m = PAGE_RE.match(line)
		if m:
			current = int(m.group(1))
			pages[current] = []
		elif current is not None:
			pages[current].append(line)
	return {k: unicodedata.normalize("NFC", "\n".join(v)) for k, v in pages.items()}


def levenshtein_matrix(a, b):
	m, n = len(a), len(b)
	dp = [list(range(n + 1))]
	for i in range(1, m + 1):
		row = [i]
		for j in range(1, n + 1):
			row.append(min(dp[i-1][j] + 1, row[j-1] + 1, dp[i-1][j-1] + (a[i-1] != b[j-1])))
		dp.append(row)
	return dp


def levenshtein(a, b):
	if len(a) < len(b):
		a, b = b, a
	prev = list(range(len(b) + 1))
	for i, ca in enumerate(a, 1):
		cur = [i]
		for j, cb in enumerate(b, 1):
			cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
		prev = cur
	return prev[-1]


def backtrace(a, b, dp):
	i, j = len(a), len(b)
	ops = []
	while i > 0 or j > 0:
		if i > 0 and j > 0 and dp[i][j] == dp[i-1][j-1] + (a[i-1] != b[j-1]):
			ops.append(("match" if a[i-1] == b[j-1] else "sub", a[i-1], b[j-1]))
			i -= 1; j -= 1
		elif i > 0 and dp[i][j] == dp[i-1][j] + 1:
			ops.append(("del", a[i-1], ""))
			i -= 1
		else:
			ops.append(("ins", "", b[j-1]))
			j -= 1
	ops.reverse()
	return ops


def show_char(c):
	if c == "\n": return "\\n"
	if c == " ":  return "\\s"
	if c == "\t": return "\\t"
	return c


def print_diff(a, b, page, provider):
	dp = levenshtein_matrix(a, b)
	ops = backtrace(a, b, dp)
	errors = [(op, ca, cb) for op, ca, cb in ops if op != "match"]
	print(f"  --- diffs page {page} ({provider}) ---")
	for op, ca, cb in errors:
		if op == "sub":
			print(f"    SUB  truth={show_char(ca)!r:8}  ocr={show_char(cb)!r}")
		elif op == "del":
			print(f"    DEL  truth={show_char(ca)!r:8}  (missing in ocr)")
		elif op == "ins":
			print(f"    INS  ocr={show_char(cb)!r:8}  (extra in ocr)")


def score(pages, label):
	page_nums = sorted(pages["truth"].keys())
	print(f"\n===== {label} =====")
	for provider in ("gcv", "sarvam"):
		print(f"\n##### {provider.upper()} #####")
		tot_dist = tot_len = 0
		for p in page_nums:
			t, o = pages["truth"][p], pages[provider][p]
			dist = levenshtein(t, o)
			tot_dist += dist
			tot_len += len(t)
			print(f"  page {p}: {len(t)} chars, dist {dist}, CER {dist/len(t):.4f}")
			if VERBOSE:
				print_diff(t, o, p, provider)
		print(f"  TOTAL: CER {tot_dist/tot_len:.4f} ({tot_dist}/{tot_len})")


def main():
	score(
		{name: parse_pages(BASE / fname) for name, fname in FILES.items()},
		"body text only (daṇḍas normalized)",
	)
	score(
		{name: parse_pages(BASE / fname) for name, fname in FILES_WS_NORM.items()},
		"body text only (whitespace also normalized)",
	)


if __name__ == "__main__":
	main()
