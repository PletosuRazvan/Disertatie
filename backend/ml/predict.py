"""
Inference helper loaded by the Flask backend.

Loads the trained PyTorch model + scaler once, replays the full match history to
reconstruct the *current* state of every team (Elo, last-5 form, season table,
head-to-head), and exposes predict(home, away) returning:
    - outcome probabilities (H/D/A)
    - predicted class
    - expected goals for each side (Poisson rates)
    - most likely exact score
"""

from __future__ import annotations

import copy
import json
import os
from collections import defaultdict, deque

import joblib
import numpy as np
import pandas as pd
import torch

from ml.features import (
    ELO_K,
    ELO_START,
    FEATURE_NAMES,
    HOME_ADVANTAGE,
    H2H_STAT_WINDOW,
    STAT_KINDS,
    STAT_WINDOW,
    _expected_score,
    _match_stat_dict,
    avg_h2h_stat,
    avg_stat_kind,
    elo_implied_triple,
)
from ml.model import EPLNet

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
DATA_CSV = os.path.join(os.path.dirname(__file__), "data", "epl_matches.csv")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

CLASS_LABELS = ["H", "D", "A"]
CLASS_NAMES = {"H": "Home win", "D": "Draw", "A": "Away win"}

MAX_GOALS = 9  # cap simulated scorelines to a sane range
MAX_RUNS = 10000  # upper bound for Monte-Carlo batch simulations

# Per-team match statistics surfaced in season simulations (yellow/red cards and
# corners). Yellows/reds are aggregated as season totals (single season) or
# per-season averages (multi-season), corners always as a per-match average.
SIM_STAT_KINDS = ("yellows", "reds", "corners")

# How much a (network-projected) red card swings expected goals:
#  - the carded team scores less, the opponent scores a bit more.
RED_SELF_PENALTY = 0.35
RED_OPP_BONUS = 0.20


def _avg(dq):
    return sum(dq) / len(dq) if dq else 0.0


def _win_pct(stats):
    return stats["won"] / stats["played"] if stats["played"] else 0.0


def _table_positions(season_stats: dict) -> dict:
    """Map team -> 1-based league position from the current season table."""
    table = sorted(
        season_stats.items(),
        key=lambda kv: (kv[1]["points"], kv[1]["gf"] - kv[1]["ga"], kv[1]["gf"]),
        reverse=True,
    )
    return {name: idx for idx, (name, _) in enumerate(table, start=1)}


def build_feature_row(state: dict, home: str, away: str, positions: dict | None = None) -> dict:
    """
    Compute the model's feature dict for a single fixture from an explicit state
    (used both for live inference and full-season simulation, so they stay in
    sync). `state` holds: elo, home_for, home_against, away_for, away_against,
    overall_form, h2h, season_stats. `positions` may be precomputed once per
    matchday to skip a redundant table sort on every fixture.
    """
    elo = state["elo"]
    season_stats = state["season_stats"]
    hs, as_ = season_stats[home], season_stats[away]

    pair = tuple(sorted([home, away]))
    h2h_list = list(state["h2h"][pair])
    h2h_home_wins = sum(1 for r in h2h_list if r == ("H" if pair[0] == home else "A"))
    h2h_draws = sum(1 for r in h2h_list if r == "D")

    if positions is None:
        positions = _table_positions(season_stats)
    elo_win_expectancy = _expected_score(elo[home] + HOME_ADVANTAGE, elo[away])
    home_form5 = _avg(state["overall_form"][home])
    away_form5 = _avg(state["overall_form"][away])
    # No bookmaker odds for hypothetical/future fixtures -> use Elo-derived
    # probability triple (the model was trained to handle this via odds-dropout).
    market_p = elo_implied_triple(elo[home], elo[away])

    home_stat_dq = state["home_stat_hist"][home]
    away_stat_dq = state["away_stat_hist"][away]
    h2h_stat_dq = state["h2h_stat_hist"][pair]

    row = {
        "home_goals_avg5": _avg(state["home_for"][home]),
        "home_conceded_avg5": _avg(state["home_against"][home]),
        "away_goals_avg5": _avg(state["away_for"][away]),
        "away_conceded_avg5": _avg(state["away_against"][away]),
        "home_win_pct": _win_pct(hs),
        "away_win_pct": _win_pct(as_),
        "home_elo": elo[home],
        "away_elo": elo[away],
        "elo_diff": elo[home] - elo[away],
        "home_goal_diff": hs["gf"] - hs["ga"],
        "away_goal_diff": as_["gf"] - as_["ga"],
        "h2h_home_wins": float(h2h_home_wins),
        "h2h_draws": float(h2h_draws),
        "home_position": float(positions.get(home, 20)),
        "away_position": float(positions.get(away, 20)),
        "elo_win_expectancy": elo_win_expectancy,
        "home_form5": home_form5,
        "away_form5": away_form5,
        "form_diff": home_form5 - away_form5,
        "market_prob_home": market_p[0],
        "market_prob_draw": market_p[1],
        "market_prob_away": market_p[2],
    }
    # Team-specific (venue-split) + head-to-head statistic features.
    for k in STAT_KINDS:
        row[f"home_{k}_for_avg"] = avg_stat_kind(home_stat_dq, k)
        row[f"away_{k}_for_avg"] = avg_stat_kind(away_stat_dq, k)
        row[f"h2h_home_{k}_avg"] = avg_h2h_stat(h2h_stat_dq, home, k)
        row[f"h2h_away_{k}_avg"] = avg_h2h_stat(h2h_stat_dq, away, k)
    return row


def _apply_result(state: dict, home: str, away: str, hg: int, ag: int,
                  home_stats: dict | None = None, away_stats: dict | None = None):
    """Advance an Elo/form/standings state after a (simulated) match."""
    elo = state["elo"]
    res = "H" if hg > ag else "A" if ag > hg else "D"

    exp_home = _expected_score(elo[home] + HOME_ADVANTAGE, elo[away])
    score_home = 1.0 if res == "H" else 0.5 if res == "D" else 0.0
    elo[home] += ELO_K * (score_home - exp_home)
    elo[away] += ELO_K * ((1.0 - score_home) - (1.0 - exp_home))

    state["home_for"][home].append(hg)
    state["home_against"][home].append(ag)
    state["away_for"][away].append(ag)
    state["away_against"][away].append(hg)

    pair = tuple(sorted([home, away]))
    state["h2h"][pair].append(
        "H" if (res == "H" and pair[0] == home) or (res == "A" and pair[0] == away)
        else "A" if (res == "A" and pair[0] == home) or (res == "H" and pair[0] == away)
        else "D"
    )

    home_pts = 3 if res == "H" else 1 if res == "D" else 0
    state["overall_form"][home].append(home_pts)
    state["overall_form"][away].append(3 - home_pts if res != "D" else 1)

    # Team-specific (venue-split) + head-to-head statistic histories. Only
    # recorded when real per-match statistics are available (history replay);
    # simulated matches have no observed stats, so they are skipped.
    if home_stats is not None and away_stats is not None:
        state["home_stat_hist"][home].append(home_stats)
        state["away_stat_hist"][away].append(away_stats)
        state["h2h_stat_hist"][pair].append({home: home_stats, away: away_stats})

    ss = state["season_stats"]
    hs, as_ = ss[home], ss[away]
    hs["played"] += 1
    as_["played"] += 1
    hs["gf"] += hg
    hs["ga"] += ag
    as_["gf"] += ag
    as_["ga"] += hg
    if res == "H":
        hs["won"] += 1
        hs["points"] += 3
        as_["lost"] += 1
    elif res == "A":
        as_["won"] += 1
        as_["points"] += 3
        hs["lost"] += 1
    else:
        hs["drawn"] += 1
        as_["drawn"] += 1
        hs["points"] += 1
        as_["points"] += 1
    return res


def _round_robin(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Balanced double round-robin schedule -> list of matchdays of (home, away)."""
    arr = list(teams)
    if len(arr) % 2:
        arr.append(None)  # bye for odd team counts
    n = len(arr)
    first_half: list[list[tuple[str, str]]] = []
    for r in range(n - 1):
        pairings = []
        for i in range(n // 2):
            t1, t2 = arr[i], arr[n - 1 - i]
            if t1 is not None and t2 is not None:
                pairings.append((t1, t2) if r % 2 == 0 else (t2, t1))
        first_half.append(pairings)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]  # rotate, keep first fixed
    second_half = [[(a, h) for (h, a) in rnd] for rnd in first_half]
    return first_half + second_half


def _new_state() -> dict:
    """A blank Elo/form/standings state for replay or simulation."""
    return {
        "elo": defaultdict(lambda: ELO_START),
        "home_for": defaultdict(lambda: deque(maxlen=5)),
        "home_against": defaultdict(lambda: deque(maxlen=5)),
        "away_for": defaultdict(lambda: deque(maxlen=5)),
        "away_against": defaultdict(lambda: deque(maxlen=5)),
        "overall_form": defaultdict(lambda: deque(maxlen=5)),
        "h2h": defaultdict(lambda: deque(maxlen=5)),
        "home_stat_hist": defaultdict(lambda: deque(maxlen=STAT_WINDOW)),
        "away_stat_hist": defaultdict(lambda: deque(maxlen=STAT_WINDOW)),
        "h2h_stat_hist": defaultdict(lambda: deque(maxlen=H2H_STAT_WINDOW)),
        "season_stats": defaultdict(
            lambda: {"played": 0, "won": 0, "drawn": 0, "lost": 0,
                     "gf": 0, "ga": 0, "points": 0}
        ),
    }


class Predictor:
    def __init__(self, history: pd.DataFrame | None = None):
        self._load_artifacts()
        if history is None:
            history = pd.read_csv(DATA_CSV, parse_dates=["date"])
        self._build_state(history)

    # ------------------------------------------------------------------ load
    def _load_artifacts(self):
        with open(os.path.join(ARTIFACT_DIR, "metadata.json"), encoding="utf-8") as f:
            self.meta = json.load(f)
        self.scaler = joblib.load(os.path.join(ARTIFACT_DIR, "scaler.pkl"))
        self.stat_targets = self.meta.get("stat_targets", [])
        # Per-team embedding vocabulary (name -> index); OOV slot == len(teams).
        self.embed_teams = self.meta.get("teams", [])
        self.team_to_idx = {t: i for i, t in enumerate(self.embed_teams)}
        self.oov_team_idx = len(self.embed_teams)
        self.model = EPLNet(
            n_features=self.meta["n_features"],
            n_stats=self.meta.get("n_stats", len(self.stat_targets) or 14),
            n_teams=self.meta.get("n_teams", len(self.embed_teams)),
        )
        self.model.load_state_dict(
            torch.load(os.path.join(ARTIFACT_DIR, "model.pt"), map_location="cpu")
        )
        self.model.eval()

    def _team_idx_tensors(self, pairs):
        """Map a list of (home, away) name pairs to two long index tensors."""
        h = [self.team_to_idx.get(home, self.oov_team_idx) for home, _ in pairs]
        a = [self.team_to_idx.get(away, self.oov_team_idx) for _, away in pairs]
        return torch.tensor(h, dtype=torch.long), torch.tensor(a, dtype=torch.long)

    # ----------------------------------------------------------------- state
    def _build_state(self, df: pd.DataFrame):
        df = df.sort_values("date").reset_index(drop=True)

        self.elo = defaultdict(lambda: ELO_START)
        self.home_for = defaultdict(lambda: deque(maxlen=5))
        self.home_against = defaultdict(lambda: deque(maxlen=5))
        self.away_for = defaultdict(lambda: deque(maxlen=5))
        self.away_against = defaultdict(lambda: deque(maxlen=5))
        self.h2h = defaultdict(lambda: deque(maxlen=5))
        self.overall_form = defaultdict(lambda: deque(maxlen=5))
        self.home_stat_hist = defaultdict(lambda: deque(maxlen=STAT_WINDOW))
        self.away_stat_hist = defaultdict(lambda: deque(maxlen=STAT_WINDOW))
        self.h2h_stat_hist = defaultdict(lambda: deque(maxlen=H2H_STAT_WINDOW))
        self.season_stats = defaultdict(
            lambda: {"played": 0, "won": 0, "gf": 0, "ga": 0, "points": 0}
        )
        self.latest_season = None

        for _, m in df.iterrows():
            season = m["season"]
            h, a = m["home_team"], m["away_team"]
            hg, ag = int(m["home_goals"]), int(m["away_goals"])
            res = str(m["result"]).upper()

            if season != self.latest_season:
                self.latest_season = season
                self.season_stats = defaultdict(
                    lambda: {"played": 0, "won": 0, "gf": 0, "ga": 0, "points": 0}
                )

            exp_home = _expected_score(self.elo[h] + HOME_ADVANTAGE, self.elo[a])
            score_home = 1.0 if res == "H" else 0.5 if res == "D" else 0.0
            self.elo[h] += ELO_K * (score_home - exp_home)
            self.elo[a] += ELO_K * ((1.0 - score_home) - (1.0 - exp_home))

            self.home_for[h].append(hg)
            self.home_against[h].append(ag)
            self.away_for[a].append(ag)
            self.away_against[a].append(hg)

            pair = tuple(sorted([h, a]))
            self.h2h[pair].append(
                "H" if (res == "H" and pair[0] == h) or (res == "A" and pair[0] == a)
                else "A" if (res == "A" and pair[0] == h) or (res == "H" and pair[0] == a)
                else "D"
            )

            home_pts = 3 if res == "H" else 1 if res == "D" else 0
            self.overall_form[h].append(home_pts)
            self.overall_form[a].append(3 - home_pts if res != "D" else 1)

            mh_stats, ma_stats = _match_stat_dict(m)
            self.home_stat_hist[h].append(mh_stats)
            self.away_stat_hist[a].append(ma_stats)
            self.h2h_stat_hist[pair].append({h: mh_stats, a: ma_stats})

            hs, as_ = self.season_stats[h], self.season_stats[a]
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

        self.known_teams = sorted(set(df["home_team"]) | set(df["away_team"]))
        latest = df[df["season"] == self.latest_season]
        self.current_teams = sorted(set(latest["home_team"]) | set(latest["away_team"]))
        # Full history + chronological season list, used to rebuild a team's
        # strength as of the start of any season we want to simulate.
        self.history = df
        self.seasons = sorted(df["season"].unique())
        self._fixtures = self._load_fixtures()
        # Keep a deep-copyable snapshot of the live state for simulations.
        self._state = {
            "elo": self.elo,
            "home_for": self.home_for,
            "home_against": self.home_against,
            "away_for": self.away_for,
            "away_against": self.away_against,
            "overall_form": self.overall_form,
            "h2h": self.h2h,
            "home_stat_hist": self.home_stat_hist,
            "away_stat_hist": self.away_stat_hist,
            "h2h_stat_hist": self.h2h_stat_hist,
            "season_stats": self.season_stats,
        }

    # --------------------------------------------------------------- helpers
    def _load_fixtures(self) -> dict:
        """Load any saved real fixture lists (e.g. fixtures_2026_2027.json)."""
        fixtures = {}
        if not os.path.isdir(DATA_DIR):
            return fixtures
        for fname in os.listdir(DATA_DIR):
            if fname.startswith("fixtures_") and fname.endswith(".json"):
                try:
                    with open(os.path.join(DATA_DIR, fname), encoding="utf-8") as f:
                        data = json.load(f)
                    fixtures[data["season"]] = data["fixtures"]
                except (OSError, ValueError, KeyError):
                    continue
        return fixtures

    def _position(self, team: str) -> int:
        return _table_positions(self.season_stats).get(team, 20)

    def _features(self, home: str, away: str) -> np.ndarray:
        values = build_feature_row(self._state, home, away)
        return np.array([[values[name] for name in FEATURE_NAMES]], dtype=float)

    # --------------------------------------------------------- match stats
    def _stats_from_rates(self, stat_rates: np.ndarray) -> dict | None:
        """
        Turn the network's statistics head output (one rate per target, in the
        order of self.stat_targets) into a structured home/away dict.
        """
        if not self.stat_targets:
            return None
        values = {name: float(v) for name, v in zip(self.stat_targets, stat_rates)}

        def side(prefix):
            return {
                "shots": round(values.get(f"{prefix}_shots", 0.0), 1),
                "sot": round(values.get(f"{prefix}_sot", 0.0), 1),
                "corners": round(values.get(f"{prefix}_corners", 0.0), 1),
                "fouls": round(values.get(f"{prefix}_fouls", 0.0), 1),
                "yellows": round(values.get(f"{prefix}_yellows", 0.0), 1),
                "reds": round(values.get(f"{prefix}_reds", 0.0), 2),
                "offsides": round(values.get(f"{prefix}_offsides", 0.0), 1),
            }

        home_stats, away_stats = side("home"), side("away")
        return {
            "home": home_stats,
            "away": away_stats,
            "totals": {
                "yellows": round(home_stats["yellows"] + away_stats["yellows"], 1),
                "reds": round(home_stats["reds"] + away_stats["reds"], 2),
                "corners": round(home_stats["corners"] + away_stats["corners"], 1),
            },
        }

    # ------------------------------------------------ simulation stat accrual
    def _match_team_stats(self, stat_rates: np.ndarray) -> tuple[dict, dict]:
        """Per-team yellows/reds/corners (expected rates) for one simulated match."""
        vals = {name: float(v) for name, v in zip(self.stat_targets, stat_rates)}
        home = {k: vals.get(f"home_{k}", 0.0) for k in SIM_STAT_KINDS}
        away = {k: vals.get(f"away_{k}", 0.0) for k in SIM_STAT_KINDS}
        return home, away

    @staticmethod
    def _new_stat_accum(teams: list[str]) -> dict:
        return {t: {"yellows": 0.0, "reds": 0.0, "corners": 0.0, "matches": 0}
                for t in teams}

    @staticmethod
    def _accumulate_match_stats(accum, home, away, home_stats, away_stats):
        ah, aa = accum[home], accum[away]
        for k in SIM_STAT_KINDS:
            ah[k] += home_stats[k]
            aa[k] += away_stats[k]
        ah["matches"] += 1
        aa["matches"] += 1

    @staticmethod
    def _attach_season_stats(standings, accum):
        """Add season-total yellows/reds and per-match corner average to a table."""
        for r in standings:
            a = accum.get(r["team"])
            if not a or a["matches"] == 0:
                continue
            r["yellows"] = round(a["yellows"], 1)
            r["reds"] = round(a["reds"], 1)
            r["corners_avg"] = round(a["corners"] / a["matches"], 1)

    # --------------------------------------------------------------- predict
    def predict(self, home: str, away: str) -> dict:
        x = self.scaler.transform(self._features(home, away))
        xt = torch.tensor(x, dtype=torch.float32)
        hi, ai = self._team_idx_tensors([(home, away)])
        with torch.no_grad():
            logits, rates, stat_rates = self.model(xt, hi, ai)
            probs = torch.softmax(logits, dim=1).numpy()[0]
            home_rate, away_rate = rates.numpy()[0]
            stat_rates = stat_rates.numpy()[0]

        pred_idx = int(np.argmax(probs))
        pred_label = CLASS_LABELS[pred_idx]

        base_home = float(home_rate)
        base_away = float(away_rate)

        # The network forecasts per-match statistics; projected red cards nudge
        # the score: the carded side scores less, the opponent a little more.
        stats = self._stats_from_rates(stat_rates)
        adj_home, adj_away = base_home, base_away
        card_adjustment = None
        if stats:
            p_red_home = min(float(stats["home"]["reds"]), 0.6)
            p_red_away = min(float(stats["away"]["reds"]), 0.6)
            adj_home = base_home * (1 - RED_SELF_PENALTY * p_red_home) \
                * (1 + RED_OPP_BONUS * p_red_away)
            adj_away = base_away * (1 - RED_SELF_PENALTY * p_red_away) \
                * (1 + RED_OPP_BONUS * p_red_home)
            card_adjustment = {
                "applied": abs(adj_home - base_home) > 0.01
                or abs(adj_away - base_away) > 0.01,
                "home_red_risk": round(p_red_home, 2),
                "away_red_risk": round(p_red_away, 2),
                "home_goal_delta": round(adj_home - base_home, 2),
                "away_goal_delta": round(adj_away - base_away, 2),
            }

        result = {
            "home_team": home,
            "away_team": away,
            "probabilities": {
                "H": round(float(probs[0]), 4),
                "D": round(float(probs[1]), 4),
                "A": round(float(probs[2]), 4),
            },
            "predicted_result": pred_label,
            "predicted_result_name": CLASS_NAMES[pred_label],
            "expected_goals": {
                "home": round(adj_home, 2),
                "away": round(adj_away, 2),
            },
            "base_expected_goals": {
                "home": round(base_home, 2),
                "away": round(base_away, 2),
            },
            "predicted_score": {
                "home": int(round(adj_home)),
                "away": int(round(adj_away)),
            },
        }
        if stats:
            result["match_stats"] = stats
            result["card_adjustment"] = card_adjustment
        return result

    # -------------------------------------------------------------- simulate
    def _strength_state_before(self, season: str) -> dict:
        """
        Replay every match BEFORE `season` to reconstruct each team's strength
        (Elo, recent form, head-to-head) as it stood going into that season.
        The season table is left empty so the simulated campaign starts at 0-0.
        """
        state = _new_state()
        prior = self.history[self.history["season"] < season].sort_values("date")
        for m in prior.itertuples(index=False):
            mh_stats, ma_stats = _match_stat_dict(m._asdict())
            _apply_result(state, m.home_team, m.away_team,
                          int(m.home_goals), int(m.away_goals),
                          home_stats=mh_stats, away_stats=ma_stats)
        # Discard the accumulated cross-season table; keep only strength signals.
        state["season_stats"] = defaultdict(
            lambda: {"played": 0, "won": 0, "drawn": 0, "lost": 0,
                     "gf": 0, "ga": 0, "points": 0}
        )
        return state

    def _teams_for_season(self, season: str) -> list[str]:
        sdf = self.history[self.history["season"] == season]
        return sorted(set(sdf["home_team"]) | set(sdf["away_team"]))

    @staticmethod
    def _standings_from(season_stats: dict, teams: list[str]) -> list[dict]:
        rows = []
        for t in teams:
            s = season_stats[t]
            rows.append({
                "team": t,
                "played": s["played"],
                "won": s["won"],
                "drawn": s["drawn"],
                "lost": s["lost"],
                "gf": s["gf"],
                "ga": s["ga"],
                "gd": s["gf"] - s["ga"],
                "points": s["points"],
            })
        rows.sort(key=lambda r: (r["points"], r["gd"], r["gf"]), reverse=True)
        for i, r in enumerate(rows, start=1):
            r["pos"] = i
        return rows

    def _sample_scoreline(self, probs, home_rate, away_rate, rng):
        """
        Hybrid sampling: pick the outcome from the classifier's probabilities
        (its strongest signal), then draw a scoreline from the Poisson goal
        rates that is consistent with that outcome. Keeps results realistic and
        different on every run.
        """
        outcome = int(rng.choice(3, p=probs))  # 0=H, 1=D, 2=A
        hg = int(min(rng.poisson(max(float(home_rate), 1e-3)), MAX_GOALS))
        ag = int(min(rng.poisson(max(float(away_rate), 1e-3)), MAX_GOALS))

        if outcome == 0 and hg <= ag:          # home win
            hg = ag + 1
        elif outcome == 2 and ag <= hg:        # away win
            ag = hg + 1
        elif outcome == 1:                     # draw
            g = int(round((hg + ag) / 2))
            hg = ag = min(g, MAX_GOALS)

        hg = min(hg, MAX_GOALS)
        ag = min(ag, MAX_GOALS)
        return hg, ag

    def simulate_season(self, season: str | None = None, seed: int | None = None) -> dict:
        """
        Simulate a full season for the real teams of `season` (default: the most
        recent season in the data). Team strengths start from the end of the
        previous season; outcomes are sampled (classifier + Poisson), so every
        run is different. Returns matchday results + the final table.
        """
        season = season if season in (self.seasons or []) else self.latest_season
        rng = np.random.default_rng(seed)
        teams = self._teams_for_season(season)
        state = self._strength_state_before(season)
        schedule = _round_robin(teams)
        stat_accum = self._new_stat_accum(teams)

        matchdays = []
        for idx, fixtures in enumerate(schedule, start=1):
            matches = []
            for home, away in fixtures:
                feat = build_feature_row(state, home, away)
                x = self.scaler.transform(
                    np.array([[feat[n] for n in FEATURE_NAMES]], dtype=float)
                )
                hi, ai = self._team_idx_tensors([(home, away)])
                with torch.no_grad():
                    logits, rates, stat_rates = self.model(
                        torch.tensor(x, dtype=torch.float32), hi, ai)
                    probs = torch.softmax(logits, dim=1).numpy()[0]
                    home_rate, away_rate = rates.numpy()[0]
                    stat_rates = stat_rates.numpy()[0]
                hg, ag = self._sample_scoreline(probs, home_rate, away_rate, rng)
                if self.stat_targets:
                    hst, ast_ = self._match_team_stats(stat_rates)
                    self._accumulate_match_stats(stat_accum, home, away, hst, ast_)
                res = _apply_result(state, home, away, hg, ag)
                matches.append({
                    "home_team": home, "away_team": away,
                    "home_goals": hg, "away_goals": ag, "result": res,
                })
            matchdays.append({"round": idx, "matches": matches})

        standings = self._standings_from(state["season_stats"], teams)
        self._attach_season_stats(standings, stat_accum)
        return {
            "season": season,
            "teams": teams,
            "matchdays": matchdays,
            "standings": standings,
        }

    def _strength_state_full(self) -> dict:
        """Reconstruct team strength from the ENTIRE history (for next season)."""
        state = _new_state()
        prior = self.history.sort_values("date")
        for m in prior.itertuples(index=False):
            _apply_result(state, m.home_team, m.away_team,
                          int(m.home_goals), int(m.away_goals))
        state["season_stats"] = defaultdict(
            lambda: {"played": 0, "won": 0, "drawn": 0, "lost": 0,
                     "gf": 0, "ga": 0, "points": 0}
        )
        return state

    @property
    def next_seasons(self) -> list[str]:
        """Real upcoming seasons we have a fixture list for (not yet in data)."""
        return sorted(s for s in self._fixtures if s not in (self.seasons or []))

    def simulate_next_season(self, season: str, seed: int | None = None) -> dict:
        """
        Simulate an upcoming season using the REAL fixture list (team line-up and
        matchday order fetched from the web). Strengths start from the end of all
        available history; outcomes are sampled, so every run differs.
        """
        fixtures = self._fixtures.get(season)
        if not fixtures:
            raise ValueError(f"No fixture list available for season {season}")

        rng = np.random.default_rng(seed)
        state = self._strength_state_full()
        teams = sorted({f["home"] for f in fixtures} | {f["away"] for f in fixtures})
        stat_accum = self._new_stat_accum(teams)

        rounds: dict[int, list] = defaultdict(list)
        for f in fixtures:
            rounds[int(f["round"])].append((f["home"], f["away"]))

        matchdays = []
        for rnd in sorted(rounds):
            matches = []
            for home, away in rounds[rnd]:
                feat = build_feature_row(state, home, away)
                x = self.scaler.transform(
                    np.array([[feat[n] for n in FEATURE_NAMES]], dtype=float)
                )
                hi, ai = self._team_idx_tensors([(home, away)])
                with torch.no_grad():
                    logits, rates, stat_rates = self.model(
                        torch.tensor(x, dtype=torch.float32), hi, ai)
                    probs = torch.softmax(logits, dim=1).numpy()[0]
                    home_rate, away_rate = rates.numpy()[0]
                    stat_rates = stat_rates.numpy()[0]
                hg, ag = self._sample_scoreline(probs, home_rate, away_rate, rng)
                if self.stat_targets:
                    hst, ast_ = self._match_team_stats(stat_rates)
                    self._accumulate_match_stats(stat_accum, home, away, hst, ast_)
                res = _apply_result(state, home, away, hg, ag)
                matches.append({
                    "home_team": home, "away_team": away,
                    "home_goals": hg, "away_goals": ag, "result": res,
                })
            matchdays.append({"round": rnd, "matches": matches})

        standings = self._standings_from(state["season_stats"], teams)
        self._attach_season_stats(standings, stat_accum)
        return {
            "season": season,
            "teams": teams,
            "matchdays": matchdays,
            "standings": standings,
            "is_next_season": True,
        }

    # --------------------------------------------------------- monte carlo
    def _resolve_schedule(self, season: str | None):
        """
        Return (label, teams, schedule, base_state, is_next) for a season.
        `schedule` is a list of matchdays, each a list of (home, away) tuples.
        """
        is_next = season in self._fixtures and season not in (self.seasons or [])
        if is_next:
            fixtures = self._fixtures[season]
            rounds: dict[int, list] = defaultdict(list)
            for f in fixtures:
                rounds[int(f["round"])].append((f["home"], f["away"]))
            schedule = [rounds[r] for r in sorted(rounds)]
            teams = sorted({f["home"] for f in fixtures} | {f["away"] for f in fixtures})
            return season, teams, schedule, self._strength_state_full(), True

        label = season if season in (self.seasons or []) else self.latest_season
        teams = self._teams_for_season(label)
        return label, teams, _round_robin(teams), self._strength_state_before(label), False

    def _run_once(self, base_state: dict, schedule: list, teams: list[str], rng):
        """Simulate one campaign from a fresh copy of `base_state`.

        Matches within a matchday are scored from the same state, so all fixtures
        of a round are batched through the model in a single forward pass.
        Returns (standings, stat_accum) where stat_accum holds this season's
        per-team yellow/red/corner totals.
        """
        state = copy.deepcopy(base_state)
        stat_accum = self._new_stat_accum(teams)
        for fixtures in schedule:
            if not fixtures:
                continue
            positions = _table_positions(state["season_stats"])
            rows = np.array(
                [[build_feature_row(state, h, a, positions)[n] for n in FEATURE_NAMES]
                 for (h, a) in fixtures],
                dtype=float,
            )
            x = self.scaler.transform(rows)
            hi, ai = self._team_idx_tensors(fixtures)
            with torch.no_grad():
                logits, rates, stat_rates = self.model(
                    torch.tensor(x, dtype=torch.float32), hi, ai)
                probs = torch.softmax(logits, dim=1).numpy()
                rate_arr = rates.numpy()
                stat_arr = stat_rates.numpy()
            for i, (home, away) in enumerate(fixtures):
                hg, ag = self._sample_scoreline(
                    probs[i], rate_arr[i][0], rate_arr[i][1], rng
                )
                if self.stat_targets:
                    hst, ast_ = self._match_team_stats(stat_arr[i])
                    self._accumulate_match_stats(stat_accum, home, away, hst, ast_)
                _apply_result(state, home, away, hg, ag)
        return self._standings_from(state["season_stats"], teams), stat_accum

    def iter_simulate_batch(self, season: str | None = None, runs: int = 1000,
                            seed: int | None = None, progress_every: int = 0):
        """
        Generator variant of :meth:`simulate_batch`.

        Yields ``("progress", done)`` tuples roughly every ``progress_every``
        completed seasons, and finally a single ``("result", result_dict)``.
        ``progress_every <= 0`` disables intermediate progress events.
        """
        runs = max(1, min(int(runs or 1), MAX_RUNS))
        label, teams, schedule, base_state, is_next = self._resolve_schedule(season)
        n = len(teams)
        releg_cut = n - 3  # bottom 3 positions are relegation (pos > n-3)
        rng = np.random.default_rng(seed)

        agg = {
            t: {"title": 0, "top4": 0, "top10": 0, "releg": 0,
                "pts_sum": 0.0, "pos_sum": 0.0, "best": n, "worst": 1,
                "yellows_sum": 0.0, "reds_sum": 0.0,
                "corners_sum": 0.0, "match_sum": 0}
            for t in teams
        }

        for i in range(runs):
            standings, stat_accum = self._run_once(base_state, schedule, teams, rng)
            for r in standings:
                a = agg[r["team"]]
                pos = r["pos"]
                if pos == 1:
                    a["title"] += 1
                if pos <= 4:
                    a["top4"] += 1
                if pos <= 10:
                    a["top10"] += 1
                if pos > releg_cut:
                    a["releg"] += 1
                a["pts_sum"] += r["points"]
                a["pos_sum"] += pos
                a["best"] = min(a["best"], pos)
                a["worst"] = max(a["worst"], pos)
                sa = stat_accum.get(r["team"])
                if sa and sa["matches"]:
                    a["yellows_sum"] += sa["yellows"]
                    a["reds_sum"] += sa["reds"]
                    a["corners_sum"] += sa["corners"]
                    a["match_sum"] += sa["matches"]
            if progress_every and (i + 1) % progress_every == 0 and (i + 1) < runs:
                yield ("progress", i + 1)

        table = []
        for t in teams:
            a = agg[t]
            row = {
                "team": t,
                "title_pct": round(100 * a["title"] / runs, 1),
                "top4_pct": round(100 * a["top4"] / runs, 1),
                "top10_pct": round(100 * a["top10"] / runs, 1),
                "releg_pct": round(100 * a["releg"] / runs, 1),
                "avg_points": round(a["pts_sum"] / runs, 1),
                "avg_position": round(a["pos_sum"] / runs, 2),
                "best_position": a["best"],
                "worst_position": a["worst"],
                "title_count": a["title"],
                "top4_count": a["top4"],
                "top10_count": a["top10"],
                "releg_count": a["releg"],
            }
            if a["match_sum"]:
                # Yellows/reds as average per season; corners per match.
                row["avg_yellows"] = round(a["yellows_sum"] / runs, 1)
                row["avg_reds"] = round(a["reds_sum"] / runs, 1)
                row["avg_corners"] = round(a["corners_sum"] / a["match_sum"], 1)
            table.append(row)
        table.sort(key=lambda r: (r["title_pct"], r["top4_pct"], r["avg_points"]),
                   reverse=True)

        yield ("result", {
            "season": label,
            "runs": runs,
            "teams": teams,
            "table": table,
            "is_next_season": is_next,
        })

    def simulate_batch(self, season: str | None = None, runs: int = 1000,
                       seed: int | None = None) -> dict:
        """
        Run `runs` independent full-season simulations and aggregate how often
        each team wins the title, finishes top 4 / top 10, and is relegated.
        """
        result = None
        for kind, payload in self.iter_simulate_batch(season=season, runs=runs, seed=seed):
            if kind == "result":
                result = payload
        return result


# Lazy singleton so the model loads only once per process.
_predictor: Predictor | None = None


def get_predictor() -> Predictor:
    global _predictor
    if _predictor is None:
        _predictor = Predictor()
    return _predictor


def reset_predictor():
    global _predictor
    _predictor = None
