"""
Feature engineering for EPL match prediction.

Builds the 15-feature vector described in the dissertation (Table: tab:features),
strictly from information available BEFORE each match (no data leakage).

Features (order matters — must match training & inference):
    home_goals_avg5, home_conceded_avg5, away_goals_avg5, away_conceded_avg5,
    home_win_pct, away_win_pct, home_elo, away_elo, elo_diff,
    home_goal_diff, away_goal_diff, h2h_home_wins, h2h_draws,
    home_position, away_position
"""

from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd

FEATURE_NAMES = [
    "home_goals_avg5",
    "home_conceded_avg5",
    "away_goals_avg5",
    "away_conceded_avg5",
    "home_win_pct",
    "away_win_pct",
    "home_elo",
    "away_elo",
    "elo_diff",
    "home_goal_diff",
    "away_goal_diff",
    "h2h_home_wins",
    "h2h_draws",
    "home_position",
    "away_position",
    # --- added to improve accuracy (calibrated Elo prob. + overall momentum) ---
    "elo_win_expectancy",
    "home_form5",
    "away_form5",
    "form_diff",
    # --- market-style 1X2 probability triple -----------------------------------
    # At training time these come from real bookmaker odds where available;
    # at inference (no odds for hypothetical/future fixtures) they are derived
    # from Elo. Odds-dropout during training bridges the two regimes.
    "market_prob_home",
    "market_prob_draw",
    "market_prob_away",
]

# Per-match statistic "kinds" produced by a team. These power the team-specific
# and head-to-head statistic features below (so the stats head can learn, e.g.,
# how many corners Arsenal typically win at home, or how foul-heavy the specific
# Arsenal vs Aston Villa fixture tends to be).
STAT_KINDS = ["shots", "sot", "corners", "fouls", "yellows", "reds", "offsides"]
STAT_WINDOW = 10   # rolling window for a team's own venue-split statistics
H2H_STAT_WINDOW = 10  # how many past meetings of a pairing feed the h2h stats

# Append the team-specific + head-to-head statistic features (order matters and
# must stay identical between training and inference).
for _k in STAT_KINDS:
    FEATURE_NAMES.append(f"home_{_k}_for_avg")   # home team, home venue, own stat
    FEATURE_NAMES.append(f"away_{_k}_for_avg")   # away team, away venue, own stat
    FEATURE_NAMES.append(f"h2h_home_{_k}_avg")   # this pairing, home team's stat
    FEATURE_NAMES.append(f"h2h_away_{_k}_avg")   # this pairing, away team's stat

RESULT_TO_LABEL = {"H": 0, "D": 1, "A": 2}  # outcome classes

# Elo-derived probability triple (fallback / inference). Draws are most likely
# in even matchups and fade as the Elo gap widens.
ELO_DRAW_BASE = 0.28
ELO_DRAW_SCALE = 400.0

# Per-match statistics the network learns to predict as auxiliary targets
# (order matters — must match training & inference). Present from ~2000/01;
# earlier seasons carry NaN and are masked out of the stats loss.
STAT_TARGETS = [
    "home_shots", "away_shots",
    "home_sot", "away_sot",
    "home_corners", "away_corners",
    "home_fouls", "away_fouls",
    "home_yellows", "away_yellows",
    "home_reds", "away_reds",
    "home_offsides", "away_offsides",
]

ELO_START = 1500.0
ELO_K = 20.0
HOME_ADVANTAGE = 60.0  # Elo points added to home side when computing expectation


def _expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def elo_implied_triple(elo_home: float, elo_away: float) -> tuple[float, float, float]:
    """
    Convert Elo ratings into a 1X2 probability triple (home, draw, away).
    Draw probability peaks for evenly matched sides and shrinks with the gap;
    the remaining mass is split by the home-advantaged expected score.
    """
    e = _expected_score(elo_home + HOME_ADVANTAGE, elo_away)  # home expected score
    gap = abs((elo_home + HOME_ADVANTAGE) - elo_away)
    p_draw = ELO_DRAW_BASE * (2.718281828 ** (-gap / ELO_DRAW_SCALE))
    p_home = (1.0 - p_draw) * e
    p_away = (1.0 - p_draw) * (1.0 - e)
    return p_home, p_draw, p_away


def odds_implied_triple(odds_h, odds_d, odds_a) -> tuple[float, float, float] | None:
    """Overround-adjusted implied probabilities from decimal 1X2 odds."""
    try:
        oh, od, oa = float(odds_h), float(odds_d), float(odds_a)
    except (TypeError, ValueError):
        return None
    if not (oh > 1 and od > 1 and oa > 1):
        return None
    rh, rd, ra = 1.0 / oh, 1.0 / od, 1.0 / oa
    s = rh + rd + ra
    if s <= 0:
        return None
    return rh / s, rd / s, ra / s


def avg_stat_kind(history, kind: str) -> float:
    """Mean of one statistic kind over a deque of per-match stat dicts (NaN-safe)."""
    vals = [d[kind] for d in history if kind in d and pd.notna(d[kind])]
    return sum(vals) / len(vals) if vals else 0.0


def avg_h2h_stat(history, team: str, kind: str) -> float:
    """
    Mean of one statistic kind for a specific team across past meetings of a
    pairing. `history` is a deque of {team_name: {kind: value}} dicts, so the
    same fixture can be read from either side's perspective (NaN-safe).
    """
    vals = [
        d[team][kind]
        for d in history
        if team in d and kind in d[team] and pd.notna(d[team][kind])
    ]
    return sum(vals) / len(vals) if vals else 0.0


def _match_stat_dict(m) -> tuple[dict, dict]:
    """Extract this match's home/away per-kind statistics (NaN where missing)."""
    hstats, astats = {}, {}
    for k in STAT_KINDS:
        hcol, acol = f"home_{k}", f"away_{k}"
        hstats[k] = float(m[hcol]) if hcol in m and pd.notna(m[hcol]) else float("nan")
        astats[k] = float(m[acol]) if acol in m and pd.notna(m[acol]) else float("nan")
    return hstats, astats


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a chronologically sorted DataFrame of matches, return a new DataFrame
    with the 15 feature columns plus the target columns:
        label (0/1/2), home_goals, away_goals
    """
    df = df.sort_values("date").reset_index(drop=True)

    elo: dict[str, float] = defaultdict(lambda: ELO_START)

    # Last-5 home games (goals for / against) keyed by team.
    home_for = defaultdict(lambda: deque(maxlen=5))
    home_against = defaultdict(lambda: deque(maxlen=5))
    away_for = defaultdict(lambda: deque(maxlen=5))
    away_against = defaultdict(lambda: deque(maxlen=5))

    # Head-to-head: last 5 meetings keyed by (home, away) unordered pair.
    h2h = defaultdict(lambda: deque(maxlen=5))  # stores 'H'/'D'/'A' from home perspective

    # Overall recent form: points (3/1/0) from each team's last 5 matches,
    # regardless of venue. Captures momentum better than venue-split goals.
    overall_form = defaultdict(lambda: deque(maxlen=5))

    # Team-specific match statistics, split by venue: each deque holds the last
    # STAT_WINDOW per-kind stat dicts a team produced at home / away. Lets the
    # model learn club-specific tendencies (e.g. Arsenal's home corner count).
    home_stat_hist = defaultdict(lambda: deque(maxlen=STAT_WINDOW))
    away_stat_hist = defaultdict(lambda: deque(maxlen=STAT_WINDOW))

    # Head-to-head statistics per pairing: last H2H_STAT_WINDOW meetings, each
    # stored as {team: {kind: value}} so the specific Arsenal vs Villa fixture
    # carries its own foul/corner profile from either side's perspective.
    h2h_stat_hist = defaultdict(lambda: deque(maxlen=H2H_STAT_WINDOW))

    # Per-season state: wins, played, goal diff, points (for standings position).
    season_stats: dict = {}
    current_season = None

    rows = []

    for _, m in df.iterrows():
        season = m["season"]
        h, a = m["home_team"], m["away_team"]
        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        res = m["result"]

        # Reset per-season aggregates at season boundary.
        if season != current_season:
            current_season = season
            season_stats = defaultdict(
                lambda: {"played": 0, "won": 0, "gf": 0, "ga": 0, "points": 0}
            )

        # ---- compute standings position BEFORE this match ----
        def _position(team: str) -> int:
            table = sorted(
                season_stats.items(),
                key=lambda kv: (kv[1]["points"], kv[1]["gf"] - kv[1]["ga"], kv[1]["gf"]),
                reverse=True,
            )
            for idx, (name, _) in enumerate(table, start=1):
                if name == team:
                    return idx
            return 20  # not yet ranked -> bottom default

        hs = season_stats[h]
        as_ = season_stats[a]

        def _avg(dq):
            return sum(dq) / len(dq) if dq else 0.0

        def _win_pct(stats):
            return stats["won"] / stats["played"] if stats["played"] else 0.0

        pair = tuple(sorted([h, a]))
        h2h_list = list(h2h[pair])
        # Count from current home team's perspective.
        h2h_home_wins = sum(1 for r in h2h_list if r == ("H" if pair[0] == h else "A"))
        h2h_draws = sum(1 for r in h2h_list if r == "D")

        # Calibrated Elo win expectancy (home perspective, includes home edge).
        elo_win_expectancy = _expected_score(elo[h] + HOME_ADVANTAGE, elo[a])
        home_form5 = _avg(overall_form[h])
        away_form5 = _avg(overall_form[a])

        # Team-specific (venue-split) and head-to-head statistic averages.
        home_stat_dq = home_stat_hist[h]
        away_stat_dq = away_stat_hist[a]
        h2h_stat_dq = h2h_stat_hist[pair]

        # Market-style 1X2 triple: real odds where available, else Elo-derived.
        elo_p = elo_implied_triple(elo[h], elo[a])
        odds_p = odds_implied_triple(
            m["odds_h"], m["odds_d"], m["odds_a"]
        ) if {"odds_h", "odds_d", "odds_a"}.issubset(m.index) else None
        market_p = odds_p if odds_p is not None else elo_p

        feat = {
            "home_goals_avg5": _avg(home_for[h]),
            "home_conceded_avg5": _avg(home_against[h]),
            "away_goals_avg5": _avg(away_for[a]),
            "away_conceded_avg5": _avg(away_against[a]),
            "home_win_pct": _win_pct(hs),
            "away_win_pct": _win_pct(as_),
            "home_elo": elo[h],
            "away_elo": elo[a],
            "elo_diff": elo[h] - elo[a],
            "home_goal_diff": hs["gf"] - hs["ga"],
            "away_goal_diff": as_["gf"] - as_["ga"],
            "h2h_home_wins": float(h2h_home_wins),
            "h2h_draws": float(h2h_draws),
            "home_position": float(_position(h)),
            "away_position": float(_position(a)),
            "elo_win_expectancy": elo_win_expectancy,
            "home_form5": home_form5,
            "away_form5": away_form5,
            "form_diff": home_form5 - away_form5,
            "market_prob_home": market_p[0],
            "market_prob_draw": market_p[1],
            "market_prob_away": market_p[2],
            # Elo-derived triple kept alongside for odds-dropout in training
            # (not a model feature itself).
            "elo_prob_home": elo_p[0],
            "elo_prob_draw": elo_p[1],
            "elo_prob_away": elo_p[2],
            # targets
            "label": RESULT_TO_LABEL[res],
            "home_goals": hg,
            "away_goals": ag,
            "season": season,
            "date": m["date"],
            # team identities (used for the model's per-team embeddings)
            "home_team": h,
            "away_team": a,
        }
        # Team-specific (venue-split) + head-to-head statistic features.
        for k in STAT_KINDS:
            feat[f"home_{k}_for_avg"] = avg_stat_kind(home_stat_dq, k)
            feat[f"away_{k}_for_avg"] = avg_stat_kind(away_stat_dq, k)
            feat[f"h2h_home_{k}_avg"] = avg_h2h_stat(h2h_stat_dq, h, k)
            feat[f"h2h_away_{k}_avg"] = avg_h2h_stat(h2h_stat_dq, a, k)
        # Carry through per-match statistics as auxiliary targets (NaN-safe).
        for col in STAT_TARGETS:
            feat[col] = float(m[col]) if col in m and pd.notna(m[col]) else float("nan")
        rows.append(feat)

        # ---- update state AFTER recording the (leak-free) features ----
        # Elo update
        exp_home = _expected_score(elo[h] + HOME_ADVANTAGE, elo[a])
        score_home = 1.0 if res == "H" else 0.5 if res == "D" else 0.0
        elo[h] += ELO_K * (score_home - exp_home)
        elo[a] += ELO_K * ((1.0 - score_home) - (1.0 - exp_home))

        # Rolling form
        home_for[h].append(hg)
        home_against[h].append(ag)
        away_for[a].append(ag)
        away_against[a].append(hg)

        # Head-to-head
        h2h[pair].append("H" if (res == "H" and pair[0] == h) or (res == "A" and pair[0] == a)
                         else "A" if (res == "A" and pair[0] == h) or (res == "H" and pair[0] == a)
                         else "D")

        # Overall recent form (points from this match for each team)
        home_pts = 3 if res == "H" else 1 if res == "D" else 0
        overall_form[h].append(home_pts)
        overall_form[a].append(3 - home_pts if res != "D" else 1)

        # Team-specific (venue-split) + head-to-head statistic histories.
        mh_stats, ma_stats = _match_stat_dict(m)
        home_stat_hist[h].append(mh_stats)
        away_stat_hist[a].append(ma_stats)
        h2h_stat_hist[pair].append({h: mh_stats, a: ma_stats})

        # Season standings
        hs["played"] += 1
        as_["played"] += 1
        hs["gf"] += hg
        hs["ga"] += ag
        as_["gf"] += ag
        as_["ga"] += hg
        if res == "H":
            hs["won"] += 1
            hs["points"] += 3
        elif res == "A":
            as_["won"] += 1
            as_["points"] += 3
        else:
            hs["points"] += 1
            as_["points"] += 1

    return pd.DataFrame(rows)


def feature_vector_from_state(state: dict) -> list[float]:
    """Build a single feature vector (for live inference) from a prepared dict."""
    return [float(state[name]) for name in FEATURE_NAMES]
