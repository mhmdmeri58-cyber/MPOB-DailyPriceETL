import os
import requests
import pandas as pd
from datetime import date
import calendar

WEBSITE_FOLDER = r"C:\xampp\htdocs\FYP"
JSON_PATH   = os.path.join(WEBSITE_FOLDER, "mpob_daily.json")
MASTER_CSV  = os.path.join(WEBSITE_FOLDER, "mpob_master.csv")

# ── Column names exactly as MPOB publishes them ──────────────
REGION_COLS = [
    "North / Utara",
    "South / Selatan",
    "Central / Tengah",
    "East Coast / Timur",
    "Sabah",
    "Sarawak*",
]
ALL_COLS = ["Date"] + REGION_COLS

def build_url():
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return (
        f"https://price.mpob.gov.my/excel/daily/ffb/"
        f"{today.year}{today.month:02d}{last_day:02d}"
    )

def download_excel(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://price.mpob.gov.my/daily",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    print(f"Download status: {r.status_code}")
    xlsx_path = os.path.join(WEBSITE_FOLDER, "mpob_latest.xlsx")
    with open(xlsx_path, "wb") as f:
        f.write(r.content)
    return xlsx_path

def parse_excel(xlsx_path):
    raw = pd.read_excel(xlsx_path, header=None)

    # ── Extract year + month from the title row ───────────────
    title = str(raw.iloc[0, 0])
    # Title looks like: "...BST...\nJune 2026" — take the last line
    month_year = title.strip().split("\n")[-1].strip()
    period = pd.to_datetime(month_year, format="%B %Y")
    year   = period.year
    month  = period.month
    last_valid_day = calendar.monthrange(year, month)[1]

    print(f"Parsed period: {month_year}  ({year}-{month:02d}, days 1-{last_valid_day})")

    # ── Build data frame ──────────────────────────────────────
    # Row 1 = header row, rows 2+ = data
    df = raw.iloc[2:].copy()
    df.columns = raw.iloc[1].tolist()
    df = df.reset_index(drop=True)

    # Rename first column to Day
    df.rename(columns={df.columns[0]: "Day"}, inplace=True)

    # ── CRITICAL FIX 1: keep ONLY rows where Day is an integer
    #   between 1 and the last calendar day of the parsed month.
    #   This drops the "summary / projection" rows at the bottom of
    #   the Excel sheet that have small integers like 1-5 for months
    #   that don't belong to the current download period.
    df["Day"] = pd.to_numeric(df["Day"], errors="coerce")
    df = df[df["Day"].notna()].copy()
    df["Day"] = df["Day"].astype(int)
    df = df[(df["Day"] >= 1) & (df["Day"] <= last_valid_day)]

    # ── Build dates ───────────────────────────────────────────
    df["Date"] = df["Day"].apply(
        lambda d: f"{year}-{month:02d}-{d:02d}"
    )

    # ── CRITICAL FIX 2: drop any date that is in the future ──
    today_str = date.today().strftime("%Y-%m-%d")
    df = df[df["Date"] <= today_str]

    # ── Keep only the columns we care about ──────────────────
    df = df[ALL_COLS].copy()

    # Normalise region values: strip whitespace, leave PH/NT as-is,
    # convert empty / NaN to empty string
    for col in REGION_COLS:
        df[col] = df[col].fillna("").astype(str).str.strip()

    print(f"Kept {len(df)} rows after filtering (1 to {last_valid_day}, not future)")
    print(df.head(10).to_string())
    return df

def merge_and_deduplicate(df_new):
    date_col = "Date"

    # ── CRITICAL FIX 3: always read/write dates as YYYY-MM-DD strings ──
    # Never use format='mixed' or dayfirst=True — those cause
    # silent misinterpretation of ambiguous dates.
    if os.path.exists(MASTER_CSV):
        df_master = pd.read_csv(
            MASTER_CSV,
            dtype=str,          # read everything as string — no auto-parsing
            keep_default_na=False,
        )
        # Validate master dates: drop any that don't parse as YYYY-MM-DD
        def safe_parse(s):
            try:
                return pd.to_datetime(s, format="%Y-%m-%d")
            except Exception:
                return pd.NaT

        df_master[date_col] = df_master[date_col].apply(safe_parse)
        df_master = df_master[df_master[date_col].notna()].copy()

        # Ensure new data dates are also datetime for comparison
        df_new[date_col] = pd.to_datetime(df_new[date_col], format="%Y-%m-%d")

        df_combined = pd.concat([df_master, df_new], ignore_index=True)
    else:
        df_new[date_col] = pd.to_datetime(df_new[date_col], format="%Y-%m-%d")
        df_combined = df_new.copy()

    # ── CRITICAL FIX 4: drop future dates from master too ────
    # Guards against any previously-saved phantom rows.
    today_dt = pd.Timestamp(date.today())
    df_combined = df_combined[df_combined[date_col] <= today_dt].copy()

    # Deduplicate — newer run wins (keep="last" after sorting by date ascending)
    df_combined = df_combined.sort_values(date_col, ascending=True)
    df_combined = df_combined.drop_duplicates(subset=[date_col], keep="last")

    # ── CRITICAL FIX 5: save dates as plain YYYY-MM-DD strings ──
    # to_csv with datetime objects can write "2026-06-05 00:00:00"
    # which then requires format='mixed' to read back — the root
    # cause of the dayfirst ambiguity bug.
    df_combined[date_col] = df_combined[date_col].dt.strftime("%Y-%m-%d")

    # Sort newest-first for CSV readability
    df_combined = df_combined.sort_values(date_col, ascending=False)

    # Save master CSV
    df_combined.to_csv(MASTER_CSV, index=False)
    print(f"Master CSV saved: {len(df_combined)} rows")

    # Save JSON (newest-first, same order)
    df_combined.to_json(JSON_PATH, orient="records", indent=2, force_ascii=False)
    print(f"✅ Done! JSON saved: {len(df_combined)} rows → {JSON_PATH}")

    # Quick sanity check: flag any future dates that snuck through
    today_str = date.today().strftime("%Y-%m-%d")
    future = df_combined[df_combined[date_col] > today_str]
    if not future.empty:
        print(f"⚠️  WARNING: {len(future)} future date(s) found after save:")
        print(future[date_col].tolist())
    else:
        print("✅ Sanity check passed: no future dates in output.")

def clean_master_csv():
    """
    One-time cleanup: removes all future-dated rows from an already-
    corrupted master CSV.  Run this once to fix the existing file,
    then the main() function keeps it clean going forward.
    """
    if not os.path.exists(MASTER_CSV):
        print("No master CSV found.")
        return

    df = pd.read_csv(MASTER_CSV, dtype=str, keep_default_na=False)
    date_col = "Date"
    before = len(df)
    today_str = date.today().strftime("%Y-%m-%d")
    df = df[df[date_col] <= today_str]
    after = len(df)
    df.to_csv(MASTER_CSV, index=False)
    print(f"Cleaned master CSV: removed {before - after} future row(s). {after} remain.")


def main():
    # ── Step 0: clean any existing corruption first ───────────
    clean_master_csv()

    # ── Step 1: download current month's Excel ────────────────
    url = build_url()
    print(f"Downloading: {url}")
    xlsx_path = download_excel(url)

    # ── Step 2: parse and filter ──────────────────────────────
    df_new = parse_excel(xlsx_path)

    # ── Step 3: merge and save ────────────────────────────────
    merge_and_deduplicate(df_new)


main()