#!/usr/bin/env python3
"""
bulk_vision_runner.py - page-aware version (robust page counting) + skip-existing + tqdm
Logs and CSV use only file basenames (no full paths) for readability.
Created with ChatGPT 5.

Usage examples:
  python bulk_vision_runner.py --root /path/to/pdfs --dry-run
  python bulk_vision_runner.py --root /path/to/pdfs --workers 10 --mode process --out-dir ./ocr_results --api-key "$MY_API_KEY"

Dependencies:
  pip install pypdf tqdm
  brew install poppler          # macOS (optional for pdfinfo)
  sudo apt install poppler-utils # Debian/Ubuntu (optional)
"""
import argparse
import csv
import logging
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List

from tqdm import tqdm

# import your existing OCR function
from ocr_service import run_google_ocr

# Try to import pypdf for best page counting
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

# ---- settings ----
DEFAULT_OUT_DIR = Path("ocr_output")
LOG_CSV = "ocr_run_log.csv"

# ---- page-count helpers ----
def _pdfinfo_pages(pdf_path: Path) -> int:
    """Return page count using the 'pdfinfo' command, or -1 if unavailable/error."""
    try:
        proc = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        return -1
    except Exception:
        return -1
    if proc.returncode != 0:
        return -1
    out = proc.stdout
    m = re.search(r"Pages:\s+(\d+)", out)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return -1
    return -1

def _heuristic_pages(pdf_path: Path) -> int:
    """
    Fallback heuristic: read the first chunk of the file and count occurrences of common page markers.
    This is imperfect but better than returning zero for many PDFs.
    """
    try:
        with open(pdf_path, "rb") as fh:
            data = fh.read(2000000)  # read up to ~2MB
        counts = []
        counts.append(data.count(b"/Type /Page"))
        # find any explicit /Count N entries
        try:
            counts += [int(m.group(1)) for m in re.finditer(br"/Count\s+(\d+)", data)]
        except Exception:
            pass
        counts.append(data.count(b"/MediaBox"))
        # some PDFs have /Pages <n>
        try:
            m = re.search(br"/Pages\s+(\d+)", data)
            if m:
                counts.append(int(m.group(1)))
        except Exception:
            pass

        best = 0
        if counts:
            # choose a plausible positive count
            best = max([c for c in counts if isinstance(c, int) and c >= 0] + [0])
        return int(best)
    except Exception:
        return 0

def pdf_page_count(pdf_path: Path) -> int:
    """
    Robust page-count:
     1) Try pypdf (PdfReader)
     2) Try pdfinfo (poppler)
     3) Heuristic fallback
    Returns integer >= 0. Uses logging.debug to record which method produced the result.
    """
    # 1) pypdf if available
    if PdfReader is not None:
        try:
            reader = PdfReader(str(pdf_path))
            # prefer explicit pages list if available
            try:
                n = len(reader.pages)
                if isinstance(n, int) and n >= 0:
                    logging.debug("pdf_page_count: pypdf -> %d for %s", n, pdf_path)
                    return int(n)
            except Exception:
                pass
            # older versions might have getNumPages
            if hasattr(reader, "getNumPages"):
                try:
                    n = reader.getNumPages()
                    logging.debug("pdf_page_count: pypdf.getNumPages -> %d for %s", n, pdf_path)
                    return int(n)
                except Exception:
                    pass
        except Exception:
            # Try decrypting with empty password if encrypted (common)
            try:
                reader = PdfReader(str(pdf_path))
                if getattr(reader, "is_encrypted", False):
                    try:
                        reader.decrypt("")  # try empty password
                        n = len(reader.pages)
                        logging.debug("pdf_page_count: pypdf (decrypted) -> %d for %s", n, pdf_path)
                        return int(n)
                    except Exception:
                        pass
            except Exception:
                pass
            # fall through to next methods

    # 2) pdfinfo fallback
    n = _pdfinfo_pages(pdf_path)
    if isinstance(n, int) and n > 0:
        logging.debug("pdf_page_count: pdfinfo -> %d for %s", n, pdf_path)
        return int(n)

    # 3) heuristic fallback
    n = _heuristic_pages(pdf_path)
    logging.debug("pdf_page_count: heuristic -> %d for %s", n, pdf_path)
    return int(n)

# ---- utilities ----
def find_pdfs(root: Path) -> List[Path]:
    return sorted([p for p in root.rglob("*.pdf") if p.is_file()])

def ensure_outpath(root: Path, pdf: Path, out_dir: Path) -> Path:
    """
    Return an output Path that mirrors the pdf's relative path under out_dir,
    but with the .pdf suffix replaced by .txt (so 'foo.pdf' -> 'foo.txt').
    """
    rel = pdf.relative_to(root)          # e.g. "subdir/foo.pdf"
    out_rel = rel.with_suffix(".txt")    # "subdir/foo.txt"
    outpath = out_dir / out_rel
    outpath.parent.mkdir(parents=True, exist_ok=True)
    return outpath

def write_text(path: Path, text: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def _join_pages_with_separators(pages_iterable):
    """Return a single string joining pages with separators '=== n ==='."""
    parts = []
    for i, ptxt in enumerate(pages_iterable, 1):
        # ensure ptxt is a string
        if ptxt is None:
            ptxt = ""
        parts.append(f"=== {i} ===\n{str(ptxt).strip()}")
    return "\n\n".join(parts)

# This wrapper is picklable (module-level) so it can be used with ProcessPoolExecutor
def worker_task(args_tuple):
    """
    args_tuple: (
       pdf_path_str,
       api_key,
       include_page_numbers,
       root_str,
       out_dir_str,
       max_retries,
       sleep_base,
       pages_int
    )
    returns (pdf_path_str, outpath_str, pages_int, status_str, error_message_or_empty, start_ts, end_ts)
    Note: pdf_path_str/outpath_str in the returned tuple are full paths (used internally),
    but the main runner writes only basenames into logs/CSV for readability.
    """
    import traceback, time, os, threading, datetime
    pdf_path_str, api_key, include_page_numbers, root_str, out_dir_str, max_retries, sleep_base, pages = args_tuple
    pdf_path = Path(pdf_path_str)
    out_dir = Path(out_dir_str)
    root = Path(root_str)

    outpath = ensure_outpath(root, pdf_path, out_dir)

    pid = os.getpid()
    tname = threading.current_thread().name

    start_ts = datetime.datetime.utcnow().isoformat() + "Z"
    logging.info("START: %s PID=%d THREAD=%s pages=%d", pdf_path.name, pid, tname, pages)

    attempt = 0
    last_exc = ""
    while attempt <= max_retries:
        try:
            res = run_google_ocr(pdf_path, api_key=api_key, include_page_numbers=include_page_numbers)

            # Race-check: if file exists by the time we write, skip to avoid overwrite
            if outpath.exists():
                end_ts = datetime.datetime.utcnow().isoformat() + "Z"
                logging.info("SKIP-WRITE (exists): %s PID=%d THREAD=%s", outpath.name, pid, tname)
                return (str(pdf_path), str(outpath), pages, "SKIPPED-RACE", "", start_ts, end_ts)

            # atomic write (temp + replace)
            tmp = outpath.with_suffix(outpath.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(res)
            try:
                os.replace(tmp, outpath)
            except Exception:
                # fallback to simple write
                write_text(outpath, res)

            end_ts = datetime.datetime.utcnow().isoformat() + "Z"
            try:
                start_dt = datetime.datetime.fromisoformat(start_ts.replace("Z",""))
                end_dt = datetime.datetime.fromisoformat(end_ts.replace("Z",""))
                elapsed = (end_dt - start_dt).total_seconds()
            except Exception:
                elapsed = None
            logging.info("END: %s PID=%d THREAD=%s status=SUCCESS pages=%d elapsed=%.2f s", pdf_path.name, pid, tname, pages, elapsed if elapsed else 0.0)
            return (str(pdf_path), str(outpath), pages, "SUCCESS", "", start_ts, end_ts)
        except Exception:
            attempt += 1
            last_exc = traceback.format_exc()
            wait = sleep_base * (2 ** (attempt - 1))
            logging.warning("RETRY %d for %s (sleep %.1fs)", attempt, pdf_path.name, wait)
            time.sleep(wait)

    end_ts = datetime.datetime.utcnow().isoformat() + "Z"
    try:
        start_dt = datetime.datetime.fromisoformat(start_ts.replace("Z",""))
        end_dt = datetime.datetime.fromisoformat(end_ts.replace("Z",""))
        elapsed = (end_dt - start_dt).total_seconds()
    except Exception:
        elapsed = None
    logging.error("END: %s PID=%d THREAD=%s status=FAIL pages=%d elapsed=%.2f s", pdf_path.name, pid, tname, pages, elapsed if elapsed else 0.0)
    return (str(pdf_path), str(outpath), pages, "FAIL", last_exc, start_ts, end_ts)

# ---- main runner ----
def main():
    p = argparse.ArgumentParser(description="Bulk runner for Google Vision OCR using your ocr_service.run_google_ocr (page-aware)")
    p.add_argument("--root", required=True, type=Path, help="Root folder containing subfolders of PDFs")
    p.add_argument("--workers", type=int, default=10, help="Number of parallel workers")
    p.add_argument("--mode", choices=("thread", "process"), default="thread",
                   help="Concurrency mode: 'thread' (lighter) or 'process' (more isolation)")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory for .txt files")
    p.add_argument("--api-key", default=os.getenv("VISION_API_KEY", ""), help="Vision API key (or leave blank to use ADC)")
    p.add_argument("--include-page-numbers", action="store_true", help="Insert page separators '=== n ===' where possible")
    p.add_argument("--dry-run", action="store_true", help="List files (with page counts) and exit")
    p.add_argument("--max-retries", type=int, default=3, help="Max retries per file on error")
    p.add_argument("--sleep-base", type=float, default=1.0, help="Base seconds for exponential backoff")
    p.add_argument("--log-csv", default=LOG_CSV, help="CSV log path for successes/errors")
    p.add_argument("--show-first", type=int, default=20, help="In dry-run show per-file page counts for the first N files")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    root = args.root.resolve()
    out_dir = args.out_dir.resolve()
    api_key = args.api_key or None

    if not root.exists():
        logging.error("Root folder does not exist: %s", root)
        sys.exit(1)

    pdfs = find_pdfs(root)
    logging.info("Found %d PDF files under %s", len(pdfs), root)

    # Count pages for each PDF (this can take a little time on large sets).
    logging.info("Counting pages for each PDF (this may take a moment)...")
    pdfs_with_pages = []
    total_pages = 0
    for pth in pdfs:
        try:
            pages = pdf_page_count(pth)
        except Exception:
            pages = 0
        pdfs_with_pages.append((pth, pages))
        total_pages += pages

    if args.dry_run:
        # Summary totals
        total_files = len(pdfs_with_pages)
        print(f"DRY RUN: {total_files} PDF files found under {root}")
        print(f"Total pages across all PDFs: {total_pages}")
        print(f"Average pages per PDF: {total_pages / max(1, total_files):.2f}\n")

        # Compute what will actually be done: skipped vs run
        to_run = []
        skipped = []
        pages_to_run = 0
        for pth, pages in pdfs_with_pages:
            print(type(str(pth)), type(pages))
            print(str(pth))
            exit()

            # compute corresponding .txt path without creating directories
            rel = pth.relative_to(root)
            out_rel = rel.with_suffix(".txt")
            outpath = out_dir / out_rel

            if outpath.exists():
                skipped.append((pth.name, pages))
            else:
                to_run.append((pth.name, pages))
                pages_to_run += int(pages)

        run_count = len(to_run)
        skip_count = len(skipped)

        print(f"Will RUN:  {run_count} files  (total pages to process: {pages_to_run})")
        print(f"Will SKIP: {skip_count} files  (already have .txt outputs)\n")

        # show examples
        show_n = min(args.show_first, len(pdfs_with_pages))
        if run_count:
            print(f"First {min(show_n, run_count)} files that WOULD BE RUN:")
            for name, pages in to_run[:show_n]:
                print(f"  {name} — {pages} pages")
            print("")
        else:
            print("No files would be run (every PDF already has a .txt output).\n")

        if skip_count:
            print(f"First {min(show_n, skip_count)} files that WOULD BE SKIPPED:")
            for name, pages in skipped[:show_n]:
                print(f"  {name} — {pages} pages")
            print("")

        print("Dry-run: done. No files were written and no directories were created.")
        return

    # Ensure out_dir exists up front
    out_dir.mkdir(parents=True, exist_ok=True)

    # write header to CSV log (append mode). New header includes start/end/duration.
    header_needed = not Path(args.log_csv).exists()
    with open(args.log_csv, "a", newline="", encoding="utf-8") as csvf:
        writer = csv.writer(csvf)
        if header_needed:
            writer.writerow(["timestamp", "pdf_name", "out_name", "pages", "status", "error", "start_ts", "end_ts", "duration_s"])

    # Prepare tasks and skip any that already have .txt output.
    tasks = []
    pages_in_total = 0
    skipped_count = 0

    # We'll report total progress over all PDFs (including skipped) so the user sees overall completion.
    total_files = len(pdfs_with_pages)

    # Use tqdm to track the whole set
    pbar = tqdm(total=total_files, unit="file", desc="Overall progress")

    for pth, pages in pdfs_with_pages:
        outpath = ensure_outpath(root, pth, out_dir)
        if outpath.exists():
            # log skip to CSV (use basenames)
            with open(args.log_csv, "a", newline="", encoding="utf-8") as csvf:
                writer = csv.writer(csvf)
                writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), pth.name, outpath.name, pages, "SKIPPED", ""])
            skipped_count += 1
            logging.info("SKIP (exists): %s -> %s", pth.name, outpath.name)
            pbar.update(1)
            continue
        # otherwise queue task
        tasks.append((str(pth), api_key, args.include_page_numbers, str(root), str(out_dir), args.max_retries, args.sleep_base, int(pages)))
        pages_in_total += int(pages)

    logging.info("Prepared %d tasks (skipped %d) covering %d total pages.", len(tasks), skipped_count, pages_in_total)
    logging.info("Starting %s executor with %d workers", args.mode, args.workers)

    executor_cls = ThreadPoolExecutor if args.mode == "thread" else ProcessPoolExecutor

    # Submit
    futures = []
    with executor_cls(max_workers=args.workers) as ex:
        for t in tasks:
            futures.append(ex.submit(worker_task, t))

        # Each time a future completes, update the pbar (skipped files were already counted).
        for fut in as_completed(futures):
            try:
                pdf_path_str, outpath_str, pages, status, error_msg, start_ts, end_ts = fut.result()
            except Exception:
                logging.exception("Unexpected worker exception")
                pbar.update(1)
                continue

            # compute duration safely
            try:
                import datetime
                start_dt = datetime.datetime.fromisoformat(start_ts.replace("Z",""))
                end_dt = datetime.datetime.fromisoformat(end_ts.replace("Z",""))
                duration = (end_dt - start_dt).total_seconds()
            except Exception:
                duration = None

            # Log to CSV with basenames
            with open(args.log_csv, "a", newline="", encoding="utf-8") as csvf:
                writer = csv.writer(csvf)
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    Path(pdf_path_str).name,
                    Path(outpath_str).name,
                    pages,
                    status,
                    error_msg.replace("\n","<NL>") if error_msg else "",
                    start_ts,
                    end_ts,
                    f"{duration:.2f}" if duration is not None else ""
                ])

            if status == "SUCCESS":
                logging.info("COMPLETED: %s -> %s (%d pages) duration=%.2fs", Path(pdf_path_str).name, Path(outpath_str).name, pages, duration if duration else 0.0)
            elif status == "FAIL":
                logging.error("FAILED: %s -> %s (%d pages) duration=%.2fs (see log)", Path(pdf_path_str).name, Path(outpath_str).name, pages, duration if duration else 0.0)
            else:
                logging.info("%s: %s -> %s (%d pages) duration=%.2fs", status, Path(pdf_path_str).name, Path(outpath_str).name, pages, duration if duration else 0.0)

            pbar.update(1)

    pbar.close()
    logging.info("All tasks submitted. Check %s for per-file logs. %d files skipped.", args.log_csv, skipped_count)


if __name__ == "__main__":
    main()
