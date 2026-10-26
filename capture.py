"""Section 1.2: capture the five generator streams to CSV, one row at a time.

  .venv\\Scripts\\python.exe capture.py --preview   # dataset_info, FIELDS, 10 rows per stream
  .venv\\Scripts\\python.exe capture.py             # full capture to data/csv + audit

The generator is imported unchanged. Rows are written as they arrive, so the
full stream is never held in memory. Results go to results/capture_audit.json
and the full console log to logs/capture.log.
"""
import argparse
import csv
import hashlib
import json
import logging
import sys
import time
from datetime import datetime
from itertools import islice
from pprint import pformat
from zoneinfo import ZoneInfo

import mobile_money_generator as g

import config

STREAMS = ("customers", "accounts", "devices", "account_devices", "transfers")
EXPECTED = {"customers": 228_000, "accounts": 248_000, "devices": 228_600,
            "account_devices": 285_600, "transfers": 20_003_300}
LOG_EVERY = 1_000_000
CAT = ZoneInfo(config.TZ)

log = logging.getLogger("capture")


def setup_logging(name):
    config.LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(config.LOG_DIR / name, mode="w", encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def stream(name):
    return getattr(g, f"iter_{name}")()  # a fresh call restarts the stream


def cat(epoch):
    return datetime.fromtimestamp(epoch, CAT).isoformat()


def preview():
    log.info("dataset_info():\n%s", pformat(g.dataset_info(), sort_dicts=False))
    log.info("FIELDS:\n%s", pformat(g.FIELDS, sort_dicts=False))
    for name in STREAMS:
        log.info("--- iter_%s() first 10 records", name)
        for row in islice(stream(name), 10):
            log.info("%s", row)


def capture_stream(name):
    path = config.CSV_DIR / f"{name}.csv"
    consumed = written = 0
    audit = None
    if name == "transfers":
        audit = {"count": 0, "earliest_occurred_at": None, "latest_occurred_at": None,
                 "sum_amount_rwf": 0}

    started = time.perf_counter()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=g.FIELDS[name])
        writer.writeheader()
        for row in stream(name):
            consumed += 1
            writer.writerow(row)
            written += 1
            if audit is not None:
                t = row["occurred_at"]
                audit["count"] += 1
                audit["sum_amount_rwf"] += row["amount_rwf"]
                if audit["earliest_occurred_at"] is None or t < audit["earliest_occurred_at"]:
                    audit["earliest_occurred_at"] = t
                if audit["latest_occurred_at"] is None or t > audit["latest_occurred_at"]:
                    audit["latest_occurred_at"] = t
                if written % LOG_EVERY == 0:
                    log.info("  transfers written: %s (%.1f s)", f"{written:,}",
                             time.perf_counter() - started)
    seconds = time.perf_counter() - started

    size = path.stat().st_size
    result = {"file": str(path.relative_to(config.ROOT)), "consumed": consumed, "written": written,
              "expected": EXPECTED[name], "matches": consumed == written == EXPECTED[name],
              "capture_seconds": round(seconds, 2), "csv_bytes": size, "csv_gb": round(size / 1e9, 3)}
    if audit is not None:
        audit["earliest_cat"] = cat(audit["earliest_occurred_at"])
        audit["latest_cat"] = cat(audit["latest_occurred_at"])
        result["audit"] = audit
    log.info("%-16s consumed=%-12s written=%-12s expected=%-12s %s  %.1f s  %.3f GB",
             name, f"{consumed:,}", f"{written:,}", f"{EXPECTED[name]:,}",
             "OK" if result["matches"] else "MISMATCH", seconds, size / 1e9)
    return result


def capture():
    config.CSV_DIR.mkdir(parents=True, exist_ok=True)
    config.RESULTS_DIR.mkdir(exist_ok=True)
    started_at = datetime.now(CAT)
    log.info("Capture started %s", started_at.isoformat(timespec="seconds"))

    results = {}
    for name in STREAMS:
        log.info("Capturing %s ...", name)
        results[name] = capture_stream(name)

    total_rows = sum(r["written"] for r in results.values())
    total_bytes = sum(r["csv_bytes"] for r in results.values())
    total_seconds = sum(r["capture_seconds"] for r in results.values())
    audit = results["transfers"]["audit"]
    summary = {
        "started_cat": started_at.isoformat(timespec="seconds"),
        "finished_cat": datetime.now(CAT).isoformat(timespec="seconds"),
        "generator_sha256": hashlib.sha256((config.ROOT / "mobile_money_generator.py").read_bytes()).hexdigest(),
        "streams": results,
        "total_rows": total_rows, "total_rows_expected": 20_993_500,
        "total_capture_seconds": round(total_seconds, 2),
        "total_csv_bytes": total_bytes, "total_csv_gb": round(total_bytes / 1e9, 3),
        "all_match": all(r["matches"] for r in results.values()) and total_rows == 20_993_500,
    }
    (config.RESULTS_DIR / "capture_audit.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    log.info("=" * 96)
    log.info("%-16s %14s %14s %14s %8s %10s %9s", "stream", "consumed", "written", "expected",
             "status", "seconds", "CSV GB")
    for name, r in results.items():
        log.info("%-16s %14s %14s %14s %8s %10.1f %9.3f", name, f"{r['consumed']:,}", f"{r['written']:,}",
                 f"{r['expected']:,}", "OK" if r["matches"] else "MISMATCH", r["capture_seconds"], r["csv_gb"])
    log.info("%-16s %14s %14s %14s %8s %10.1f %9.3f", "TOTAL", "", f"{total_rows:,}", "20,993,500",
             "OK" if summary["all_match"] else "MISMATCH", total_seconds, total_bytes / 1e9)
    log.info("Transfer audit: count=%s  earliest=%s (%s)  latest=%s (%s)  sum_amount_rwf=%s",
             f"{audit['count']:,}", audit["earliest_occurred_at"], audit["earliest_cat"],
             audit["latest_occurred_at"], audit["latest_cat"], f"{audit['sum_amount_rwf']:,}")
    log.info("Saved results/capture_audit.json")
    return summary["all_match"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", action="store_true", help="show dataset_info, FIELDS and 10 rows per stream")
    args = parser.parse_args()
    if args.preview:
        setup_logging("capture_preview.log")
        preview()
    else:
        setup_logging("capture.log")
        sys.exit(0 if capture() else 1)


if __name__ == "__main__":
    main()
