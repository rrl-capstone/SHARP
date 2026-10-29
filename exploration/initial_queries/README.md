# Initial exploration (early October 2026)

The team's first-pass queries, run by hand in DBeaver before the protocol-based
pipeline in `sql/` existed. They are kept here, unchanged, as a record. They are
not part of the pipeline, and their numbers are rough descriptive counts, not
study results.

| File | Question | Result (see `notes/eda.md`) |
|---|---|---|
| `01_Dataset_Overview.sql` | How big is the dataset? | 116.0M patients, 5.3M providers, 59.4M aged 50+ |
| `02_HIV_Population.sql` | How many people aged 50+ have HIV? | 286,720 (0.48% of people aged 50+) |
| `03_Hypertension_by_HIV.sql` | How common is hypertension, HIV vs. no HIV? | 77.9% vs. 69.7% |

The DBeaver screenshot of each result is in `assets/images/phase0_eda/`, with the same number as its query.

## How these differ from the protocol pipeline

| | These queries | Protocol pipeline (`sql/`) |
|---|---|---|
| Time frame | All of 2016-2025 pooled together | Each calendar year separately |
| Aged 50+ | Born 1975 or earlier (50+ by 2025) | Age in each study year |
| Eligibility | None applied | Same plan all year, alive all year, no missing demographics |
| HIV codes | B20 and Z21 | Supplement 1: also B97.35, and R75 with a second claim |
| HIV rule | 1 inpatient claim, or 2 outpatient dates any distance apart | 2 outpatient claims at least 7 days apart, or 2 HIV refills (not lamivudine) |
| Comparison group | Random 1% sample, not matched | Matched 1:1 on birth year, sex, and location |
| Hypertension | Any I10-I16 code over 10 years | Defined per year, in Phase 4 |

## What carries forward

- Matching B20 as a range (`>= 'B20' AND < 'B21'`) is right: in US ICD-10-CM, B20 has no
  sub-codes. Phase 2 should keep this.
- The hash-based 1% sample (`MOD(STRTOL(LEFT(MD5(...))))`) is a good way to explore quickly.

## Running them again

They write to `work_wang_life297`, so change that to your own work schema first.
`03` reads the table that `02` creates, so run `02` first.
