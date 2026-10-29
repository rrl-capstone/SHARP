"""
Gagne step 4: comorbidity network plot.

Run:  python gagne_4_network.py      (after gagne_2_scores.py; needs gagne_3_plots.py in the same folder)
Needs: pip install matplotlib

Saves in the "plots" folder:
  7_comorbidity_network.png   which conditions occur TOGETHER more than chance,
                              people with HIV vs matched controls

How the network works
---------------------
For every pair of conditions (A, B) we count person-years that have both.
"Lift" compares that with what you'd expect if A and B were unrelated:
    lift = P(A and B) / (P(A) x P(B))
lift = 1 means no link; lift = 2 means they occur together twice as often as
chance. Only the TOP_LINKS strongest pairs (with lift >= MIN_LIFT) are drawn
in each panel, thicker = stronger; sicker people tend to have many conditions
at once, so drawing every pair above a threshold fills the whole circle.
Lift is used instead of raw counts so very common conditions (hypertension,
in ~60% of person-years) don't connect to everything just by being common.

Privacy: Redshift returns only aggregate counts (pairs of conditions);
any count under 11 is dropped (small-cell rule).
These are descriptive and PROVISIONAL (medication-only filter not yet applied).
"""

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from gagne_config import table, query_df, load_gagne_rules
from gagne_3_plots import (HIV_COLOUR, CONTROL_COLOUR, LABELS, SCORE, MIN_CELL,
                           pretty, finish)

MIN_LIFT = 1.2        # a pair must be at least 1.2x more common together than chance
TOP_LINKS = 25        # draw only the 25 strongest pairs per panel
LEAVE_OUT = {"hiv_aids"}   # 0% in controls by design, so it can't be compared


# =============================================================================
# Queries (aggregates only)
# =============================================================================

def fetch_network_counts(conn):
    """Returns (pairs, singles, totals):
    pairs:   hiv, g1, g2, n   person-years with both conditions
    singles: hiv, g, n        person-years with each condition
    totals:  hiv, n           person-years in each group"""
    pairs = query_df(conn, f"""
        SELECT py.hiv, a.gagne_group AS g1, b.gagne_group AS g2, COUNT(*) AS n
        FROM {table('evidence')} a
        JOIN {table('evidence')} b
          ON b.patient_id = a.patient_id
         AND b.analysis_year = a.analysis_year
         AND b.gagne_group > a.gagne_group          -- each pair once
        JOIN {table('person_years')} py
          ON py.patient_id = a.patient_id
         AND py.analysis_year = a.analysis_year
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= {MIN_CELL}""")
    singles = query_df(conn, f"""
        SELECT py.hiv, e.gagne_group AS g, COUNT(*) AS n
        FROM {table('evidence')} e
        JOIN {table('person_years')} py
          ON py.patient_id = e.patient_id
         AND py.analysis_year = e.analysis_year
        GROUP BY 1, 2
        HAVING COUNT(*) >= {MIN_CELL}""")
    totals = query_df(conn, f"SELECT hiv, COUNT(*) AS n FROM {table('person_years')} GROUP BY 1")
    return pairs, singles, totals


# =============================================================================
# Plot 7: comorbidity network
# =============================================================================

def network_tables(pairs, singles, totals, groups):
    """Per group (HIV / control): node prevalence and edge lift."""
    keep = groups[~groups.group_name.isin(LEAVE_OUT)]
    names = dict(zip(keep.gagne_group, keep.group_name))
    out = {}
    for hiv in (0, 1):
        total = int(totals.loc[totals.hiv == hiv, "n"].iloc[0])
        prev = singles[singles.hiv == hiv].set_index("g").n / total
        e = pairs[(pairs.hiv == hiv) & pairs.g1.isin(names) & pairs.g2.isin(names)].copy()
        e["lift"] = (e.n / total) / (e.g1.map(prev) * e.g2.map(prev))
        e = e[e.lift >= MIN_LIFT].nlargest(TOP_LINKS, "lift")
        out[hiv] = (prev.reindex(list(names)).fillna(0), e)
    return out, names


def plot_comorbidity_network(pairs, singles, totals, groups):
    tables, names = network_tables(pairs, singles, totals, groups)
    ids = list(names)
    angle = {g: 2 * math.pi * i / len(ids) for i, g in enumerate(ids)}
    pos = {g: (math.cos(a), math.sin(a)) for g, a in angle.items()}
    all_lifts = pd.concat([t[1].lift for t in tables.values()])
    lo, hi = (all_lifts.min(), all_lifts.max()) if len(all_lifts) else (MIN_LIFT, MIN_LIFT)

    fig, axes = plt.subplots(1, 2, figsize=(16, 8.5))
    for ax, hiv, colour in [(axes[0], 0, CONTROL_COLOUR), (axes[1], 1, HIV_COLOUR)]:
        prev, edges = tables[hiv]
        for e in edges.sort_values("lift").itertuples():      # strongest drawn on top
            (x1, y1), (x2, y2) = pos[e.g1], pos[e.g2]
            strength = (e.lift - lo) / max(hi - lo, 1e-9)   # same scale in both panels
            ax.plot([x1, x2], [y1, y2], color=colour, lw=0.5 + 4 * strength,
                    alpha=0.15 + 0.65 * strength, zorder=1)
        for g in ids:
            x, y = pos[g]
            ax.scatter(x, y, s=60 + 2500 * prev[g], color=colour, edgecolor="white",
                       lw=1.5, zorder=3)
            ax.text(1.17 * x, 1.17 * y, pretty(names[g]), fontsize=8.5,
                    ha="left" if x > 0.05 else "right" if x < -0.05 else "center",
                    va="center", zorder=4)
        ax.set_title(f"{LABELS[hiv]}", fontsize=13)
        ax.set_xlim(-1.75, 1.75)
        ax.set_ylim(-1.35, 1.35)
        ax.set_aspect("equal")
        ax.axis("off")
    fig.suptitle(f"Which conditions cluster together? Circle size = how common; "
                 f"lines = the {TOP_LINKS} pairs most over-represented vs chance (thicker = stronger)",
                 fontsize=12)
    finish(fig, "7_comorbidity_network.png")

    # Also print the strongest links so they can be quoted
    for hiv in (1, 0):
        top = tables[hiv][1].sort_values("lift", ascending=False).head(8)
        print(f"\nStrongest links, {LABELS[hiv]}:")
        for e in top.itertuples():
            print(f"  {pretty(names[e.g1])} + {pretty(names[e.g2])}: lift {e.lift:.1f}")


def main():
    from gagne_config import connect
    _, groups = load_gagne_rules()
    conn = connect()
    try:
        plot_comorbidity_network(*fetch_network_counts(conn), groups)
    finally:
        conn.close()


if __name__ == "__main__":
    main()