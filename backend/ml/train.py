"""
Train the multi-task EPL model.

Pipeline:
  1. Load ml/data/epl_matches.csv (run download_data.py first).
  2. Build the 15-feature vectors + targets (features.build_features).
  3. Standardize features (StandardScaler) and do a stratified 80/20 split.
  4. Train EPLNet with a combined loss:
        CrossEntropy(outcome) + PoissonNLL(home goals) + PoissonNLL(away goals)
     using Adam + early stopping on the validation outcome accuracy.
  5. Save artifacts to ml/artifacts/:
        model.pt, scaler.pkl, metrics.json, metadata.json

Usage:
    python -m ml.train
"""

from __future__ import annotations

import json
import os
import time

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from ml.features import FEATURE_NAMES, STAT_TARGETS, build_features
from ml.model import EPLNet

DATA_CSV = os.path.join(os.path.dirname(__file__), "data", "epl_matches.csv")
ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

EPOCHS = 1500          # hard cap per restart (early stopping usually hits first)
PATIENCE = 150         # epochs without val-loss improvement before a restart ends
MIN_TRAIN_SECONDS = 1800  # train for at least this long (30 min), spawning fresh
                          # restarts and keeping the globally best model
BATCH_SIZE = 128
LR = 1.5e-3
WEIGHT_DECAY = 1e-4
SEED = 42
STATS_WEIGHT = 0.5   # weight of the auxiliary stats loss vs. outcome/goals.
                     # The stats loss is averaged over 14 outputs, so the
                     # effective per-stat weight is STATS_WEIGHT/14. Keeping this
                     # high enough lets the stats head (corners/cards/etc.)
                     # converge to realistic per-match means before the combined
                     # validation loss selects the best epoch.
ODDS_DROPOUT = 0.35  # fraction of training rows where real-odds probs are
                     # replaced by Elo-derived probs (matches inference regime)
RECENCY_HALFLIFE_YEARS = 4.0  # sample weight halves every N years into the past,
                              # so recent matches count more in the loss
RECENCY_MIN_WEIGHT = 0.25     # floor so old matches still contribute some signal


def _set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_dataset() -> pd.DataFrame:
    if not os.path.exists(DATA_CSV):
        raise FileNotFoundError(
            f"{DATA_CSV} not found. Run `python -m ml.download_data` first."
        )
    raw = pd.read_csv(DATA_CSV, parse_dates=["date"])
    feats = build_features(raw)
    # Drop the early warm-up matches with no history at all (all-zero form rows
    # are imputed, but we keep them; the scaler handles scale).
    return feats


def train():
    _set_seed(SEED)
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    data = load_dataset()
    X = data[FEATURE_NAMES].astype(float).values
    y_out = data["label"].astype(int).values
    y_hg = data["home_goals"].astype(float).values
    y_ag = data["away_goals"].astype(float).values
    # Auxiliary statistics targets (NaN before ~2000/01) + availability mask.
    y_stats = data[STAT_TARGETS].astype(float).values
    stats_mask = ~np.isnan(y_stats).any(axis=1)
    # Empirical per-stat means (over rows that actually have statistics) used to
    # calibrate the stats head's bias so its average output matches reality.
    stat_priors = np.nanmean(
        np.where(stats_mask[:, None], y_stats, np.nan), axis=0
    ).tolist()
    y_stats = np.nan_to_num(y_stats, nan=0.0)
    # Empirical mean goals to calibrate the goals head's bias the same way.
    goal_priors = [float(np.mean(y_hg)), float(np.mean(y_ag))]

    # Elo-derived 1X2 triple (always available) used for odds-dropout so the
    # model stays accurate at inference, where only Elo probs exist.
    elo_triple = data[["elo_prob_home", "elo_prob_draw", "elo_prob_away"]].astype(float).values
    market_idx = [FEATURE_NAMES.index(c) for c in
                  ("market_prob_home", "market_prob_draw", "market_prob_away")]

    # Per-team identity indices for the model's embeddings. A sorted vocabulary
    # maps each club to an integer; index == len(teams) is the OOV slot.
    teams = sorted(set(data["home_team"]) | set(data["away_team"]))
    team_to_idx = {t: i for i, t in enumerate(teams)}
    oov_idx = len(teams)
    home_idx_all = data["home_team"].map(lambda t: team_to_idx.get(t, oov_idx)).astype(int).values
    away_idx_all = data["away_team"].map(lambda t: team_to_idx.get(t, oov_idx)).astype(int).values

    # Recency weights: matches decay exponentially with age (half every
    # RECENCY_HALFLIFE_YEARS) so recent seasons drive the fit, with a floor so
    # older matches still contribute. Age is measured from the most recent match.
    dates = pd.to_datetime(data["date"])
    age_years = (dates.max() - dates).dt.days.values / 365.25
    recency_w = np.maximum(
        0.5 ** (age_years / RECENCY_HALFLIFE_YEARS), RECENCY_MIN_WEIGHT
    ).astype(float)

    (X_tr, X_te, yo_tr, yo_te, hg_tr, hg_te, ag_tr, ag_te,
     ys_tr, ys_te, sm_tr, sm_te, elo_tr, elo_te,
     hi_tr, hi_te, ai_tr, ai_te, rw_tr, rw_te) = train_test_split(
        X, y_out, y_hg, y_ag, y_stats, stats_mask, elo_triple,
        home_idx_all, away_idx_all, recency_w,
        test_size=0.20, random_state=SEED, stratify=y_out
    )

    # Odds-dropout: for a random subset of training rows, swap the real-odds
    # probability triple for the Elo-derived one.
    rng = np.random.default_rng(SEED)
    drop = rng.random(X_tr.shape[0]) < ODDS_DROPOUT
    X_tr[np.ix_(drop, market_idx)] = elo_tr[drop]

    scaler = StandardScaler().fit(X_tr)
    X_tr = scaler.transform(X_tr)
    X_te = scaler.transform(X_te)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    to_t = lambda arr, dt=torch.float32: torch.tensor(arr, dtype=dt, device=device)

    Xtr_t = to_t(X_tr)
    Xte_t = to_t(X_te)
    yo_tr_t = to_t(yo_tr, torch.long)
    yo_te_t = to_t(yo_te, torch.long)
    hg_tr_t, ag_tr_t = to_t(hg_tr), to_t(ag_tr)
    hg_te_t, ag_te_t = to_t(hg_te), to_t(ag_te)
    ys_tr_t = to_t(ys_tr)
    ys_te_t = to_t(ys_te)
    sm_tr_t = to_t(sm_tr.astype(float))
    sm_te_t = to_t(sm_te.astype(float))
    hi_tr_t = to_t(hi_tr, torch.long)
    hi_te_t = to_t(hi_te, torch.long)
    ai_tr_t = to_t(ai_tr, torch.long)
    ai_te_t = to_t(ai_te, torch.long)
    rw_tr_t = to_t(rw_tr)
    rw_te_t = to_t(rw_te)

    n_teams = len(teams)
    model = EPLNet(n_features=len(FEATURE_NAMES), n_stats=len(STAT_TARGETS),
                   n_teams=n_teams, stat_priors=stat_priors,
                   goal_priors=goal_priors).to(device)

    # Class weights (softened inverse frequency) to counter the home/draw/away
    # imbalance without collapsing accuracy: the square root keeps the draw
    # class learnable while preserving overall performance.
    counts = np.bincount(yo_tr, minlength=3).astype(float)
    weights = np.sqrt(counts.sum() / (3.0 * counts))
    class_weights = torch.tensor(weights, dtype=torch.float32, device=device)
    # Per-sample reduction so each match can be weighted by its recency.
    ce_loss = nn.CrossEntropyLoss(weight=class_weights, reduction="none")
    poisson_loss = nn.PoissonNLLLoss(log_input=False, full=True, reduction="none")

    def _weighted(per_sample, w):
        """Recency-weighted mean of a per-sample loss vector."""
        return (per_sample * w).sum() / w.sum()

    n = Xtr_t.shape[0]

    def _run_restart(restart_idx: int):
        """Train one model from scratch; return its best (state, val_loss, acc, f1)."""
        _set_seed(SEED + restart_idx)
        net = EPLNet(n_features=len(FEATURE_NAMES), n_stats=len(STAT_TARGETS),
                     n_teams=n_teams, stat_priors=stat_priors,
                     goal_priors=goal_priors).to(device)
        opt = torch.optim.Adam(net.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
        # Cosine schedule gently anneals the learning rate over the long run.
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)

        r_best_loss, r_best_acc, r_best_f1, r_best_state, wait = (
            float("inf"), 0.0, 0.0, None, 0
        )
        for epoch in range(1, EPOCHS + 1):
            net.train()
            perm = torch.randperm(n, device=device)
            for i in range(0, n, BATCH_SIZE):
                idx = perm[i:i + BATCH_SIZE]
                # BatchNorm needs >1 sample; skip a trailing singleton batch.
                if idx.numel() < 2:
                    continue
                opt.zero_grad()
                logits, rates, stats = net(Xtr_t[idx], hi_tr_t[idx], ai_tr_t[idx])
                w = rw_tr_t[idx]
                loss = (
                    _weighted(ce_loss(logits, yo_tr_t[idx]), w)
                    + _weighted(poisson_loss(rates[:, 0], hg_tr_t[idx]), w)
                    + _weighted(poisson_loss(rates[:, 1], ag_tr_t[idx]), w)
                )
                # Auxiliary stats loss, only on rows that actually have statistics.
                m = sm_tr_t[idx] > 0.5
                if m.any():
                    stats_ps = poisson_loss(stats[m], ys_tr_t[idx][m]).mean(dim=1)
                    loss = loss + STATS_WEIGHT * _weighted(stats_ps, w[m])
                loss.backward()
                opt.step()

            sched.step()

            # --- validation ---
            net.eval()
            with torch.no_grad():
                logits, v_rates, v_stats = net(Xte_t, hi_te_t, ai_te_t)
                val_pred = logits.argmax(dim=1).cpu().numpy()
                val_acc = accuracy_score(yo_te, val_pred)
                val_f1 = f1_score(yo_te, val_pred, average="macro", zero_division=0)
                # Combined validation loss across all three heads (recency-weighted
                # to match the training objective).
                v_loss = (
                    _weighted(ce_loss(logits, yo_te_t), rw_te_t)
                    + _weighted(poisson_loss(v_rates[:, 0], hg_te_t), rw_te_t)
                    + _weighted(poisson_loss(v_rates[:, 1], ag_te_t), rw_te_t)
                )
                vm = sm_te_t > 0.5
                if vm.any():
                    v_stats_ps = poisson_loss(v_stats[vm], ys_te_t[vm]).mean(dim=1)
                    v_loss = v_loss + STATS_WEIGHT * _weighted(v_stats_ps, rw_te_t[vm])
                val_loss = float(v_loss.item())

            # Keep the epoch with the lowest combined validation loss; this keeps
            # the goals/stats heads improving even after outcome accuracy plateaus.
            if val_loss < r_best_loss:
                r_best_loss, r_best_f1, r_best_acc, wait = val_loss, val_f1, val_acc, 0
                r_best_state = {k: v.cpu().clone() for k, v in net.state_dict().items()}
            else:
                wait += 1

            if epoch % 10 == 0 or epoch == 1:
                print(f"[restart {restart_idx}] Epoch {epoch:4d} | "
                      f"val_acc = {val_acc:.4f} | val_f1 = {val_f1:.4f} | "
                      f"val_loss = {val_loss:.4f} | best_loss = {r_best_loss:.4f}",
                      flush=True)

            if wait >= PATIENCE:
                print(f"[restart {restart_idx}] Early stopping at epoch {epoch} "
                      f"(best acc = {r_best_acc:.4f}, macro-F1 = {r_best_f1:.4f}).",
                      flush=True)
                break

        return r_best_state, r_best_loss, r_best_acc, r_best_f1

    # Multi-restart: keep spawning fresh models (different seeds) until we have
    # trained for at least MIN_TRAIN_SECONDS, retaining the globally best model
    # (lowest combined validation loss across all heads).
    best_val_loss, best_acc, best_f1, best_state = float("inf"), 0.0, 0.0, None
    start = time.time()
    restart_idx = 0
    while True:
        elapsed = time.time() - start
        print(f"\n=== Restart {restart_idx} (elapsed {elapsed/60:.1f} min) ===",
              flush=True)
        state, r_loss, r_acc, r_f1 = _run_restart(restart_idx)
        if state is not None and r_loss < best_val_loss:
            best_val_loss, best_acc, best_f1, best_state = r_loss, r_acc, r_f1, state
            print(f"--> New global best: val_loss = {best_val_loss:.4f}, "
                  f"acc = {best_acc:.4f}, macro-F1 = {best_f1:.4f}", flush=True)
        restart_idx += 1
        if time.time() - start >= MIN_TRAIN_SECONDS:
            break

    total_min = (time.time() - start) / 60.0
    print(f"\nTrained {restart_idx} restart(s) over {total_min:.1f} min. "
          f"Best val_loss = {best_val_loss:.4f}, acc = {best_acc:.4f}, "
          f"macro-F1 = {best_f1:.4f}.", flush=True)

    if best_state is not None:
        model.load_state_dict(best_state)

    # --- final evaluation ---
    model.eval()
    with torch.no_grad():
        logits, rates, stats_pred = model(Xte_t, hi_te_t, ai_te_t)
        pred = logits.argmax(dim=1).cpu().numpy()

    acc = accuracy_score(yo_te, pred)
    report = classification_report(
        yo_te, pred, target_names=["Home", "Draw", "Away"],
        output_dict=True, zero_division=0,
    )
    print(f"\nFinal test accuracy: {acc:.4f}")
    print(classification_report(yo_te, pred, target_names=["Home", "Draw", "Away"],
                                zero_division=0))

    # Mean absolute error of the auxiliary statistics head (where available).
    stats_mae = {}
    sp = stats_pred.cpu().numpy()
    te_mask = sm_te.astype(bool)
    if te_mask.any():
        abs_err = np.abs(sp[te_mask] - ys_te[te_mask])
        for j, name in enumerate(STAT_TARGETS):
            stats_mae[name] = float(abs_err[:, j].mean())
        print("\nStats head MAE:")
        for name, v in stats_mae.items():
            print(f"  {name:16s} {v:.2f}")

    # --- save artifacts ---
    torch.save(model.state_dict(), os.path.join(ARTIFACT_DIR, "model.pt"))
    joblib.dump(scaler, os.path.join(ARTIFACT_DIR, "scaler.pkl"))

    with open(os.path.join(ARTIFACT_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"accuracy": acc, "report": report, "stats_mae": stats_mae}, f, indent=2)

    with open(os.path.join(ARTIFACT_DIR, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump({
            "feature_names": FEATURE_NAMES,
            "n_features": len(FEATURE_NAMES),
            "classes": ["H", "D", "A"],
            "stat_targets": STAT_TARGETS,
            "n_stats": len(STAT_TARGETS),
            "teams": teams,
            "n_teams": n_teams,
            "n_train": int(X_tr.shape[0]),
            "n_test": int(X_te.shape[0]),
        }, f, indent=2)

    print(f"\nArtifacts saved to {ARTIFACT_DIR}")


if __name__ == "__main__":
    train()
