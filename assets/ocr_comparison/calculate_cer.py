"""Compute CER for all base_text/provider_date combos and write cer_results.json.

Traverses BASE/<base_text>/<provider_date>/ automatically.
Run from anywhere: python3 calculate_cer.py [--verbose]
"""

import unicodedata
import sys
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent

PAGE_RE = re.compile(r"^===\s*(\d+)\s*===\s*$")

VERBOSE = "--verbose" in sys.argv

SKIP_DIRS = {"scan"}


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


def compute_cer(truth_pages, ocr_pages, label=""):
	page_nums = sorted(truth_pages.keys())
	result = {}
	tot_dist = tot_len = 0
	for p in page_nums:
		t = truth_pages[p]
		o = ocr_pages.get(p, "")
		dist = levenshtein(t, o)
		tot_dist += dist
		tot_len += len(t)
		result[str(p)] = round(dist / len(t), 6) if len(t) else 0
		if VERBOSE and label:
			print(f"  page {p}: {len(t)} chars, dist {dist}, CER {dist/len(t):.4f}")
			print_diff(t, o, p, label)
	result["total"] = round(tot_dist / tot_len, 6) if tot_len else 0
	return result


def main():
	output = {}

	base_text_dirs = sorted(
		d for d in BASE.iterdir()
		if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
	)

	for bt_dir in base_text_dirs:
		bt_name = bt_dir.name
		gt_raw_path = bt_dir / "ground_truth.txt"
		gt_norm_path = bt_dir / "ground_truth_normalized.txt"

		if not gt_raw_path.exists():
			print(f"[skip] {bt_name}: no ground_truth.txt")
			continue

		truth_raw = parse_pages(gt_raw_path)
		truth_norm = parse_pages(gt_norm_path) if gt_norm_path.exists() else truth_raw

		providers = {}
		provider_dirs = sorted(
			d for d in bt_dir.iterdir()
			if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
		)

		for prov_dir in provider_dirs:
			prov_name = prov_dir.name
			raw_path = prov_dir / "ocr_raw.txt"
			norm_path = prov_dir / "ocr_normalized.txt"

			if not raw_path.exists():
				print(f"[skip] {bt_name}/{prov_name}: no ocr_raw.txt")
				continue

			ocr_raw = parse_pages(raw_path)
			ocr_norm = parse_pages(norm_path) if norm_path.exists() else ocr_raw

			print(f"\n##### {bt_name} / {prov_name} #####")
			cer_raw = compute_cer(truth_raw, ocr_raw, f"{prov_name} raw")
			cer_norm = compute_cer(truth_norm, ocr_norm, f"{prov_name} norm")
			print(f"  CER raw:        {cer_raw['total']:.4f}")
			print(f"  CER normalized: {cer_norm['total']:.4f}")

			providers[prov_name] = {
				"cer_raw": cer_raw,
				"cer_normalized": cer_norm,
			}

		output[bt_name] = {
			"ground_truth_pages": sorted(truth_raw.keys()),
			"providers": providers,
			"table_rows": [],
		}

	out_path = BASE / "cer_results.json"
	out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"\nWrote {out_path}")


if __name__ == "__main__":
	main()
