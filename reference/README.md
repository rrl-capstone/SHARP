# Code lists

What counts as each condition, procedure, drug and care-quality measure. The pipeline reads
these files on every run; change a code here, never in the SQL. Lists inside a cell are
separated by spaces. Every value is checked before it is written into SQL.

| File | One row is | Used by |
|---|---|---|
| `hiv_drugs.csv` | an HIV drug ingredient or brand, and whether it identifies HIV (List 3) | stage 2, File 06 |
| `census_regions.csv` | a state code and its census region | stage 2 to 4 (matching, characteristics) |
| `conditions.csv` | a condition and its ICD-10-CM prefixes (no dots) | stage 3 (conditions), stage 6 (denominators) |
| `procedure_codes.csv` | a procedure concept and its CPT or HCPCS codes | stage 6 |
| `drug_patterns.csv` | a drug concept and words found in generic drug names | stage 6 |
| `quality_measures.csv` | one Table 1 measure | stage 6 |
| `gagne_diagnosis_lookup.csv` | one Gagne code rule (exact code, prefix or range), from Nemo | stage 5 (Rhea's code) |
| `gagne_weight_lookup.csv` | one Gagne group and its weight, from Nemo | stage 5 |

**`hiv_drugs.csv`.** From HIVDrugAbbrev.xlsx (Supplement 6). A fill identifies HIV when its
generic name contains an ingredient, or its brand name a brand, with `identifies_hiv = yes`.
Drugs marked `no` (with the reason in `why_not`) are also given to people without HIV, so they
never identify HIV on their own; a product that also contains a `yes` ingredient still counts.
To change which drugs identify HIV, change this file: `tests/test_hiv_drugs.py` lists the PI's
exclusions and fails if any other drug drops out.

**`census_regions.csv`.** The four Census Bureau regions. Any other state code (territories,
unknown) becomes `Other`, so nobody drops out of matching.

**`conditions.csv`.** `study_condition = yes` rows are reported in the comparisons; `no` rows
are only used by a measure (heart failure, GERD alarm symptoms). `rule = claims` needs 1
inpatient claim, or 2 outpatient claims on different days, in the year (`config/study.yml`
`conditions`); `rule = any_claim` needs any one claim.

**`quality_measures.csv`.** `+` means AND and `|` means OR, so
`antihypertensive|bp_sys_lt140+bp_dia_lt90` is "a blood pressure medicine, or both BP result
codes". `lookback_years` is how many years, counting the measurement year, the numerator may
come from. `missing_as_met` names a concept whose absence counts as meeting the numerator (the
diabetes measure counts "not tested" as poor control). `higher_is_better = 0` marks measures
where a higher share is worse care.

**Gagne lookups.** Nemo Zhou's files (`clinical_metric_lookups_2026-06-24`, built from the
score's SAS formats), kept exactly as supplied so their checksums still match. Replace both to
update them; do not edit rows by hand. Only the ICD-10-CM rows are used.

## Status: provisional

The condition, procedure, drug and measure lists were drafted from published definitions so
the pipeline runs end to end. Before reporting results, check them against the protocol:

- Conditions: Supplement 4 (CCW definitions). Measures: the protocol's Table 1.
- Lab and vital-sign results (HbA1c above 9%, BP below 140/90, LVEF below 40%) use CPT
  Category II result codes, which appear only when clinics report them.
- Gagne: confirm with Nemo or the PI the HIV/AIDS weight of -1, and that depression (F32, F33)
  counts under psychosis.
