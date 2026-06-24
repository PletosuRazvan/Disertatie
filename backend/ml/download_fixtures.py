"""
Download the real Premier League fixture list for an upcoming season from
fixturedownload.com (free, no account) and save it as JSON for the simulator.

The feed uses slightly different team names than our historical dataset
(football-data.co.uk), so we normalise them via TEAM_NAME_MAP.

Usage:
    python -m ml.download_fixtures            # defaults to the 2026/27 season
Produces:
    ml/data/fixtures_<season>.json
        {"season": "2026/27", "fixtures": [{"round": 1, "home": "...", "away": "..."}, ...]}
"""

from __future__ import annotations

import json
import os

import requests

FEED_URL = "https://fixturedownload.com/feed/json/epl-{year}"

# fixturedownload.com name -> our dataset (football-data.co.uk) name.
TEAM_NAME_MAP = {
    "Man Utd": "Man United",
    "Spurs": "Tottenham",
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _norm(name: str) -> str:
    name = (name or "").strip()
    return TEAM_NAME_MAP.get(name, name)


def _season_label(start_year: int) -> str:
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def download_fixtures(start_year: int = 2026) -> str:
    url = FEED_URL.format(year=start_year)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    fixtures = []
    for m in raw:
        home = _norm(m.get("HomeTeam"))
        away = _norm(m.get("AwayTeam"))
        rnd = m.get("RoundNumber")
        if home and away and rnd is not None:
            fixtures.append({"round": int(rnd), "home": home, "away": away})

    fixtures.sort(key=lambda f: f["round"])
    season = _season_label(start_year)

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f"fixtures_{start_year}_{start_year + 1}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"season": season, "fixtures": fixtures}, f, indent=2)

    teams = sorted({f["home"] for f in fixtures} | {f["away"] for f in fixtures})
    rounds = max(f["round"] for f in fixtures)
    print(f"[DONE] {season}: {len(fixtures)} fixtures, {len(teams)} teams, "
          f"{rounds} rounds -> {out_path}")
    print("Teams:", ", ".join(teams))
    return out_path


if __name__ == "__main__":
    download_fixtures(2026)
