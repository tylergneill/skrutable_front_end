"""Score the two OCR body-text-only outputs against ground_truth.txt.

Computes per-page and total CER (Levenshtein distance at the character level,
whitespace preserved as-is). Run from anywhere: python3 score_ocr.py
"""

import unicodedata
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent

FILES = {
	"truth": "ground_truth.txt",
	"gcv": "skrutable_cloud_vision_ocr_body_text_only.txt",
	"sarvam": "skrutable_sarvam_ai_ocr_body_text_only.txt",
}

PAGE_RE = re.compile(r"^===\s*(\d+)\s*===\s*$")


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


def main():
	pages = {name: parse_pages(BASE / fname) for name, fname in FILES.items()}
	page_nums = sorted(pages["truth"].keys())

	for provider in ("gcv", "sarvam"):
		print(f"\n##### {provider.upper()} #####")
		tot_dist = tot_len = 0
		for p in page_nums:
			t, o = pages["truth"][p], pages[provider][p]
			dist = levenshtein(t, o)
			tot_dist += dist
			tot_len += len(t)
			print(f"  page {p}: {len(t)} chars, dist {dist}, CER {dist/len(t):.4f}")
		print(f"  TOTAL: CER {tot_dist/tot_len:.4f} ({tot_dist}/{tot_len})")


if __name__ == "__main__":
	main()
