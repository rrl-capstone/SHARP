"""
Gagne step 3: descriptive plots of the matched cohort's comorbidity.

Run:  python gagne_3_plots.py      (after gagne_2_scores.py)
Needs: pip install matplotlib

Saves PNG files in results/<run>/5_gagne/plots/ (SHARP_GAGNE_PLOTS_DIR; a "plots"
folder next to this script when run on its own):
  1_score_over_time.png       mean Gagne score per year, HIV vs controls
  2_condition_prevalence.png  % with each of the 20 Gagne groups, HIV vs controls
  3_score_distribution.png    how scores are spread out in each group
  4_pair_differences.png      HIV score minus matched control's score, per pair
  5_prevalence_gap_heatmap.png  difference in % with each group, by year
  6_comorbidity_age_gap.png   mean score by age, and how many years "older" the
                              HIV group looks in comorbidity terms (interpolated)

Privacy: every query below returns AGGREGATES only (means, percents, counts),
computed inside Redshift. No patient-level rows are pulled into Python.

These are DESCRIPTIVE results: no confidence intervals and no adjustment for
repeated years per person.
"""

import os
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")            # draw straight to files, no window needed
import matplotlib.pyplot as plt
import pandas as pd

from gagne_config import SETTINGS, table, query_df, load_gagne_rules

# Colour-blind-friendly colours (Okabe-Ito palette), used in every plot
HIV_COLOUR = "#D55E00"
CONTROL_COLOUR = "#0072B2"
LABELS = {1: "People with HIV", 0: "Matched controls"}
SCORE = "gagne_score_excl_hiv"   # the fair comparison: HIV/AIDS group left out
NOTE = "Descriptive, unadjusted for repeated years per person."

OUT_DIR = Path(os.environ.get("SHARP_GAGNE_PLOTS_DIR") or Path(__file__).resolve().parent / "plots")
MATCH_RATIO = int(os.environ.get("SHARP_MATCH_RATIO", "1"))   # plot 4 compares 1:1 pairs only

MIN_CELL = 11      # hide any age/group cell with fewer than 11 person-years (small-cell rule)
AGE_CAP = 85       # Komodo appears to cap ages near 85, so 85+ is one group


def pretty(group_name):
    """congestive_heart_failure -> Congestive heart failure"""
    return group_name.replace("_", " ").capitalize()


def finish(fig, filename):
    fig.text(0.01, 0.005, NOTE, fontsize=8, color="grey", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / filename
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Saved {path}")


# =============================================================================
# Queries (aggregates only)
# =============================================================================

def fetch_scores_by_year(conn):
    return query_df(conn, f"""
        SELECT analysis_year, hiv, COUNT(*) AS person_years,
               AVG(gagne_score::FLOAT)          AS mean_score,
               AVG(gagne_score_excl_hiv::FLOAT) AS mean_score_excl_hiv
        FROM {table('scores')}
        GROUP BY 1, 2 ORDER BY 1, 2""")


def fetch_prevalence(conn, groups, by_year=False):
    """Percent of person-years with each group, by HIV status (and year)."""
    keys = "analysis_year, hiv" if by_year else "hiv"
    cols = ",\n".join(f"100.0 * AVG({c}::FLOAT) AS g{n}"
                      for n, c in zip(groups.gagne_group, groups.flag_column))
    wide = query_df(conn, f"SELECT {keys}, {cols} FROM {table('scores')} GROUP BY {keys}")
    long = wide.melt(id_vars=keys.split(", "), var_name="g", value_name="pct")
    long["gagne_group"] = long["g"].str[1:].astype(int)
    return long.drop(columns="g").merge(groups[["gagne_group", "group_name"]], on="gagne_group")


def fetch_score_distribution(conn):
    return query_df(conn, f"""
        SELECT hiv, {SCORE} AS score, COUNT(*) AS person_years
        FROM {table('scores')}
        GROUP BY 1, 2 ORDER BY 1, 2""")


def fetch_pair_differences(conn):
    """For every matched pair: HIV person's score minus their control's score.
    Returns how many pairs have each difference (not the pairs themselves)."""
    return query_df(conn, f"""
        SELECT diff, COUNT(*) AS pairs
        FROM (SELECT pair_id,
                     SUM(CASE WHEN hiv = 1 THEN {SCORE} ELSE -{SCORE} END) AS diff
              FROM {table('scores')}
              GROUP BY pair_id) p
        GROUP BY diff ORDER BY diff""")


def fetch_scores_by_age(conn):
    """Mean score at each age (50..85+), by HIV status. Age comes from Faye's
    eligible_person_years (age = year minus birth year, as of Dec 31)."""
    return query_df(conn, f"""
        SELECT LEAST(e.age, {AGE_CAP}) AS age, s.hiv,
               COUNT(*) AS person_years,
               AVG(s.{SCORE}::FLOAT) AS mean_score
        FROM {table('scores')} s
        JOIN {SETTINGS['work_schema']}.eligible_person_years{SETTINGS['table_suffix']} e
          ON e.patient_id = s.patient_id
         AND e.analysis_year = s.analysis_year
        GROUP BY 1, 2
        HAVING COUNT(*) >= {MIN_CELL}
        ORDER BY 1, 2""")


# =============================================================================
# Plots (each takes a small summary table)
# =============================================================================

def plot_score_over_time(df):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for hiv, colour in [(1, HIV_COLOUR), (0, CONTROL_COLOUR)]:
        d = df[df.hiv == hiv].sort_values("analysis_year")
        ax.plot(d.analysis_year, d.mean_score_excl_hiv, marker="o", lw=2.2, color=colour,
                label=f"{LABELS[hiv]} (HIV/AIDS group excluded)")
        if hiv == 1:  # original score only differs for the HIV group
            ax.plot(d.analysis_year, d.mean_score, ls="--", lw=1.4, color=colour, alpha=0.7,
                    label=f"{LABELS[hiv]} (original score)")
    ax.axvline(2022, color="grey", ls=":", lw=1)
    ax.text(2022.1, ax.get_ylim()[1] * 0.97, "Paxlovid widely\navailable", fontsize=8,
            color="grey", va="top")
    ax.set_xticks(sorted(df.analysis_year.unique()))
    ax.set_xlabel("Year")
    ax.set_ylabel("Mean Gagne comorbidity score")
    ax.set_title("Comorbidity burden over time: people with HIV vs matched controls")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(frameon=False, fontsize=9)
    finish(fig, "1_score_over_time.png")


def plot_condition_prevalence(df):
    wide = df.pivot_table(index="group_name", columns="hiv", values="pct")
    wide = wide.drop(index="hiv_aids", errors="ignore")      # 0% in controls by design
    wide["gap"] = wide[1] - wide[0]
    wide = wide.sort_values("gap")
    y = range(len(wide))

    fig, ax = plt.subplots(figsize=(9, 7.5))
    ax.hlines(y, wide[0], wide[1], color="lightgrey", lw=2)
    ax.scatter(wide[0], y, color=CONTROL_COLOUR, s=45, label=LABELS[0], zorder=3)
    ax.scatter(wide[1], y, color=HIV_COLOUR, s=45, label=LABELS[1], zorder=3)
    ax.set_yticks(list(y))
    ax.set_yticklabels([pretty(g) for g in wide.index])
    ax.set_xlabel("% of person-years with the condition (2016-2025)")
    ax.set_title("Which conditions differ? (sorted by gap; HIV/AIDS group not shown)")
    ax.grid(axis="x", alpha=0.3)
    ax.legend(frameon=False, loc="lower right")
    finish(fig, "2_condition_prevalence.png")


def plot_score_distribution(df):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    width = 0.4
    for hiv, colour, shift in [(0, CONTROL_COLOUR, -width / 2), (1, HIV_COLOUR, width / 2)]:
        d = df[df.hiv == hiv].copy()
        d["pct"] = 100 * d.person_years / d.person_years.sum()
        ax.bar(d.score + shift, d.pct, width=width, color=colour, label=LABELS[hiv])
    ax.set_xlabel("Gagne score (HIV/AIDS group excluded)")
    ax.set_ylabel("% of person-years")
    ax.set_title("How scores are spread out")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(frameon=False)
    finish(fig, "3_score_distribution.png")


def plot_pair_differences(df):
    total = df.pairs.sum()
    df = df.assign(pct=100 * df.pairs / total)
    colours = [HIV_COLOUR if d > 0 else CONTROL_COLOUR if d < 0 else "grey" for d in df["diff"]]
    higher = 100 * df.loc[df["diff"] > 0, "pairs"].sum() / total
    lower = 100 * df.loc[df["diff"] < 0, "pairs"].sum() / total
    mean_diff = (df["diff"] * df.pairs).sum() / total

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar(df["diff"], df.pct, color=colours, width=0.8)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("HIV person's score minus their matched control's score")
    ax.set_ylabel("% of matched pairs")
    ax.set_title(f"Within-pair differences: HIV person higher in {higher:.0f}% of pairs, "
                 f"lower in {lower:.0f}% (mean difference {mean_diff:+.2f})", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    finish(fig, "4_pair_differences.png")


def plot_prevalence_gap_heatmap(df):
    wide = df.pivot_table(index=["group_name", "analysis_year"], columns="hiv", values="pct")
    gap = (wide[1] - wide[0]).unstack("analysis_year")
    gap = gap.drop(index="hiv_aids", errors="ignore")
    gap = gap.loc[gap.mean(axis=1).sort_values(ascending=False).index]

    limit = max(abs(gap.values.min()), abs(gap.values.max()))
    fig, ax = plt.subplots(figsize=(10, 7.5))
    im = ax.imshow(gap.values, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto")
    ax.set_xticks(range(gap.shape[1]))
    ax.set_xticklabels(gap.columns)
    ax.set_yticks(range(gap.shape[0]))
    ax.set_yticklabels([pretty(g) for g in gap.index])
    for i in range(gap.shape[0]):
        for j in range(gap.shape[1]):
            ax.text(j, i, f"{gap.values[i, j]:.0f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, label="Percentage-point gap (HIV minus controls)")
    ax.set_title("Prevalence gap by condition and year (red = more common with HIV)")
    finish(fig, "5_prevalence_gap_heatmap.png")


def equivalent_control_age(df):
    """For each age, find the age at which the AVERAGE CONTROL reaches the HIV
    group's mean score, by linear interpolation along the controls' curve.
    Returns a table of age, HIV score, equivalent control age, and the gap."""
    hiv = df[df.hiv == 1].set_index("age").mean_score
    ctl = df[df.hiv == 0].set_index("age").mean_score
    ages = sorted(set(hiv.index) & set(ctl.index))
    hiv, ctl = hiv.loc[ages], ctl.loc[ages]

    # np.interp needs an increasing curve; take the running maximum so small
    # dips in the controls' curve don't break the lookup
    ctl_monotone = np.maximum.accumulate(ctl.values)
    equivalent = np.interp(hiv.values, ctl_monotone, ages, left=np.nan, right=np.nan)
    out = pd.DataFrame({"age": ages, "hiv_score": hiv.values, "equivalent_control_age": equivalent})
    out["age_gap"] = out.equivalent_control_age - out.age
    # The top age (85+) is a capped group, so its interpolated age isn't meaningful
    out.loc[out.equivalent_control_age >= AGE_CAP, ["equivalent_control_age", "age_gap"]] = np.nan
    return out


def plot_comorbidity_age_gap(df):
    eq = equivalent_control_age(df)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    for hiv, colour in [(1, HIV_COLOUR), (0, CONTROL_COLOUR)]:
        d = df[df.hiv == hiv]
        ax1.plot(d.age, d.mean_score, marker="o", ms=3, lw=2, color=colour, label=LABELS[hiv])
    # Show one worked example: age 55
    ex = eq[(eq.age == 55) & eq.equivalent_control_age.notna()]
    if not ex.empty:
        a, sc, eqa = ex.age.iloc[0], ex.hiv_score.iloc[0], ex.equivalent_control_age.iloc[0]
        ax1.annotate("", xy=(eqa, sc), xytext=(a, sc),
                     arrowprops=dict(arrowstyle="->", color="black", lw=1.2))
        ax1.text((a + eqa) / 2, sc + 0.08, f"age {a:.0f} with HIV = age {eqa:.0f} control",
                 ha="center", fontsize=9)
    ax1.set_xlabel(f"Age (years; {AGE_CAP} = {AGE_CAP}+)")
    ax1.set_ylabel("Mean Gagne score (HIV/AIDS group excluded)")
    ax1.set_title("Comorbidity burden by age")
    ax1.grid(alpha=0.3)
    ax1.legend(frameon=False)

    ok = eq.dropna()
    ax2.bar(ok.age, ok.age_gap, color=HIV_COLOUR, width=0.8)
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xlabel("Age of people with HIV")
    ax2.set_ylabel("Extra years (equivalent control age minus actual age)")
    ax2.set_title("How many years 'older' people with HIV look, in comorbidity terms")
    ax2.grid(axis="y", alpha=0.3)
    finish(fig, "6_comorbidity_age_gap.png")
    print(ok[["age", "equivalent_control_age", "age_gap"]].round(1).to_string(index=False))


def main():
    from gagne_config import connect
    _, groups = load_gagne_rules()
    conn = connect()
    try:
        plot_score_over_time(fetch_scores_by_year(conn))
        plot_condition_prevalence(fetch_prevalence(conn, groups))
        plot_score_distribution(fetch_score_distribution(conn))
        if MATCH_RATIO == 1:
            plot_pair_differences(fetch_pair_differences(conn))
        else:
            print(f"Skipped 4_pair_differences.png: it compares 1:1 pairs, matching ratio is {MATCH_RATIO}.")
        plot_prevalence_gap_heatmap(fetch_prevalence(conn, groups, by_year=True))
        plot_comorbidity_age_gap(fetch_scores_by_age(conn))
    finally:
        conn.close()


if __name__ == "__main__":
    main()