"""
Download English Premier League historical results from football-data.co.uk.

This source is free and requires no account. Each season is a CSV at:
    https://www.football-data.co.uk/mmz4281/<SEASON>/E0.csv
where <SEASON> is a 4-digit code, e.g. 9394 for 1993/94, 2324 for 2023/24.

We keep the columns relevant to the dissertation methodology:
    Date, HomeTeam, AwayTeam, FTHG (home goals), FTAG (away goals), FTR (H/D/A)
plus the match-statistics columns (available from ~2000/01 onwards):
    shots, shots on target, corners, fouls, yellow cards, red cards, offsides
(throw-ins are NOT recorded by this source).

Usage:
    python -m ml.download_data
Produces:
    ml/data/epl_matches.csv   (combined, cleaned, chronologically sorted)
"""

from __future__ import annotations

import io
import os
import time

import pandas as pd
import requests

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/E0.csv"

# Season codes from 1993/94 to 2025/26.
SEASON_CODES = [
    "9394", "9495", "9596", "9697", "9798", "9899",
    "9900", "0001", "0102", "0203", "0304", "0405", "0506", "0607",
    "0708", "0809", "0910", "1011", "1112", "1213", "1314", "1415",
    "1516", "1617", "1718", "1819", "1920", "2021", "2122", "2223", "2324",
    "2425", "2526",
]

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_CSV = os.path.join(DATA_DIR, "epl_matches.csv")

KEEP_COLS = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]

# Optional per-match statistics (present from ~2000/01). football-data codes
# -> our snake_case names. Missing in a season => filled with NaN.
STAT_COLS = {
    "HS": "home_shots", "AS": "away_shots",
    "HST": "home_sot", "AST": "away_sot",
    "HC": "home_corners", "AC": "away_corners",
    "HF": "home_fouls", "AF": "away_fouls",
    "HY": "home_yellows", "AY": "away_yellows",
    "HR": "home_reds", "AR": "away_reds",
    "HO": "home_offsides", "AO": "away_offsides",
}

# Bookmaker odds (1X2). Available from ~2000/01 onward. We capture several
# sources and, per match, pick the best available into unified odds_h/d/a:
# preference market-average (Avg / BbAv) over a single book (Bet365).
ODDS_SOURCES = [
    ("AvgH", "AvgD", "AvgA"),     # market average (recent seasons)
    ("BbAvH", "BbAvD", "BbAvA"),  # Betbrain market average (mid seasons)
    ("B365H", "B365D", "B365A"),  # Bet365 (most consistently present)
]
ODDS_RAW_COLS = [c for trio in ODDS_SOURCES for c in trio]


def _season_label(code: str) -> str:
    """Convert a 4-digit code like '9394' or '2324' into '1993/94'."""
    start, end = code[:2], code[2:]
    start_year = 1900 + int(start) if int(start) >= 90 else 2000 + int(start)
    return f"{start_year}/{end}"


def _download_one(code: str) -> pd.DataFrame | None:
    url = BASE_URL.format(season=code)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[WARN] Season {code}: download failed ({exc}).")
        return None

    # Some older files contain trailing empty columns / bad rows; be tolerant.
    df = pd.read_csv(io.StringIO(resp.text), encoding="latin-1", on_bad_lines="skip")
    missing = [c for c in KEEP_COLS if c not in df.columns]
    if missing:
        print(f"[WARN] Season {code}: missing columns {missing}, skipping.")
        return None

    available_stats = [c for c in STAT_COLS if c in df.columns]
    available_odds = [c for c in ODDS_RAW_COLS if c in df.columns]
    df = df[KEEP_COLS + available_stats + available_odds].copy()
    # Ensure every stat column exists (NaN where this season lacks it).
    for c in STAT_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    for c in ODDS_RAW_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    df["season"] = _season_label(code)
    return df


def download_all() -> pd.DataFrame:
    os.makedirs(DATA_DIR, exist_ok=True)
    frames: list[pd.DataFrame] = []

    for code in SEASON_CODES:
        df = _download_one(code)
        if df is not None and not df.empty:
            frames.append(df)
            print(f"[OK]   Season {_season_label(code)}: {len(df)} matches.")
        time.sleep(0.3)  # be polite to the server

    if not frames:
        raise RuntimeError("No season data could be downloaded.")

    combined = pd.concat(frames, ignore_index=True)

    # --- Clean ----------------------------------------------------------------
    combined = combined.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"])
    combined = combined.rename(columns={
        "HomeTeam": "home_team",
        "AwayTeam": "away_team",
        "FTHG": "home_goals",
        "FTAG": "away_goals",
        "FTR": "result",
        **STAT_COLS,
    })
    combined["home_goals"] = combined["home_goals"].astype(int)
    combined["away_goals"] = combined["away_goals"].astype(int)
    combined["result"] = combined["result"].str.upper().str.strip()
    combined = combined[combined["result"].isin(["H", "D", "A"])]

    # Coerce stat columns to numeric (some old files have blanks/strings).
    for col in STAT_COLS.values():
        combined[col] = pd.to_numeric(combined[col], errors="coerce")

    # Coerce odds columns to numeric, then consolidate into unified odds_h/d/a
    # (prefer market average, fall back to Betbrain average, then Bet365).
    for col in ODDS_RAW_COLS:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined["odds_h"] = float("nan")
    combined["odds_d"] = float("nan")
    combined["odds_a"] = float("nan")
    for h_col, d_col, a_col in ODDS_SOURCES:
        need = combined["odds_h"].isna()
        combined.loc[need, "odds_h"] = combined.loc[need, h_col]
        combined.loc[need, "odds_d"] = combined.loc[need, d_col]
        combined.loc[need, "odds_a"] = combined.loc[need, a_col]

    # Parse dates (football-data uses dd/mm/yy or dd/mm/yyyy).
    combined["date"] = pd.to_datetime(
        combined["Date"], dayfirst=True, errors="coerce"
    )
    combined = combined.dropna(subset=["date"])
    combined = combined.drop(columns=["Date"])

    combined = combined.sort_values("date").reset_index(drop=True)
    combined = combined[
        ["season", "date", "home_team", "away_team", "home_goals", "away_goals", "result"]
        + list(STAT_COLS.values())
        + ["odds_h", "odds_d", "odds_a"]
    ]

    combined.to_csv(OUTPUT_CSV, index=False)
    print(f"\n[DONE] {len(combined)} matches saved to {OUTPUT_CSV}")
    return combined


if __name__ == "__main__":
    download_all()
