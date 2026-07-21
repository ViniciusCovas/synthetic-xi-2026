#!/usr/bin/env python3
"""Build externally contextualized candidate profiles for the definitive v2 experiment.

The model uses only the frozen 2025-2026 player-detail cache plus provider fixture
metadata. It creates a transparent results-based Elo network, measures each player's
minute-weighted opponent and competition strength, rebuilds goalkeeper quality from
shot-stopping/distribution proxies, and produces role-ready profiles with explicit
traceability and sensitivity outputs.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BATCH_DIR = Path("data/lake/batches")
CONTEXT = Path("data/lake/v2_fixture_context.csv.gz")
CANDIDATES = Path("data/audits/position_ontology_v3/final_candidate_roles.csv")
OUT = Path("data/audits/external_validity_v2")
PROFILES = OUT / "strength_adjusted_candidate_roles.csv"
TOP10 = OUT / "role_top10_plausibility.csv"
STATUS = OUT / "strength_model_status.json"
ROLES = ["GK", "RB", "RCB", "LCB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
DIMS = ["build_up", "progression", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]
ROLE_WEIGHTS = {
    "GK": {"goalkeeping": .55, "build_up": .20, "retention": .15, "overall_final": .10},
    "RB": {"defending": .22, "duels": .14, "build_up": .18, "progression": .28, "creation": .18},
    "LB": {"defending": .22, "duels": .14, "build_up": .18, "progression": .28, "creation": .18},
    "RCB": {"defending": .33, "duels": .25, "build_up": .22, "retention": .20},
    "LCB": {"defending": .33, "duels": .25, "build_up": .22, "retention": .20},
    "DM": {"defending": .25, "duels": .18, "build_up": .25, "retention": .20, "progression": .12},
    "CM": {"build_up": .23, "retention": .20, "progression": .20, "creation": .16, "defending": .12, "duels": .09},
    "AM": {"creation": .32, "progression": .24, "finishing": .17, "retention": .15, "build_up": .12},
    "RW": {"progression": .29, "creation": .23, "finishing": .22, "retention": .14, "duels": .12},
    "LW": {"progression": .29, "creation": .23, "finishing": .22, "retention": .14, "duels": .12},
    "ST": {"finishing": .44, "creation": .12, "progression": .12, "duels": .18, "retention": .14},
}
NATIONAL_PATTERNS = (
    "world cup", "qualification", "qualifiers", "nations league", "friendlies",
    "copa america", "gold cup", "africa cup of nations", "asian cup",
    "european championship", "euro championship", "ofc nations", "arab cup",
    "africa nations championship", "olympics men", "olympic games men",
)
CLUB_EXCLUSIONS = ("club world cup", "uefa champions league", "afc champions league", "caf champions league", "concacaf champions", "copa libertadores")


def truth(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def safe_numeric(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def load_player_matches(candidate_ids: set[int]) -> pd.DataFrame:
    rows = []
    columns = [
        "fixture_id", "date_utc", "league_id", "league_name", "season",
        "in_current_window", "in_pre_world_cup_window", "team_id", "team_name",
        "player_id", "player_name", "minutes", "provider_position", "saves",
        "goals_conceded", "passes_total", "passes_accuracy_raw", "penalty_saved",
    ]
    for path in sorted(BATCH_DIR.glob("*players*.csv*")):
        header = pd.read_csv(path, nrows=0).columns
        use = [column for column in columns if column in header]
        if not {"fixture_id", "team_id", "player_id", "minutes"}.issubset(use):
            continue
        frame = pd.read_csv(path, usecols=use, low_memory=False)
        for column in columns:
            if column not in frame:
                frame[column] = np.nan
        safe_numeric(frame, ["fixture_id", "league_id", "season", "team_id", "player_id", "minutes", "saves", "goals_conceded", "passes_total", "passes_accuracy_raw", "penalty_saved"])
        frame = frame.loc[frame.player_id.isin(candidate_ids)]
        if "in_current_window" in frame:
            frame = frame.loc[truth(frame.in_current_window)]
        rows.append(frame[columns])
    if not rows:
        raise RuntimeError("no cached player match rows for reviewed candidates")
    merged = pd.concat(rows, ignore_index=True)
    merged = merged.dropna(subset=["fixture_id", "team_id", "player_id"]).copy()
    for column in ["fixture_id", "team_id", "player_id"]:
        merged[column] = merged[column].astype(int)
    quality_columns = ["minutes", "saves", "goals_conceded", "passes_total", "passes_accuracy_raw", "penalty_saved"]
    merged["_quality"] = merged[quality_columns].notna().sum(axis=1)
    merged = merged.sort_values(["fixture_id", "team_id", "player_id", "_quality"]).drop_duplicates(["fixture_id", "team_id", "player_id"], keep="last")
    return merged.drop(columns="_quality")


def is_national_competition(name: object) -> bool:
    text = str(name or "").strip().lower()
    if any(exclusion in text for exclusion in CLUB_EXCLUSIONS):
        return False
    return any(pattern in text for pattern in NATIONAL_PATTERNS)


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}
        self.size: dict[int, int] = {}

    def add(self, value: int) -> None:
        if value not in self.parent:
            self.parent[value] = value
            self.size[value] = 1

    def find(self, value: int) -> int:
        self.add(value)
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a == b:
            return
        if self.size[a] < self.size[b]:
            a, b = b, a
        self.parent[b] = a
        self.size[a] += self.size[b]


def build_elo(fixtures: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = fixtures.copy()
    frame["date_utc"] = pd.to_datetime(frame.date_utc, utc=True, errors="coerce")
    safe_numeric(frame, ["home_team_id", "away_team_id", "home_goals", "away_goals", "league_id"])
    frame = frame.dropna(subset=["home_team_id", "away_team_id", "home_goals", "away_goals", "date_utc"]).copy()
    for column in ["home_team_id", "away_team_id", "league_id"]:
        frame[column] = frame[column].astype(int)
    frame["domain"] = np.where(frame.league_name.map(is_national_competition), "national", "club")
    frame = frame.sort_values(["date_utc", "fixture_id"])

    ratings: dict[tuple[str, int], float] = defaultdict(lambda: 1500.0)
    uf_by_domain = {"club": UnionFind(), "national": UnionFind()}
    competition_sets: dict[tuple[str, int], set[int]] = defaultdict(set)
    team_competitions: dict[tuple[str, int], set[int]] = defaultdict(set)
    for row in frame.itertuples(index=False):
        domain = str(row.domain)
        home = int(row.home_team_id)
        away = int(row.away_team_id)
        hg = float(row.home_goals)
        ag = float(row.away_goals)
        competition = int(row.league_id)
        uf_by_domain[domain].union(home, away)
        competition_sets[(domain, competition)].update([home, away])
        team_competitions[(domain, home)].add(competition)
        team_competitions[(domain, away)].add(competition)
        rh = ratings[(domain, home)]
        ra = ratings[(domain, away)]
        home_advantage = 45.0 if domain == "club" else 25.0
        expected_home = 1.0 / (1.0 + 10.0 ** ((ra - (rh + home_advantage)) / 400.0))
        actual_home = 1.0 if hg > ag else 0.0 if hg < ag else 0.5
        margin = abs(hg - ag)
        multiplier = 1.0 if margin <= 1 else 1.0 + 0.35 * math.log1p(margin - 1.0)
        k = 22.0 if domain == "club" else 26.0
        delta = k * multiplier * (actual_home - expected_home)
        ratings[(domain, home)] = rh + delta
        ratings[(domain, away)] = ra - delta

    team_rows = []
    for (domain, team_id), rating in ratings.items():
        uf = uf_by_domain[domain]
        root = uf.find(team_id)
        component_size = uf.size[uf.find(root)]
        team_rows.append({
            "domain": domain,
            "team_id": team_id,
            "elo": rating,
            "component_id": f"{domain}:{root}",
            "component_size": component_size,
            "competition_count": len(team_competitions[(domain, team_id)]),
            "cross_competition_bridge": len(team_competitions[(domain, team_id)]) >= 2,
        })
    teams = pd.DataFrame(team_rows)
    if teams.empty:
        raise RuntimeError("could not build Elo ratings")
    teams["elo_z"] = 0.0
    for domain, group in teams.groupby("domain"):
        median = float(group.elo.median())
        mad = float((group.elo - median).abs().median())
        scale = max(1.0, 1.4826 * mad)
        teams.loc[group.index, "elo_z"] = ((group.elo - median) / scale).clip(-4, 4)

    competition_rows = []
    name_by_key = frame.groupby(["domain", "league_id"], as_index=False).agg(
        competition_name=("league_name", "first"),
        competition_country=("league_country", "first"),
        matches=("fixture_id", "nunique"),
    )
    team_lookup = teams.set_index(["domain", "team_id"])
    for (domain, competition), team_ids in competition_sets.items():
        values = [float(team_lookup.loc[(domain, team_id), "elo"]) for team_id in team_ids if (domain, team_id) in team_lookup.index]
        zvalues = [float(team_lookup.loc[(domain, team_id), "elo_z"]) for team_id in team_ids if (domain, team_id) in team_lookup.index]
        competition_rows.append({
            "domain": domain,
            "league_id": competition,
            "competition_strength": float(np.median(values)) if values else 1500.0,
            "competition_strength_z": float(np.median(zvalues)) if zvalues else 0.0,
            "rated_teams": len(values),
        })
    competitions = name_by_key.merge(pd.DataFrame(competition_rows), on=["domain", "league_id"], how="left")
    return teams, competitions


def logit_adjust(value: float, shift: float) -> float:
    if not np.isfinite(value):
        return np.nan
    clipped = min(1 - 1e-6, max(1e-6, float(value)))
    logit = math.log(clipped / (1 - clipped))
    return 1.0 / (1.0 + math.exp(-(logit + shift)))


def percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    ranked = values.rank(method="average", pct=True)
    return ranked if higher_is_better else 1.0 - ranked + (1.0 / max(1, values.notna().sum()))


def goalkeeper_model(matches: pd.DataFrame, candidate_frame: pd.DataFrame, team_ratings: pd.DataFrame) -> pd.DataFrame:
    gk_ids = set(candidate_frame.loc[candidate_frame.final_role.eq("GK"), "player_id"].astype(int))
    gk = matches.loc[matches.player_id.isin(gk_ids) & matches.minutes.gt(0)].copy()
    for column in ["saves", "goals_conceded", "passes_total", "passes_accuracy_raw", "penalty_saved"]:
        gk[column] = pd.to_numeric(gk[column], errors="coerce").fillna(0.0)
    gk["sot_faced"] = gk.saves + gk.goals_conceded
    gk["clean_sheet_60"] = ((gk.minutes >= 60) & (gk.goals_conceded <= 0)).astype(float)
    gk["appearance_60"] = (gk.minutes >= 60).astype(float)
    gk["accurate_passes"] = np.minimum(gk.passes_accuracy_raw, gk.passes_total).clip(lower=0)

    team_lookup = team_ratings.set_index(["domain", "team_id"])
    own_elo = []
    opp_elo = []
    for row in gk.itertuples(index=False):
        domain = str(row.domain)
        own_key = (domain, int(row.team_id))
        opp_key = (domain, int(row.opponent_team_id))
        own_elo.append(float(team_lookup.loc[own_key, "elo"]) if own_key in team_lookup.index else 1500.0)
        opp_elo.append(float(team_lookup.loc[opp_key, "elo"]) if opp_key in team_lookup.index else 1500.0)
    gk["own_elo"] = own_elo
    gk["opponent_elo"] = opp_elo
    diff = (gk.opponent_elo - gk.own_elo) / 400.0
    y = np.log(gk.goals_conceded + 0.5)
    x = np.column_stack([np.ones(len(gk)), diff.to_numpy()])
    beta, *_ = np.linalg.lstsq(x, y.to_numpy(), rcond=None)
    expected_full = np.maximum(0.05, np.exp(x @ beta) - 0.5)
    gk["expected_gc"] = expected_full * (gk.minutes.clip(lower=1, upper=120) / 90.0)
    gk["goals_prevented_proxy"] = gk.expected_gc - gk.goals_conceded

    aggregate = gk.groupby("player_id", as_index=False).agg(
        gk_minutes=("minutes", "sum"),
        gk_matches=("fixture_id", "nunique"),
        saves=("saves", "sum"),
        goals_conceded=("goals_conceded", "sum"),
        sot_faced=("sot_faced", "sum"),
        passes=("passes_total", "sum"),
        accurate_passes=("accurate_passes", "sum"),
        penalty_saves=("penalty_saved", "sum"),
        clean_sheets=("clean_sheet_60", "sum"),
        appearances_60=("appearance_60", "sum"),
        expected_gc=("expected_gc", "sum"),
        goals_prevented=("goals_prevented_proxy", "sum"),
    )
    total_sot = max(1.0, float(aggregate.sot_faced.sum()))
    save_prior = float(aggregate.saves.sum() / total_sot)
    pass_prior = float(aggregate.accurate_passes.sum() / max(1.0, aggregate.passes.sum()))
    clean_prior = float(aggregate.clean_sheets.sum() / max(1.0, aggregate.appearances_60.sum()))
    penalty_attempts_proxy = aggregate.penalty_saves + 1.0
    penalty_prior = float(aggregate.penalty_saves.sum() / max(1.0, penalty_attempts_proxy.sum()))
    aggregate["bayes_save_rate"] = (aggregate.saves + 40.0 * save_prior) / (aggregate.sot_faced + 40.0)
    aggregate["bayes_pass_accuracy"] = (aggregate.accurate_passes + 200.0 * pass_prior) / (aggregate.passes + 200.0)
    aggregate["bayes_clean_sheet_rate"] = (aggregate.clean_sheets + 10.0 * clean_prior) / (aggregate.appearances_60 + 10.0)
    aggregate["bayes_penalty_save_rate"] = (aggregate.penalty_saves + 5.0 * penalty_prior) / (penalty_attempts_proxy + 5.0)
    aggregate["goals_prevented_p90"] = aggregate.goals_prevented / aggregate.gk_minutes.clip(lower=1) * 90.0
    aggregate["save_pct_component"] = percentile(aggregate.bayes_save_rate)
    aggregate["goals_prevented_component"] = percentile(aggregate.goals_prevented_p90)
    aggregate["clean_sheet_component"] = percentile(aggregate.bayes_clean_sheet_rate)
    aggregate["distribution_component"] = percentile(aggregate.bayes_pass_accuracy)
    aggregate["penalty_component"] = percentile(aggregate.bayes_penalty_save_rate)
    aggregate["goalkeeper_score_unshrunk"] = (
        .50 * aggregate.save_pct_component
        + .20 * aggregate.goals_prevented_component
        + .15 * aggregate.clean_sheet_component
        + .10 * aggregate.distribution_component
        + .05 * aggregate.penalty_component
    )
    reliability = aggregate.gk_minutes / (aggregate.gk_minutes + 900.0)
    aggregate["goalkeeping_v2"] = 0.5 + reliability * (aggregate.goalkeeper_score_unshrunk - 0.5)
    aggregate["goalkeeper_model_reliability"] = reliability
    aggregate["gk_proxy_model"] = "Bayesian save rate + Elo-adjusted concession residual + clean sheets + distribution + penalties"
    return aggregate


def role_score(frame: pd.DataFrame, role: str) -> pd.Series:
    score = pd.Series(0.0, index=frame.index)
    for metric, weight in ROLE_WEIGHTS[role].items():
        score += pd.to_numeric(frame[metric], errors="coerce") * weight
    return score


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not CONTEXT.exists() or not CANDIDATES.exists():
        raise RuntimeError("fixture context and candidate table are required")
    candidates = pd.read_csv(CANDIDATES, low_memory=False)
    candidates["player_id"] = pd.to_numeric(candidates.player_id, errors="coerce")
    candidates = candidates.dropna(subset=["player_id"]).copy()
    candidates.player_id = candidates.player_id.astype(int)
    candidates["final_role"] = candidates.final_role.astype(str).str.upper()
    candidates = candidates.loc[candidates.final_role.isin(ROLES) & truth(candidates.final_candidate_eligible)].copy()
    if candidates.empty:
        raise RuntimeError("no eligible reviewed candidate roles")

    context = pd.read_csv(CONTEXT, low_memory=False)
    safe_numeric(context, ["fixture_id", "league_id", "season", "home_team_id", "away_team_id", "home_goals", "away_goals"])
    context = context.dropna(subset=["fixture_id", "home_team_id", "away_team_id"]).copy()
    for column in ["fixture_id", "home_team_id", "away_team_id"]:
        context[column] = context[column].astype(int)
    context = context.drop_duplicates("fixture_id", keep="last")
    context["domain"] = np.where(context.league_name.map(is_national_competition), "national", "club")

    team_ratings, competition_ratings = build_elo(context)
    team_ratings.to_csv(OUT / "team_elo_ratings.csv", index=False)
    competition_ratings.to_csv(OUT / "competition_strength.csv", index=False)

    matches = load_player_matches(set(candidates.player_id))
    context_columns = [
        "fixture_id", "date_utc", "league_id", "league_name", "league_country", "season",
        "home_team_id", "home_team_name", "away_team_id", "away_team_name",
        "home_goals", "away_goals", "domain",
    ]
    matches = matches.drop(columns=[c for c in ["date_utc", "league_id", "league_name", "season"] if c in matches], errors="ignore").merge(context[context_columns], on="fixture_id", how="left")
    matches["is_home"] = matches.team_id.eq(matches.home_team_id)
    matches["opponent_team_id"] = np.where(matches.is_home, matches.away_team_id, matches.home_team_id)
    matches["opponent_team_name"] = np.where(matches.is_home, matches.away_team_name, matches.home_team_name)
    matches["own_goals"] = np.where(matches.is_home, matches.home_goals, matches.away_goals)
    matches["opponent_goals"] = np.where(matches.is_home, matches.away_goals, matches.home_goals)
    safe_numeric(matches, ["opponent_team_id", "minutes"])
    matches = matches.dropna(subset=["opponent_team_id", "domain"]).copy()
    matches.opponent_team_id = matches.opponent_team_id.astype(int)

    team_lookup = team_ratings.set_index(["domain", "team_id"])
    comp_lookup = competition_ratings.set_index(["domain", "league_id"])
    opponent_elo = []
    opponent_z = []
    own_elo = []
    comp_strength = []
    comp_z = []
    component_size = []
    bridge = []
    for row in matches.itertuples(index=False):
        domain = str(row.domain)
        own = (domain, int(row.team_id))
        opp = (domain, int(row.opponent_team_id))
        comp = (domain, int(row.league_id))
        own_row = team_lookup.loc[own] if own in team_lookup.index else None
        opp_row = team_lookup.loc[opp] if opp in team_lookup.index else None
        comp_row = comp_lookup.loc[comp] if comp in comp_lookup.index else None
        own_elo.append(float(own_row.elo) if own_row is not None else 1500.0)
        opponent_elo.append(float(opp_row.elo) if opp_row is not None else 1500.0)
        opponent_z.append(float(opp_row.elo_z) if opp_row is not None else 0.0)
        comp_strength.append(float(comp_row.competition_strength) if comp_row is not None else 1500.0)
        comp_z.append(float(comp_row.competition_strength_z) if comp_row is not None else 0.0)
        component_size.append(int(opp_row.component_size) if opp_row is not None else 1)
        bridge.append(bool(opp_row.cross_competition_bridge) if opp_row is not None else False)
    matches["own_team_elo"] = own_elo
    matches["opponent_elo"] = opponent_elo
    matches["opponent_strength_z"] = opponent_z
    matches["competition_strength"] = comp_strength
    matches["competition_strength_z"] = comp_z
    matches["opponent_component_size"] = component_size
    matches["opponent_cross_competition_bridge"] = bridge
    matches["context_strength_z"] = 0.70 * matches.opponent_strength_z + 0.30 * matches.competition_strength_z
    matches.to_csv(OUT / "candidate_match_context.csv.gz", index=False, compression="gzip")

    weighted = matches.copy()
    weighted["weight"] = weighted.minutes.clip(lower=0)
    for metric in ["opponent_elo", "opponent_strength_z", "competition_strength", "competition_strength_z", "context_strength_z", "opponent_component_size"]:
        weighted[f"w_{metric}"] = weighted[metric] * weighted.weight
    aggregate = weighted.groupby("player_id", as_index=False).agg(
        context_minutes=("weight", "sum"),
        context_matches=("fixture_id", "nunique"),
        opponent_strength_adjusted_num=("w_opponent_elo", "sum"),
        opponent_strength_z_num=("w_opponent_strength_z", "sum"),
        competition_strength_num=("w_competition_strength", "sum"),
        competition_strength_z_num=("w_competition_strength_z", "sum"),
        context_strength_z_num=("w_context_strength_z", "sum"),
        component_size_num=("w_opponent_component_size", "sum"),
        bridge_match_count=("opponent_cross_competition_bridge", "sum"),
    )
    denominator = aggregate.context_minutes.replace(0, np.nan)
    aggregate["opponent_strength_adjusted"] = aggregate.opponent_strength_adjusted_num / denominator
    aggregate["opponent_strength_z"] = aggregate.opponent_strength_z_num / denominator
    aggregate["competition_strength"] = aggregate.competition_strength_num / denominator
    aggregate["competition_strength_z"] = aggregate.competition_strength_z_num / denominator
    aggregate["context_strength_z"] = aggregate.context_strength_z_num / denominator
    aggregate["opponent_component_size"] = aggregate.component_size_num / denominator

    def dominant(group: pd.DataFrame, domain: str | None, column: str) -> object:
        current = group if domain is None else group.loc[group.domain.eq(domain)]
        if current.empty:
            return ""
        totals = current.groupby(column, dropna=True).minutes.sum().sort_values(ascending=False)
        return totals.index[0] if len(totals) else ""

    trace_rows = []
    for player_id, group in matches.groupby("player_id"):
        trace_rows.append({
            "player_id": int(player_id),
            "club_name": dominant(group, "club", "team_name"),
            "national_team_name": dominant(group, "national", "team_name"),
            "competition_id": dominant(group, None, "league_id"),
            "competition_name": dominant(group, None, "league_name"),
            "club_minutes": float(group.loc[group.domain.eq("club"), "minutes"].sum()),
            "national_minutes": float(group.loc[group.domain.eq("national"), "minutes"].sum()),
            "competition_count": int(group.league_id.nunique()),
        })
    trace = pd.DataFrame(trace_rows)
    aggregate = aggregate.merge(trace, on="player_id", how="left")

    gk_model = goalkeeper_model(matches, candidates, team_ratings)
    frame = candidates.merge(aggregate, on="player_id", how="left").merge(gk_model, on="player_id", how="left")
    frame["context_minutes"] = frame.context_minutes.fillna(0)
    frame["context_matches"] = frame.context_matches.fillna(0)
    frame["context_coverage"] = (frame.context_minutes / pd.to_numeric(frame.exact_window_total_minutes, errors="coerce").replace(0, np.nan)).clip(upper=1).fillna(0)
    frame["network_reliability"] = (
        0.50 * (frame.opponent_component_size.fillna(0).clip(upper=100) / 100.0)
        + 0.25 * (frame.context_matches.fillna(0).clip(upper=20) / 20.0)
        + 0.25 * (frame.bridge_match_count.fillna(0).clip(upper=5) / 5.0)
    ).clip(0, 1)
    frame["context_model"] = "results-based Elo; 70% opponent strength + 30% competition median strength"
    frame["context_gamma"] = 0.18

    for metric in ["overall_final", *DIMS, "uncertainty", "conservative_score_final"]:
        if metric in frame:
            frame[f"raw_{metric}"] = frame[metric]
    shift = 0.18 * frame.context_strength_z.fillna(0).clip(-3, 3) * frame.network_reliability.fillna(0)
    for metric in ["overall_final", "build_up", "progression", "creation", "finishing", "defending", "duels", "retention"]:
        frame[metric] = [logit_adjust(value, delta) for value, delta in zip(pd.to_numeric(frame[metric], errors="coerce"), shift, strict=True)]
    gk_mask = frame.final_role.eq("GK")
    frame.loc[gk_mask, "goalkeeping"] = frame.loc[gk_mask, "goalkeeping_v2"]
    frame.loc[~gk_mask, "goalkeeping"] = [logit_adjust(value, delta) for value, delta in zip(pd.to_numeric(frame.loc[~gk_mask, "goalkeeping"], errors="coerce"), shift.loc[~gk_mask], strict=True)]
    base_uncertainty = pd.to_numeric(frame.raw_uncertainty, errors="coerce").fillna(0.10)
    context_uncertainty = 0.06 * (1 - frame.context_coverage) + 0.04 * (1 - frame.network_reliability)
    gk_uncertainty = np.where(gk_mask, 0.05 * (1 - frame.goalkeeper_model_reliability.fillna(0)), 0.0)
    frame["uncertainty"] = np.sqrt(base_uncertainty**2 + context_uncertainty**2 + gk_uncertainty**2)
    frame["conservative_score_final"] = frame.overall_final - frame.uncertainty

    frame["external_context_complete"] = (
        frame.context_coverage.ge(0.90)
        & frame.context_matches.ge(5)
        & frame.opponent_strength_adjusted.notna()
        & frame.competition_strength.notna()
    )
    frame["goalkeeper_model_complete"] = (~gk_mask) | (
        frame.gk_minutes.fillna(0).ge(900)
        & frame.sot_faced.fillna(0).ge(30)
        & frame.goalkeeping_v2.notna()
    )
    frame["final_candidate_eligible_v2"] = frame.external_context_complete & frame.goalkeeper_model_complete
    frame["v2_exclusion_reason"] = ""
    frame.loc[frame.context_coverage.lt(0.90), "v2_exclusion_reason"] += "context_coverage_lt_0_90;"
    frame.loc[frame.context_matches.lt(5), "v2_exclusion_reason"] += "context_matches_lt_5;"
    frame.loc[gk_mask & frame.gk_minutes.fillna(0).lt(900), "v2_exclusion_reason"] += "gk_minutes_lt_900;"
    frame.loc[gk_mask & frame.sot_faced.fillna(0).lt(30), "v2_exclusion_reason"] += "gk_shots_on_target_faced_lt_30;"

    frame["adjusted_role_score_v2"] = np.nan
    frame["raw_role_score"] = np.nan
    for role in ROLES:
        mask = frame.final_role.eq(role)
        frame.loc[mask, "adjusted_role_score_v2"] = role_score(frame.loc[mask], role)
        raw = frame.loc[mask].copy()
        for metric in ["overall_final", *DIMS]:
            raw[metric] = pd.to_numeric(raw[f"raw_{metric}"], errors="coerce")
        frame.loc[mask, "raw_role_score"] = role_score(raw, role)
    frame = frame.sort_values(["final_role", "adjusted_role_score_v2", "player_id"], ascending=[True, False, True])
    frame.to_csv(PROFILES, index=False)

    top_rows = []
    for role in ROLES:
        pool = frame.loc[frame.final_role.eq(role) & frame.final_candidate_eligible_v2].copy()
        pool = pool.sort_values(["adjusted_role_score_v2", "player_id"], ascending=[False, True]).head(10)
        for rank, row in enumerate(pool.itertuples(index=False), start=1):
            top_rows.append({
                "role": role,
                "rank_v2": rank,
                "player_id": int(row.player_id),
                "player_name": row.player_name,
                "club_name": getattr(row, "club_name", ""),
                "national_team": getattr(row, "world_cup_team", ""),
                "dominant_competition": getattr(row, "competition_name", ""),
                "minutes": float(row.exact_window_total_minutes),
                "context_matches": int(row.context_matches),
                "context_coverage": float(row.context_coverage),
                "opponent_strength": float(row.opponent_strength_adjusted),
                "competition_strength": float(row.competition_strength),
                "context_strength_z": float(row.context_strength_z),
                "raw_role_score": float(row.raw_role_score),
                "adjusted_role_score_v2": float(row.adjusted_role_score_v2),
                "uncertainty_v2": float(row.uncertainty),
                "goalkeeping_v2": float(row.goalkeeping) if role == "GK" else "",
            })
    top_frame = pd.DataFrame(top_rows)
    top_frame.to_csv(TOP10, index=False)

    role_counts = frame.loc[frame.final_candidate_eligible_v2].groupby("final_role").player_id.nunique().reindex(ROLES, fill_value=0).astype(int).to_dict()
    gk_values = frame.loc[gk_mask & frame.final_candidate_eligible_v2, "goalkeeping"].dropna()
    winners = top_frame.loc[top_frame.rank_v2.eq(1)] if not top_frame.empty else pd.DataFrame()
    gk_pass = bool(len(gk_values) >= 20 and gk_values.nunique() >= 10 and (gk_values.std(ddof=0) if len(gk_values) else 0) >= 0.03)
    status = {
        "status": "strength_adjusted_profiles_v2_built",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_role_pairs": int(len(frame)),
        "candidate_role_pairs_v2_eligible": int(frame.final_candidate_eligible_v2.sum()),
        "eligible_candidates_by_role": role_counts,
        "minimum_20_each_role": all(role_counts[role] >= 20 for role in ROLES),
        "fixture_context_rows": int(len(context)),
        "candidate_match_context_rows": int(len(matches)),
        "candidate_context_coverage_median": float(frame.context_coverage.median()),
        "goalkeeper_model": {
            "method": "Bayesian save rate + Elo-adjusted concession residual + clean sheets + distribution + penalties",
            "eligible_goalkeepers": int(len(gk_values)),
            "unique_goalkeeping_values": int(gk_values.nunique()),
            "standard_deviation": float(gk_values.std(ddof=0)) if len(gk_values) else None,
            "passed": gk_pass,
            "limitations": "shots-on-target faced are proxied as saves plus goals conceded; event-level xG faced is unavailable",
        },
        "competition_context": {
            "method": "results-based Elo over club and national-team networks",
            "home_advantage_elo": {"club": 45, "national": 25},
            "opponent_weight": 0.70,
            "competition_weight": 0.30,
            "logit_adjustment_gamma": 0.18,
            "fields_present": ["club_name", "competition_id", "competition_name", "competition_strength", "opponent_strength_adjusted"],
        },
        "role_winners_v2": winners[["role", "player_id", "player_name", "club_name", "adjusted_role_score_v2"]].to_dict("records") if not winners.empty else [],
        "external_validity_profile_gate_passed": bool(all(role_counts[role] >= 20 for role in ROLES) and gk_pass),
        "next_action": "build and inspect one v2 Real XI and AI XI" if all(role_counts[role] >= 20 for role in ROLES) and gk_pass else "repair deficient role pools or context coverage",
        "outputs": {"profiles": str(PROFILES), "top10": str(TOP10)},
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
