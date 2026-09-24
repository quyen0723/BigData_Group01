# download_data.py — Fetch MovieLens 32M into data/raw/ (WBS 1.1 prerequisite)
# Gates: (0) official MD5 checksum, (1) zip integrity, (2) expected row counts (ERR2).
# Usage: .venv/bin/python scripts/download_data.py [--keep-zip]
import hashlib, sys, time, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ZIP = RAW / "ml-32m.zip"
EXTRACT_DIR = RAW / "ml-32m"
URL = "https://files.grouplens.org/datasets/movielens/ml-32m.zip"
MD5_URL = URL + ".md5"   # official checksum published by GroupLens

# FACT from PRD (dataset_expectations in configs/spark.yaml):
#   ratings 32,000,204 rows; movies 87,585; tags 2,000,072; links 87,585
# CSV line counts = data rows + 1 header each.
EXPECTED = {
    "ratings.csv": 32_000_205,
    "movies.csv": 87_586,
    "tags.csv": 2_000_073,
    "links.csv": 87_586,
}

def fail(msg):
    print(f"DOWNLOAD VERIFY: FAIL — {msg}")
    sys.exit(1)

def line_count(p: Path) -> int:
    with p.open("rb") as f:
        return sum(1 for _ in f)

def md5_of(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    keep_zip = "--keep-zip" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)

    if all((EXTRACT_DIR / f).exists() for f in EXPECTED):
        print("Raw CSVs already present — skip download.")
    else:
        if not ZIP.exists():
            print(f"Downloading {URL} (~1 GB) ...")
            t0 = time.time()
            try:
                urllib.request.urlretrieve(URL, ZIP)
            except Exception as e:
                fail(f"download error: {e}")
            print(f"Downloaded in {time.time()-t0:.0f}s, size = {ZIP.stat().st_size/1e6:.1f} MB")

        # Gate 0: official GroupLens MD5
        print("Verifying MD5 against GroupLens published checksum ...")
        try:
            official = urllib.request.urlopen(MD5_URL).read().decode().strip().split()[0].lower()
        except Exception as e:
            official = None
            print(f"WARN: could not fetch official MD5 ({e}) — relying on zip + row-count gates")
        if official:
            local = md5_of(ZIP)
            if local != official:
                fail(f"MD5 mismatch: local={local} official={official} — redownload")
            print(f"MD5 OK: {local}")

        # Gate 1: zip integrity
        print("Verifying zip integrity ...")
        try:
            bad = zipfile.ZipFile(ZIP).testzip()
            if bad is not None:
                fail(f"corrupt member in zip: {bad}")
        except zipfile.BadZipFile:
            fail("bad zip file — re-run to redownload")

        print("Extracting ...")
        with zipfile.ZipFile(ZIP) as z:
            z.extractall(RAW)
        # zip root folder is ml-32m/ already
        if not EXTRACT_DIR.exists() and (RAW / "ml-32m").exists():
            pass

    # Gate 2: row counts vs PRD expectations (ERR2 — mismatch => STOP, do not proceed)
    all_ok = True
    for name, expected in EXPECTED.items():
        p = EXTRACT_DIR / name
        if not p.exists():
            fail(f"missing file after extraction: {p}")
        n = line_count(p)
        ok = n == expected
        all_ok &= ok
        print(f"{name}: {n:,} lines (expected {expected:,}) {'OK' if ok else 'MISMATCH'}")

    if not all_ok:
        fail("row counts do not match PRD — investigate before B1.1 (ERR2)")

    if not keep_zip and ZIP.exists():
        ZIP.unlink()
        print("Removed zip (use --keep-zip to retain).")

    print("DOWNLOAD VERIFY: PASS — data/raw/ml-32m ready for B1.1")

if __name__ == "__main__":
    main()