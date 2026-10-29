"""
Gagne step 2: turn the evidence into scores, one row per matched person-year.

Run:  python gagne_2_scores.py      (after gagne_1_evidence.py)

Builds, in the work schema:
  gagne_scores   one row per matched person-year with:
                   patient_id, analysis_year, pair_id, hiv, index_date
                   gagne_group_01_... to gagne_group_20_...   (0/1 flags)
                   gagne_group_count     number of groups present
                   gagne_score           Nemo's weighted sum (all 20 groups)
                   gagne_score_excl_hiv  same, without group 19 (HIV/AIDS)

Rules (same as Nemo's script 5):
  * each group counts at most once per person-year
  * score = sum of the weights of the groups present
  * person-years with no Gagne codes are KEPT, with all zeros and score 0

Why two scores: group 19 (HIV/AIDS, code B20) has weight -1. Controls can
never have it (anyone with HIV evidence was excluded from the control pool),
so the original score builds the exposure into the comparison.
gagne_score_excl_hiv leaves group 19 out; the flag itself is still kept.
"""

from gagne_config import SETTINGS, table, connect, run_sql, query_df, show, load_gagne_rules


def build_scores_sql(groups):
    hiv_group = SETTINGS["hiv_group"]

    # One MAX(CASE ...) line per group: 1 if the person-year has that group
    flag_lines = ",\n".join(
        f"        MAX(CASE WHEN ev.gagne_group = {g.gagne_group} THEN 1 ELSE 0 END) AS {g.flag_column}"
        for g in groups.itertuples())

    flag_select = ", ".join(f"f.{c}" for c in groups["flag_column"])
    count_expr = " + ".join(groups["flag_column"])
    score_expr = " + ".join(f"({g.weight}) * {g.flag_column}" for g in groups.itertuples())
    score_excl_expr = " + ".join(f"({g.weight}) * {g.flag_column}"
                                 for g in groups.itertuples() if g.gagne_group != hiv_group)

    return f"""
CREATE TABLE {table("scores")}
DISTKEY(patient_id) SORTKEY(patient_id, analysis_year) AS
WITH flags AS (
    SELECT
        py.patient_id, py.analysis_year, py.pair_id, py.hiv, py.index_date,
{flag_lines}
    FROM {table("person_years")} py
    LEFT JOIN {table("evidence")} ev            -- LEFT JOIN keeps person-years with no Gagne codes
      ON ev.patient_id = py.patient_id
     AND ev.analysis_year = py.analysis_year
    GROUP BY py.patient_id, py.analysis_year, py.pair_id, py.hiv, py.index_date
)
SELECT f.patient_id, f.analysis_year, f.pair_id, f.hiv, f.index_date,
       {flag_select},
       {count_expr} AS gagne_group_count,
       {score_expr} AS gagne_score,
       {score_excl_expr} AS gagne_score_excl_hiv
FROM flags f;"""


def main():
    rules, groups = load_gagne_rules()
    hiv_flag = groups.loc[groups.gagne_group == SETTINGS["hiv_group"], "flag_column"].iloc[0]
    hiv_weight = int(groups.loc[groups.gagne_group == SETTINGS["hiv_group"], "weight"].iloc[0])

    conn = connect()
    try:
        run_sql(conn, f"DROP TABLE IF EXISTS {table('scores')};")
        run_sql(conn, build_scores_sql(groups), "Gagne scores")

        # --- Check 1: exactly one row per matched person-year, none lost ---
        qa = query_df(conn, f"""
            SELECT (SELECT COUNT(*) FROM {table('person_years')}) AS person_years_in,
                   COUNT(*) AS rows_out,
                   COUNT(DISTINCT patient_id || '-' || analysis_year) AS distinct_out
            FROM {table('scores')}""")
        print(qa.to_string(index=False))
        if not (qa.person_years_in[0] == qa.rows_out[0] == qa.distinct_out[0]):
            raise RuntimeError("gagne_scores does not have exactly one row per matched person-year.")

        # --- Check 2: the two scores differ only by the HIV/AIDS group ---
        bad = query_df(conn, f"""
            SELECT COUNT(*) AS n_bad FROM {table('scores')}
            WHERE gagne_score_excl_hiv <> gagne_score - ({hiv_weight}) * {hiv_flag}""").n_bad[0]
        print(f"Rows where the two scores disagree beyond the HIV group: {bad} (should be 0)")
        if bad != 0:
            raise RuntimeError("Score check failed.")

        # --- Summaries ---
        show(conn, "Score range (possible: -2 to 26):", f"""
            SELECT MIN(gagne_score) AS min_score, MAX(gagne_score) AS max_score,
                   MIN(gagne_score_excl_hiv) AS min_excl_hiv, MAX(gagne_score_excl_hiv) AS max_excl_hiv
            FROM {table('scores')}""")

        show(conn, "Mean scores by year and HIV status:", f"""
            SELECT analysis_year, hiv, COUNT(*) AS person_years,
                   ROUND(AVG(gagne_score::FLOAT), 2)          AS mean_score,
                   ROUND(AVG(gagne_score_excl_hiv::FLOAT), 2) AS mean_score_excl_hiv,
                   ROUND(AVG(gagne_group_count::FLOAT), 2)    AS mean_groups,
                   ROUND(100.0 * SUM(CASE WHEN gagne_group_count = 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                              AS pct_no_groups
            FROM {table('scores')}
            GROUP BY 1, 2 ORDER BY 1, 2""")

        prevalence = ",\n".join(
            f"ROUND(100.0 * AVG({c}::FLOAT), 1) AS g{n:02d}"
            for n, c in zip(groups.gagne_group, groups.flag_column))
        show(conn, "Percent of person-years with each group, by HIV status (g01 ... g20):", f"""
            SELECT hiv, {prevalence}
            FROM {table('scores')}
            GROUP BY 1 ORDER BY 1""")
        print("\nGroup numbers:")
        print(groups[["gagne_group", "group_name", "weight"]].to_string(index=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()