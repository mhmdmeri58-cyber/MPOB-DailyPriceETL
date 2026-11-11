import os
import requests
import pandas as pd
from datetime import date
import calendar

WEBSITE_FOLDER = r"C:\xampp\htdocs\FYP"
JSON_PATH = os.path.join(WEBSITE_FOLDER, "mpob_daily.json")
MASTER_CSV = os.path.join(WEBSITE_FOLDER, "mpob_master.csv")

def build_url(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return f"https://price.mpob.gov.my/excel/daily/ffb/{year}{month:02d}{last_day:02d}"

def download_excel(url, year, month):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Referer": "https://price.mpob.gov.my/daily",
    }
    r = requests.get(url, headers=headers)
    print(f"  Status: {r.status_code}")
    xlsx_path = os.path.join(WEBSITE_FOLDER, f"mpob_{year}{month:02d}.xlsx")
    with open(xlsx_path, "wb") as f:
        f.write(r.content)
    return xlsx_path

def parse_excel(xlsx_path):
    raw = pd.read_excel(xlsx_path, header=None)

    title = str(raw.iloc[0, 0])
    month_year = title.strip().split("\n")[-1].strip()
    period = pd.to_datetime(month_year, format="%B %Y")
    year = period.year
    month = period.month

    headers = raw.iloc[1].tolist()
    df = raw.iloc[2:].copy()
    df.columns = headers
    df = df.reset_index(drop=True)

    df.rename(columns={df.columns[0]: "Day"}, inplace=True)
    df = df[pd.to_numeric(df["Day"], errors="coerce").notna()]
    df["Day"] = df["Day"].astype(int)

    df["Date"] = pd.to_datetime(
        df["Day"].apply(lambda d: f"{year}-{month:02d}-{d:02d}")
    )
    df = df.drop(columns=["Day"])

    cols = ["Date"] + [c for c in df.columns if c != "Date"]
    df = df[cols]
    df = df.fillna("")

    return df, month_year

def merge_and_deduplicate(df_new):
    date_col = "Date"

    if os.path.exists(MASTER_CSV):
        df_master = pd.read_csv(MASTER_CSV, parse_dates=[date_col])
        df_combined = pd.concat([df_master, df_new])
    else:
        df_combined = df_new

    df_combined = df_combined.drop_duplicates(subset=[date_col], keep="last")
    df_combined = df_combined.sort_values(date_col, ascending=False)
    df_combined.to_csv(MASTER_CSV, index=False)

    df_out = df_combined.copy()
    df_out[date_col] = df_out[date_col].dt.strftime("%Y-%m-%d")
    df_out.to_json(JSON_PATH, orient="records", indent=2)

    return len(df_combined)

def main():
    today = date.today()
    start_year, start_month = 2026, 1

    # Build list of all months from Jan 2026 to current month
    months = []
    y, m = start_year, start_month
    while (y, m) <= (today.year, today.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    print(f"Downloading {len(months)} months...\n")

    for year, month in months:
        url = build_url(year, month)
        month_name = date(year, month, 1).strftime("%B %Y")
        print(f"📥 {month_name}: {url}")
        try:
            xlsx_path = download_excel(url, year, month)
            df_new, label = parse_excel(xlsx_path)
            total = merge_and_deduplicate(df_new)
            print(f"  ✅ Parsed {len(df_new)} rows — total in master: {total}\n")
        except Exception as e:
            print(f"  ❌ Failed: {e}\n")

    print("🎉 All done! mpob_master.csv and mpob_daily.json updated.")

main()