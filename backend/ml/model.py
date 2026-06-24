"""
Multi-task feedforward neural network (PyTorch) for EPL prediction.

Shared trunk -> three heads:
  * outcome head: 3-class logits (Home win / Draw / Away win)
  * goals head:   two Poisson rate outputs (expected home & away goals)
  * stats head:   per-match statistics (shots, shots on target, corners, fouls,
                  yellow/red cards, offsides for both teams) as Poisson rates

This matches the dissertation's feedforward architecture (Dense-ReLU-Dropout)
while additionally supporting exact-score estimation via Poisson regression,
which is the classical statistical model for football goals (Maher 1982,
Dixon-Coles 1997). The auxiliary statistics head lets the same shared
representation forecast in-match events (e.g. cards) from pre-match inputs.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class EPLNet(nn.Module):
    def __init__(self, n_features: int, n_classes: int = 3, n_stats: int = 14,
                 n_teams: int = 0, embed_dim: int = 8,
                 stat_priors: "list[float] | None" = None,
                 goal_priors: "list[float] | None" = None):
        super().__init__()
        # Per-team embeddings: a learned vector for each club as the home side
        # and (separately) as the away side. This lets the network memorise each
        # team's individual behaviour AND the specific way two teams interact
        # (matchup-specific stats), instead of relying only on aggregate
        # averages. Index `n_teams` is reserved as an out-of-vocabulary slot for
        # clubs never seen in training.
        self.n_teams = n_teams
        self.embed_dim = embed_dim if n_teams > 0 else 0
        if n_teams > 0:
            self.home_embed = nn.Embedding(n_teams + 1, embed_dim)
            self.away_embed = nn.Embedding(n_teams + 1, embed_dim)

        trunk_in = n_features + 2 * self.embed_dim
        # Wider/deeper trunk with BatchNorm for a stronger shared representation.
        # BatchNorm stabilises training and lets us train for many more epochs.
        self.trunk = nn.Sequential(
            nn.Linear(trunk_in, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(0.30),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(0.25),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.20),
        )
        self.outcome_head = nn.Linear(64, n_classes)
        # Two outputs -> softplus later gives positive Poisson rates.
        self.goals_head = nn.Linear(64, 2)
        # Auxiliary match-statistics head -> positive Poisson rates.
        self.stats_head = nn.Linear(64, n_stats)

        # Calibrate the Poisson heads' average output to the empirical means.
        # BatchNorm makes the trunk output `z` roughly zero-mean, so the mean of
        # each softplus(head(z)) output is controlled almost entirely by the
        # head's bias. Initialising the bias to inverse_softplus(mean) makes the
        # network output realistic per-match rates from the very first epoch,
        # which keeps corners/cards/etc. well-calibrated even though early
        # stopping selects the model before the auxiliary head fully converges.
        if goal_priors is not None:
            self._init_poisson_bias(self.goals_head, goal_priors)
        if stat_priors is not None:
            self._init_poisson_bias(self.stats_head, stat_priors)

    @staticmethod
    def _init_poisson_bias(head: nn.Linear, priors: "list[float]"):
        """Set a Linear head's bias so softplus(bias) ~= the given prior means."""
        with torch.no_grad():
            head.weight.mul_(0.1)  # start near the prior; let training add signal
            for j, m in enumerate(priors):
                if j >= head.bias.numel():
                    break
                m = max(float(m), 1e-3)
                # inverse softplus: b such that log(1 + e^b) = m
                head.bias[j] = float(torch.log(torch.expm1(torch.tensor(m))))

    def forward(self, x: torch.Tensor, home_idx: torch.Tensor | None = None,
                away_idx: torch.Tensor | None = None):
        if self.n_teams > 0 and home_idx is not None and away_idx is not None:
            h_vec = self.home_embed(home_idx)
            a_vec = self.away_embed(away_idx)
            x = torch.cat([x, h_vec, a_vec], dim=1)
        z = self.trunk(x)
        outcome_logits = self.outcome_head(z)
        goal_rates = torch.nn.functional.softplus(self.goals_head(z)) + 1e-6
        stat_rates = torch.nn.functional.softplus(self.stats_head(z)) + 1e-6
        return outcome_logits, goal_rates, stat_rates
