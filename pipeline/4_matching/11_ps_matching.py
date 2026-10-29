"""File 11: propensity score matching, one study year at a time, in Python (no R needed).

The same method as Lifei's MatchIt call (matchit(hiv ~ birth_year + census_region +
patient_race_ethnicity, method = "nearest", exact = ~ patient_gender, ratio = 1,
replace = FALSE, distance = "glm", link = "linear.logit", caliper = 0.2)):

  1. Score. A logistic regression of HIV on birth year, census region and race, fitted on the
     year's ps_input (File 10: the HIV group plus 20 controls per case). The distance between
     two people is the difference in the linear predictor (the logit of the score).
  2. Exact on sex. Men are only matched with men, women with women.
  3. Nearest neighbour, 1:1, without replacement. People with HIV are taken from the highest
     score down; each gets the unused control with the closest logit, so a control is used at
     most once per year (it can be used again in another year).
  4. Caliper. A person with HIV whose closest unused control is more than caliper_sd standard
     deviations of the logit away (SD over everyone in that year) is left unmatched.
  5. Balance. The standardized mean difference of each matching variable, before and after
     matching, divided by the SD in the HIV group (MatchIt's default); under 0.1 is good.

Ties are broken by patient_id order, so the same data always gives the same pairs. Individual
pairs can differ from an R run where scores tie, but the method and the balance are the same.
Writes ${work_schema}.ps_matched${sfx} and results/<profile>/4_matching/balance_smd.csv.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import redshift_connector

from runner import config, db, results, sql

log = logging.getLogger(__name__)

CONTINUOUS = ("birth_year",)
CATEGORICAL = ("census_region", "patient_race_ethnicity")
INSERT_ROWS = 5000


def fit_logit(X: np.ndarray, y: np.ndarray, max_iter: int = 25, tol: float = 1e-8) -> np.ndarray:
    """Maximum-likelihood logistic regression by Newton-Raphson (what R's glm does; 25 steps is
    glm's default limit). X includes the intercept column."""
    beta = np.zeros(X.shape[1])
    for _ in range(max_iter):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ beta, -30, 30)))
        w = np.clip(p * (1 - p), 1e-10, None)
        step = np.linalg.solve((X * w[:, None]).T @ X + 1e-9 * np.eye(X.shape[1]), X.T @ (y - p))
        beta += step
        if np.max(np.abs(step)) < tol:
            break
    return beta


def covariates(df: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """The model matrix (intercept, standardized birth year, one column per category except the
    first of each variable) and, for the balance table, every variable and category as a column."""
    shown = pd.DataFrame({c: df[c].astype(float) for c in CONTINUOUS}, index=df.index)
    for column in CATEGORICAL:
        levels = sorted(df[column].astype(str).unique())
        for level in levels:
            shown[f"{column}: {level}"] = (df[column].astype(str) == level).astype(float)
    model = [np.ones(len(df))]
    for c in CONTINUOUS:
        values = shown[c].to_numpy()
        model.append((values - values.mean()) / (values.std() or 1.0))
    for column in CATEGORICAL:
        levels = sorted(df[column].astype(str).unique())
        model += [shown[f"{column}: {level}"].to_numpy() for level in levels[1:]]
    return np.column_stack(model), shown


class _Free:
    """Positions 0..n-1 of the controls, sorted by logit; finds the nearest unused one on either
    side in near-constant time (union-find with path compression)."""

    def __init__(self, n: int) -> None:
        self.right = list(range(n + 1))   # right[i]: smallest free position >= i (n = none)
        self.left = list(range(n + 1))    # left[i + 1]: largest free position <= i, plus 1 (0 = none)

    @staticmethod
    def _root(parent: list[int], i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    def at_or_after(self, i: int) -> int:
        return self._root(self.right, i)

    def at_or_before(self, i: int) -> int:
        return self._root(self.left, i + 1) - 1

    def take(self, i: int) -> None:
        self.right[i] = i + 1
        self.left[i + 1] = i


def match_year(df: pd.DataFrame, caliper_sd: float) -> tuple[list[tuple[int, int]], np.ndarray, pd.DataFrame]:
    """One year's matching. df: that year's ps_input, sorted by patient_id. Returns the matched
    (HIV row, control row) pairs in matching order, the logit of every row, and the balance
    variables."""
    X, shown = covariates(df)
    y = df["hiv"].to_numpy().astype(float)
    logit = X @ fit_logit(X, y)
    caliper = caliper_sd * logit.std(ddof=1)
    pairs: list[tuple[int, int]] = []
    for rows in df.groupby("patient_gender", sort=True).indices.values():
        treated = rows[y[rows] == 1]
        controls = rows[y[rows] == 0]
        if len(treated) == 0 or len(controls) == 0:
            continue
        controls = controls[np.argsort(logit[controls], kind="stable")]
        control_logit = logit[controls]
        free = _Free(len(controls))
        for t in treated[np.argsort(-logit[treated], kind="stable")]:
            spot = int(np.searchsorted(control_logit, logit[t]))
            options = [i for i in (free.at_or_before(spot - 1), free.at_or_after(spot))
                       if 0 <= i < len(controls)]
            if not options:
                break
            best = min(options, key=lambda i: (abs(control_logit[i] - logit[t]), controls[i]))
            if abs(control_logit[best] - logit[t]) > caliper:
                continue
            free.take(best)
            pairs.append((int(t), int(controls[best])))
    return pairs, logit, shown


def _smd(values: np.ndarray, treated: np.ndarray, control: np.ndarray, sd: float) -> float:
    if not treated.any() or not control.any() or not sd:
        return float("nan")
    return round(float((values[treated].mean() - values[control].mean()) / sd), 3)


def balance_table(shown: pd.DataFrame, logit: np.ndarray, hiv: np.ndarray,
                  pairs: list[tuple[int, int]], year: int) -> pd.DataFrame:
    """Standardized mean differences before and after matching, over the SD in the HIV group."""
    table = shown.copy()
    table.insert(0, "distance", logit)
    matched = np.zeros(len(table), dtype=bool)
    for t, c in pairs:
        matched[t] = matched[c] = True
    treated, control = hiv == 1, hiv == 0
    out = []
    for column in table.columns:
        values = table[column].to_numpy()
        binary = column not in ("distance",) + CONTINUOUS
        p = values[treated].mean()
        sd = float(np.sqrt(p * (1 - p)) if binary else values[treated].std(ddof=1))
        out.append({"analysis_year": year, "variable": column,
                    "smd_before": _smd(values, treated, control, sd),
                    "smd_after": _smd(values, treated & matched, control & matched, sd)})
    return pd.DataFrame(out)


def run(conn: redshift_connector.Connection, cfg: config.Config, variables: dict[str, str],
        results_dir: Path) -> None:
    if cfg.match_ratio != 1:
        raise config.ConfigError("Only 1:1 matching is built (agreed with the PI): set matching.ratio: 1.")
    ps_input = sql.render("${work_schema}.ps_input${sfx}", variables, "11_ps_matching.py")
    ps_matched = sql.render("${work_schema}.ps_matched${sfx}", variables, "11_ps_matching.py")
    db.execute(conn, f"DROP TABLE IF EXISTS {ps_matched}", "11 drop")
    db.execute(conn, f"CREATE TABLE {ps_matched} (analysis_year INT, index_date DATE, pair_id VARCHAR(50), "
                     "patient_id VARCHAR(100), hiv INT, match_weight FLOAT8) "
                     "DISTKEY(patient_id) SORTKEY(patient_id, analysis_year)", "11 create")
    years = db.query(conn, f"SELECT DISTINCT analysis_year FROM {ps_input} ORDER BY 1", "11 years")
    balance = []
    for year in (int(y) for y in years["analysis_year"]):
        df = db.query(conn, f"SELECT patient_id, birth_year, patient_gender, census_region, "
                            f"patient_race_ethnicity, hiv FROM {ps_input} WHERE analysis_year = {year} "
                            "ORDER BY patient_id", f"11 read {year}").reset_index(drop=True)
        df["hiv"] = df["hiv"].astype(int)
        pairs, logit, shown = match_year(df, cfg.caliper_sd)
        rows = []
        for number, (t, c) in enumerate(pairs, start=1):
            for i in (t, c):   # one HIV person and their control share pair_id = <year>-<number>
                rows.append(f"({year}, '{year}-12-31', '{year}-{number}', "
                            f"{config.sql_quote(str(df.at[i, 'patient_id']))}, {int(df.at[i, 'hiv'])}, 1.0)")
        for start in range(0, len(rows), INSERT_ROWS):
            db.execute(conn, f"INSERT INTO {ps_matched} VALUES " + ",".join(rows[start:start + INSERT_ROWS]),
                       f"11 insert {year}")
        year_balance = balance_table(shown, logit, df["hiv"].to_numpy(), pairs, year)
        balance.append(year_balance)
        log.info("%d: %d of %d people with HIV matched; worst |SMD| after matching %.3f",
                 year, len(pairs), int(df["hiv"].sum()), year_balance["smd_after"].abs().max())
    results.save(pd.concat(balance, ignore_index=True), results_dir / "balance_smd.csv")