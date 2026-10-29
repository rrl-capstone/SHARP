# The pipeline, step by step

`python -m runner` runs these in order (the order is defined once, in `runner/steps.py`). Every
table is written to your work schema and rebuilt from scratch each run, so any step can be rerun.
Table names end in the profile's suffix (`_s1`, `_s30`, none for `full`), so the three profiles
can run at once.
Every SELECT in a step is a check: it prints, and is saved to `results/<run>/<stage>/<name>.csv`
with counts from 1 to 10 shown as `<11`.

| Stage | Step | Builds | What it does |
|---|---|---|---|
| **1 Cohort** (Lifei) | `00_sample.sql` | `study_ids` | People in this run: the repeatable ~1% or ~30% sample, or everyone (`--profile`) |
| | `01_age50_alive.sql` | `age50_alive` | Person-years 2016 to 2025: aged 50+ on Dec 31 and alive all year |
| | `02_same_insurance_all_year.sql` | `same_insurance` | Medical and pharmacy closed all year, one medical and one pharmacy payer |
| | `03_demographics.sql` | `eligible_person_years`, `eligible_ids` | Drops missing birth date, sex, state (on Dec 31) or race |
| **2 HIV groups** (Lifei) | `04_hiv_dx_inpatient.sql` | `hiv_dx_inpatient` | 1+ inpatient HIV diagnosis (R75 needs another HIV code), or an HIV MS-DRG |
| | `05_hiv_dx_outpatient.sql` | `hiv_dx_outpatient` | HIV diagnoses on 2 outpatient dates at least 7 days apart |
| | `06_hiv_rx.sql` | `hiv_rx_fills_all`, `hiv_rx_drug_names`, `hiv_rx` | 2 fills of identifying HIV drugs 1 to 90 days apart (`reference/hiv_drugs.csv`) |
| | `07_pwh_cohort.sql` | `pwh_all`, `pwh_cohort` | **The HIV group**: person-years from the first HIV year, closed from the HIV date on |
| | `08_any_hiv_evidence.sql` | `any_hiv_evidence_ids` | Anyone with any HIV record at all (reported only) |
| | `09_nonhiv_pool.sql` | `nonhiv_pool` | **The control pool**: eligible person-years of everyone who is not an HIV case |
| **3 Conditions** | `1_study_person_years.sql` | `study_person_years` | The HIV group and the control pool together, with `hiv` 1/0, sex, race, census region |
| | `2_condition_codes.py` | `ref_conditions` | Loads `reference/conditions.csv` |
| | `3_condition_dx_rows.sql` | `condition_dx_rows` | [HEAVY] One diagnosis scan per year, condition codes only |
| | `4_person_year_conditions.sql` | `person_year_conditions` | Each person-year's conditions; **comparison before matching** |
| **4 Matching** (Lifei) | `10_ps_input.sql` | `ps_input` | The HIV group plus 20 random controls per case, by year and sex |
| | `11_ps_matching.R` | `ps_matched` | Per year, 1:1: nearest neighbour, exact on sex, score from birth year, census region and race, caliper `matching.caliper_sd`; balance before and after |
| | `12_matched_summaries.sql` | | Who was matched, characteristics before and after, CONSORT for year one; **comparison after matching** |
| **5 Gagne** (Rhea) | `gagne_1_evidence.py` | `gagne_person_years`, `gagne_rules`, `gagne_dx_candidates`, `gagne_code_map`, `gagne_group_evidence` | One diagnosis scan; Nemo's rules on the distinct codes |
| | `gagne_2_scores.py` | `gagne_scores` | Per matched person-year: 20 group flags, `gagne_score`, `gagne_score_excl_hiv` |
| | `gagne_3_plots.py`, `gagne_4_network.py` | `results/<run>/5_gagne/plots/` | Seven plots (aggregates only) |
| | `gagne_5_summaries.sql` | | Scores, levels, group prevalence and the comorbidity network (`gagne_network_links`: pairs of groups and their lift) as tables |
| **6 Care quality** | `1_measure_codes.py` | `ref_procedures`, `ref_drug_patterns`, `ref_measures` | Loads the measure code lists |
| | `2_procedure_rows.sql` | `matched_ids`, `care_px_concepts` | [HEAVY] Procedure claims of the matched people, from 5 years before 2016 |
| | `3_drug_rows.sql` | `care_generic_fills`, `care_drug_map`, `care_rx_concepts` | [HEAVY] Final, paid fills of the matched people |
| | `4_quality_measures.py` | `measure_concepts`, `measure_flags`, `quality_measures` | Every Table 1 measure: denominator, and met or not |
| | `5_care_quality_results.sql` | | Rates: overall, per year, **by Gagne level**, by age |

## The rules each step follows

- **HIV drugs (PI, `notes/methods.md`).** Lamivudine, ritonavir, tenofovir, emtricitabine,
  cabotegravir and lenacapavir do not identify HIV on their own (`identifies_hiv = no` in
  `reference/hiv_drugs.csv`); a product that also contains another HIV drug still counts. Only
  final, paid claims count.
- **Control pool (PI).** Anyone eligible who is not an HIV case, even with a single HIV record.
  HIV cases are left out in every year, including the years before HIV was first found.
- **Matching variables (PI).** Birth year, sex (exact), census region and race.
- **Conditions.** Found once for the HIV group and the control pool, so the comparisons before
  and after matching use the same flags. `rule = claims`: 1 inpatient or 2 outpatient claims on
  different days in the year; `rule = any_claim`: any claim.
- **Matching weights.** `ps_matched.match_weight` is MatchIt's weight (all 1 with 1:1 matching).
  Every percentage and average after matching uses it; counts are people.
- **Gagne as a filter.** Care quality is also compared within Gagne levels (score without the
  HIV/AIDS group, levels from `gagne.level_tops`), so people with HIV are compared with
  controls who are about as sick.

## Writing a new step

1. Put the file in its stage folder and add one line to `STEPS` in `runner/steps.py`.
2. Use `${work_schema}`, `${komodo_schema}` and the other variables in `runner/config.py`
   (`sql_variables`); never write a schema name or a study year into the SQL. Every work-schema
   table is `${work_schema}.<name>${sfx}` (a test fails otherwise).
3. Start with `DROP TABLE IF EXISTS`, so the step can be rerun.
4. Put `-- result: <name>` above every SELECT, and `-- expect: a = b` above any check that
   must hold. Name percentages `pct_*` and averages `mean_*`; every other number is a count.
5. A scan of a big Komodo table goes one year at a time: `-- for each year: study` above the
   INSERT.
6. `python -m runner --dry-run` renders everything to `build/rendered/`; `python -m pytest`
   checks it.

A frailty index, for example, would be a new stage folder with its steps, one more block in
`STEPS`, and one more `JOIN` in the care-quality results.
