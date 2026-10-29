"""
Gagne combined comorbidity score: settings and shared helpers.

Project: SHARP / OHDSI-3 multimorbidity cohort (HIV+ vs matched HIV-)
Author:  Rhea

What this file does
-------------------
Holds everything the two pipeline scripts share:
  * SETTINGS and TABLES: study years, schema names, output table names
  * connect():           opens a Redshift connection (password typed at runtime)
  * run_sql/query_df:    send SQL to Redshift, with timing
  * load_gagne_rules():  reads Nemo's lookup CSVs (ICD-10-CM rules + weights)
  * candidate_prefixes(): the short code prefixes used as a cheap filter in the
                          diagnosis scan (same idea as Nemo's script 3)

It does not create any tables by itself.

Logic follows Nemo Zhou's shareable_clinical_metrics R scripts 2, 3 and 5
(Gagne parts only), generalised from 2022 to any list of study years and
pointed at the matched cohort (ps_matched) instead of his eligibility table.

Settings come from config/study.yml and config/local.yml: `python -m runner`
passes them to these scripts as environment variables (SHARP_*, REDSHIFT_*).
"""

import getpass
import os
import time
from pathlib import Path

import pandas as pd


# =============================================================================
# Settings
# =============================================================================

def _env(name: str) -> "str | None":
    return os.environ.get(name) or None


SETTINGS = {
    # Years to score. Each person-year uses diagnoses from Jan 1 - Dec 31 of
    # that year (1-year look-back to the Dec 31 index date).
    "study_years": list(range(int(os.environ.get("SHARP_FIRST_YEAR", "2016")),
                              int(os.environ.get("SHARP_LAST_YEAR", "2025")) + 1)),

    "work_schema": _env("SHARP_WORK_SCHEMA"),
    # Every work-schema table name ends in the profile's suffix (_s1, _s30, or none for full),
    # so the three profiles can run at the same time.
    "table_suffix": os.environ.get("SHARP_TABLE_SUFFIX", ""),
    # The profile's people, applied inside the diagnosis scan: the MD5 test that picks the 1% or
    # 30% sample (all matched people are in it), or TRUE for everyone. Set by the runner.
    "sample_filter": os.environ.get("SHARP_SAMPLE_FILTER") or "TRUE",
    "komodo_schema": _env("SHARP_KOMODO_SCHEMA"),
    "matched_table": "ps_matched",          # File 11 output: one row per matched person-year
    "dx_table": "normalized_dx_events",

    # Nemo's lookup CSVs, in the repository's reference/ folder
    "lookup_dir": Path(__file__).resolve().parents[2] / "reference",
    "diagnosis_lookup_file": "gagne_diagnosis_lookup.csv",
    "weight_lookup_file": "gagne_weight_lookup.csv",

    # Longest prefix used in the scan filter (Nemo's diagnosis_candidate_prefix_length)
    "max_prefix_length": 3,

    # Gagne group number for HIV/AIDS (B20, weight -1). Left out of gagne_score_excl_hiv.
    "hiv_group": 19,

    "redshift_host": _env("REDSHIFT_HOST"),
    "redshift_port": int(os.environ.get("REDSHIFT_PORT", "5439")),
    "redshift_database": _env("REDSHIFT_DATABASE"),
    "redshift_user": _env("REDSHIFT_USER"),
}

DB_SETTINGS = ("work_schema", "komodo_schema", "redshift_host", "redshift_database", "redshift_user")

# Output tables (all created in work_schema)
TABLES = {
    "person_years": "gagne_person_years",    # matched person-years to score
    "rules":        "gagne_rules",           # Nemo's ICD-10-CM rules
    "candidates":   "gagne_dx_candidates",   # distinct (patient, year, dx_code) that passed the filter
    "code_map":     "gagne_code_map",        # distinct dx_code -> Gagne group
    "evidence":     "gagne_group_evidence",  # distinct (patient, year, group)
    "scores":       "gagne_scores",          # FINAL: one row per matched person-year
}


def table(key):
    """Full table name in the work schema, e.g. table("scores") -> work_you.gagne_scores_s1"""
    return f'{SETTINGS["work_schema"]}.{TABLES[key]}{SETTINGS["table_suffix"]}'


def komodo(name):
    """Full Komodo table name, e.g. komodo("dx_table")."""
    return f'{SETTINGS["komodo_schema"]}.{SETTINGS[name]}'


# =============================================================================
# Connection and SQL helpers
# =============================================================================

def connect():
    """Open a Redshift connection. The password comes from REDSHIFT_PASSWORD (set by the
    runner) or is typed at runtime, and is never saved."""
    import redshift_connector  # imported here so the rule functions can be tested without it

    missing = [key for key in DB_SETTINGS if not SETTINGS[key]]
    if missing:
        raise RuntimeError(f"Settings not set: {missing}. Run the Gagne steps with `python -m runner`.")
    conn = redshift_connector.connect(
        host=SETTINGS["redshift_host"],
        port=SETTINGS["redshift_port"],
        database=SETTINGS["redshift_database"],
        user=SETTINGS["redshift_user"],
        password=os.environ.get("REDSHIFT_PASSWORD") or getpass.getpass("Redshift password: "),
    )
    conn.autocommit = True   # each CREATE TABLE is saved immediately (same as DBeaver's default)
    return conn


def run_sql(conn, sql, label=None):
    """Run one SQL statement (no results), printing how long it took."""
    started = time.time()
    if label:
        print(f"[{time.strftime('%H:%M:%S')}] START {label}", flush=True)
    cursor = conn.cursor()
    cursor.execute(sql)
    cursor.close()
    if label:
        minutes = (time.time() - started) / 60
        print(f"[{time.strftime('%H:%M:%S')}] DONE  {label} ({minutes:.1f} min)", flush=True)


def query_df(conn, sql):
    """Run a SELECT and return the result as a pandas table. Use for small QA results only."""
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    cursor.close()
    return pd.DataFrame(rows, columns=columns)


def show(conn, label, sql):
    """Run a QA query and print it with a label."""
    print(f"\n{label}")
    print(query_df(conn, sql).to_string(index=False))


def sql_str(value):
    """Wrap a value in single quotes for SQL; None/NaN becomes NULL."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


# =============================================================================
# Gagne rules (Nemo's lookups)
# =============================================================================

def load_gagne_rules():
    """
    Read Nemo's Gagne lookups and return (rules, groups).

    rules:  one row per ICD-10-CM rule, with columns
            gagne_group, match_type (exact/prefix/range), match_value,
            range_start, range_end, range_end_inclusive
    groups: one row per Gagne group (20), with gagne_group, group_name, weight,
            and the output column name for its 0/1 flag

    Only ICD-10-CM rules are kept: the study starts in 2016, after the US
    switched from ICD-9 (Oct 2015).

    Note on ranges: Nemo's lookup writes exclusive range ends with a trailing
    "[" (e.g. C77 to "C80["). Comparing dx_code < 'C80[' as text keeps every
    code starting with C80 (digits and capital letters sort before "["), so
    the range covers C77 through C80*. We keep the values exactly as supplied
    so our results match his.
    """
    folder = SETTINGS["lookup_dir"]
    dx = pd.read_csv(folder / SETTINGS["diagnosis_lookup_file"], dtype=str, keep_default_na=False)
    wt = pd.read_csv(folder / SETTINGS["weight_lookup_file"], dtype=str, keep_default_na=False)

    # "NA" in the CSV means missing
    dx = dx.replace({"NA": None, "": None})

    rules = dx[(dx["metric"] == "GAGNE") & (dx["code_system"] == "ICD10CM")].copy()
    rules["gagne_group"] = rules["gagne_group"].astype(int)
    rules["match_type"] = rules["match_type"].str.lower()
    rules = rules[["gagne_group", "match_type", "match_value",
                   "range_start", "range_end", "range_end_inclusive"]].reset_index(drop=True)

    groups = wt[wt["metric"] == "GAGNE"].copy()
    groups["gagne_group"] = groups["gagne_group"].astype(int)
    groups["weight"] = groups["weight"].astype(int)
    groups["group_name"] = groups["gagne_group_desc"].str.lower()
    # Same naming as Nemo's output, e.g. gagne_group_02_congestive_heart_failure
    groups["flag_column"] = groups.apply(
        lambda g: f"gagne_group_{g.gagne_group:02d}_{g.group_name}", axis=1)
    groups = groups.sort_values("gagne_group")[
        ["gagne_group", "group_name", "weight", "flag_column"]].reset_index(drop=True)

    # --- Checks: fail early if the lookups aren't what we expect ---
    if len(groups) != 20 or sorted(groups["gagne_group"]) != list(range(1, 21)):
        raise ValueError("Weight lookup must have exactly Gagne groups 1-20.")
    if not set(rules["match_type"]) <= {"exact", "prefix", "range"}:
        raise ValueError("Unexpected match_type in the diagnosis lookup.")
    if set(rules["gagne_group"]) != set(groups["gagne_group"]):
        raise ValueError("Every Gagne group must have at least one ICD-10-CM rule.")
    hiv = groups[groups["gagne_group"] == SETTINGS["hiv_group"]]
    if hiv.empty or hiv["group_name"].iloc[0] != "hiv_aids":
        raise ValueError("hiv_group setting does not point at the HIV/AIDS group.")

    return rules, groups


def _range_prefixes(start, end, max_len):
    """
    Short prefix(es) guaranteed to cover every code in a range (port of Nemo's
    candidate_prefixes_for_range). Uses the characters the two ends share:
      N032-N037  -> "N03"
      C77-C80[   -> "C"   (they only share the first letter)
    If even the first letter differs, every letter in between is returned.
    """
    shared = 0
    for a, b in zip(start, end):
        if a != b:
            break
        shared += 1
    if shared == 0:
        leads = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [str(d) for d in range(10)]
        return leads[leads.index(start[0]): leads.index(end[0]) + 1]
    return [start[: min(max_len, shared)]]


def candidate_prefixes(rules):
    """
    The set of short prefixes used to pre-filter the diagnosis scan.
    Exact/prefix rules contribute their first (up to) 3 characters; ranges
    contribute the shared prefix of their two ends. This is only a coarse
    filter: the exact rules are applied later, on distinct codes.
    Returns {prefix_length: sorted list of prefixes}.
    """
    max_len = SETTINGS["max_prefix_length"]
    prefixes = set()
    for r in rules.itertuples():
        if r.match_type in ("exact", "prefix"):
            prefixes.add(r.match_value[:max_len])
        else:
            prefixes.update(_range_prefixes(r.range_start, r.range_end, max_len))
    by_length = {}
    for p in prefixes:
        by_length.setdefault(len(p), set()).add(p)
    return {n: sorted(ps) for n, ps in sorted(by_length.items())}


def prefix_filter_sql(prefixes, column="dx_code"):
    """Literal SQL filter, e.g. (LEFT(dx_code, 1) IN ('C') OR LEFT(dx_code, 3) IN ('B20', ...)).
    Literal values (not a join) give Redshift the best chance to filter inside the scan."""
    parts = [f"LEFT({column}, {n}) IN ({', '.join(sql_str(p) for p in ps)})"
             for n, ps in prefixes.items()]
    return "(" + "\n       OR ".join(parts) + ")"


if __name__ == "__main__":
    # Quick local check (no database needed): python gagne_config.py
    rules, groups = load_gagne_rules()
    print(f"{len(rules)} ICD-10-CM rules across {rules['gagne_group'].nunique()} groups")
    print(rules["match_type"].value_counts().to_string())
    print()
    print(groups.to_string(index=False))
    print()
    for n, ps in candidate_prefixes(rules).items():
        print(f"{len(ps)} prefixes of length {n}: {ps[:15]}{' ...' if len(ps) > 15 else ''}")