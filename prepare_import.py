"""Section 3.2 step 1: make temporary Neo4j import copies of the captured CSVs.

The source CSVs in data/csv stay unchanged. Each copy gets a Neo4j typed
header; data rows are copied as they are, streamed line by line.
owns.csv is derived from accounts.csv in (customer_id, account_id) order.

  .venv\\Scripts\\python.exe prepare_import.py            # write import/*.csv
  .venv\\Scripts\\python.exe prepare_import.py --clean    # remove the temporary copies
"""
import argparse
import csv
import shutil
import time
from itertools import islice

import config

IMPORT_DIR = config.ROOT / "import"

# source file -> (import file, typed header in the same column order as the source)
COPIES = {
    "customers.csv":       ("customers.csv",   "customer_id:ID(Customer),region:string"),
    "accounts.csv":        ("accounts.csv",    "account_id:ID(Account),:IGNORE,role:string"),
    "devices.csv":         ("devices.csv",     "device_id:ID(Device),access_type:string"),
    "account_devices.csv": ("used_device.csv", ":START_ID(Account),:END_ID(Device),"
                                               "first_day:int,last_day:int,observations:int"),
    "transfers.csv":       ("transfers.csv",   "transfer_id:long,:START_ID(Account),:END_ID(Account),"
                                               "occurred_at:long,amount_rwf:int"),
}
OWNS_HEADER = ":START_ID(Customer),:END_ID(Account)"


def copy_with_header(src, dst, header, limit=None):
    rows = 0
    with open(src, encoding="utf-8", newline="") as fin, open(dst, "w", encoding="utf-8", newline="") as fout:
        next(fin)                      # drop the plain source header
        fout.write(header + "\n")
        for line in islice(fin, limit):
            fout.write(line if line.endswith("\n") else line + "\n")
            rows += 1
    return rows


def write_owns(src, dst):
    with open(src, encoding="utf-8", newline="") as f:
        pairs = sorted((int(r["customer_id"]), int(r["account_id"])) for r in csv.DictReader(f))
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write(OWNS_HEADER + "\n")
        f.writelines(f"{c},{a}\n" for c, a in pairs)
    return len(pairs)


def prepare(out_dir, sample=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for src_name, (dst_name, header) in COPIES.items():
        t0 = time.perf_counter()
        limit = sample if (sample and src_name == "transfers.csv") else None
        n = copy_with_header(config.CSV_DIR / src_name, out_dir / dst_name, header, limit)
        print(f"{dst_name:<18}{n:>14,} rows  {time.perf_counter() - t0:6.1f} s   header: {header}")
    t0 = time.perf_counter()
    n = write_owns(config.CSV_DIR / "accounts.csv", out_dir / "owns.csv")
    print(f"{'owns.csv':<18}{n:>14,} rows  {time.perf_counter() - t0:6.1f} s   header: {OWNS_HEADER}")
    print(f"Prepared import copies in {out_dir} in {time.perf_counter() - started:.1f} s "
          f"(source CSVs in {config.CSV_DIR} unchanged)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clean", action="store_true", help="delete the temporary import copies")
    parser.add_argument("--out-dir", default=str(IMPORT_DIR), help=argparse.SUPPRESS)
    parser.add_argument("--sample", type=int, help=argparse.SUPPRESS)  # testing only
    args = parser.parse_args()
    if args.clean:
        shutil.rmtree(IMPORT_DIR, ignore_errors=True)
        print(f"Removed temporary import copies: {IMPORT_DIR}")
    else:
        from pathlib import Path
        prepare(Path(args.out_dir), args.sample)


if __name__ == "__main__":
    main()
