# OHDSI-3: Care quality in people with and without HIV

Group 3, fall 2026 capstone, with the Olivieri-Mui Lab at Northeastern University.

People with HIV develop age-related conditions earlier than people without HIV. Using Komodo
insurance claims from 2016 to 2025, this project follows adults aged 50 and over one year at a
time, compares which chronic conditions people with and without HIV have, matches each person
with HIV to similar people without HIV, measures how sick each group is (Gagne comorbidity
score), and compares how often their conditions are treated to standard.

## The pipeline

Six stages, run in order by one command (details of every step: [`pipeline/README.md`](pipeline/README.md)):

1. **Cohort** (Lifei): every person-year aged 50+, alive and fully insured all year, with no
   missing demographics.
2. **HIV groups** (Lifei, with the PI's drug rules): the HIV group, and a control pool of
   everyone else who is eligible.
3. **Conditions** (Rama): which of the study conditions each person has each year; the two groups
   compared **before matching**.
4. **Matching** (Rama): 1:1 propensity score matching within each year on birth year, sex,
   census region and race; characteristics before and after, a CONSORT count for year one, and
   the conditions compared again **after matching**.
5. **Gagne** (Rhea): how sick each matched person is.
6. **Care quality** (Rama): each Table 1 measure in the matched groups, overall and **within Gagne
   levels**, so people with HIV are compared with controls who are about as sick.

## Running it

On a machine that can reach Redshift (the lab workspace), from this folder:

```
pip install -r requirements.lock
copy config\local.example.yml config\local.yml
```

Edit `config/local.yml`: your Redshift username and the folder holding the Redshift JDBC driver.
In R, once: `install.packages(c("DatabaseConnector", "dplyr", "MatchIt"))`. Then:

```
python -m runner --check
python -m runner
```

`--check` tests your connection and schema. The run asks for your Redshift password once (or
reads `REDSHIFT_PASSWORD`); it is never saved.

There are three profiles, chosen with `--profile` (default: `run.profile` in `config/study.yml`):

| Profile | People | Table names | Results |
|---|---|---|---|
| `sample_1pct` | the repeatable ~1% sample | end in `_s1` | `results/sample_1pct/` |
| `sample_30pct` | the repeatable ~30% sample (includes the 1%) | end in `_s30` | `results/sample_30pct/` |
| `full` | everyone | no suffix | `results/full/` |

Each profile has its own tables and results, so the three can run at the same time in three
terminals, for example `python -m runner --profile sample_30pct`.

If a step fails, the run stops, says why, and prints the command to resume, for example
`python -m runner --from 4_matching`. `python -m runner --only 07_pwh_cohort.sql` runs a single
step, and `python -m runner --dry-run` writes every statement it would run to `build/rendered/`
without touching the database.

## Results

Each run saves aggregate tables to `results/<profile>/`, one folder per stage, plus Rhea's plots in `5_gagne/plots/` and `run_info.json` (when, from which commit, with
which settings). Counts from 1 to 10 are shown as `<11`, and the percentages next to them are
blanked. Every other count is rounded to the nearest 10 (never shown below 20) and percentages to
one decimal, so a hidden count cannot be worked out from totals. After changing this rule, run
`python -m runner.results` to re-apply it to the saved CSVs. Only these files leave Redshift; patient-level tables stay in your work schema, and
the matching backup `build/matched.rds` is never committed.

To share a run: commit `results/` and push.

## Website

[`docs/`](docs/) is a website that draws every result for the three runs, published at
https://rrl-capstone.github.io/SHARP/. The workflow
[`.github/workflows/pages.yml`](.github/workflows/pages.yml) publishes it on every push to `main`
that changes `docs/` or `results/`: it rebuilds the site's data from `results/` with
`python -m runner.site_data` (only finished runs are published), then deploys `docs/`. To look at
it before pushing, run `python -m runner.site_data` and open `docs/index.html` in a browser.
Pages is set up once in the repository settings: Pages, Source: GitHub Actions.

## Repository layout

| Path | What's in it |
|---|---|
| [`config/`](config/) | `study.yml`: every study setting, in one place. `local.yml`: your own settings (not committed) |
| [`pipeline/`](pipeline/) | The six stages, one folder each, steps in run order |
| [`runner/`](runner/) | Runs the steps (the order is listed once, in `runner/steps.py`) and saves results |
| [`reference/`](reference/) | Code lists: conditions, procedures, drugs, measures, Gagne lookups |
| [`results/`](results/) | Saved aggregate results of each run; `teammates_original/` holds Rhea's earlier plots |
| [`tests/`](tests/) | Checks that run without the database: `python -m pytest` |
| [`notes/`](notes/) | Proposal, plan, methods decisions, literature, EDA, and [how this repository is organized](notes/repo_structure.md) |
| [`exploration/`](exploration/) | The team's first DBeaver queries, kept as a record |
| [`assets/`](assets/) | Images, the Komodo data model diagram, and the presentation |
| [`docs/`](docs/) | The results website (GitHub Pages); its data is rebuilt by `python -m runner.site_data` |

## Where the code came from

Commit `e06303d` is Lifei's and Rhea's code exactly as supplied. Since then:

- Schema names, study years and the sample switch come from `config/` instead of being typed
  into each file, so anyone can run it in their own schema. The logic is unchanged.
- The PI's decisions from the October 2026 lab meetings (`notes/methods.md`):
  - File 06: the HIV drug lists moved to `reference/hiv_drugs.csv`; lamivudine, ritonavir,
    tenofovir, emtricitabine, cabotegravir and lenacapavir no longer identify HIV on their own.
    Only final, paid pharmacy claims count.
  - File 09: anyone who is not an HIV case can be a control (File 08 is now only reported).
  - Files 10 and 11: matching uses census region instead of state, 1:1.
- File 11 reads its settings from the runner, saves the match weights and the balance before
  and after matching, and stops if a matched set is malformed. File 12 adds the
  characteristics before and after matching and the CONSORT count for year one.
- Stages 3 and 6 are new: they reuse the condition and care-quality logic of the team's
  earlier pipeline, now run on Lifei's cohort.

## Open items

- **To confirm with the PI:** Viread and Vemlidy as non-identifying drugs (she hesitated);
  whether people with an HIV diagnosis code that does not meet the definition may be controls.
- **Table 1 is partial.** Insurance type and dual eligibility, which the PI listed as
  descriptors, are not in Lifei's tables yet.
- **Code lists are provisional** until checked against Supplement 4 and Table 1
  ([`reference/README.md`](reference/README.md)).
- **Statistical methods** (confidence intervals, repeated years per person) are still to be
  agreed with the PI; results are descriptive.
- **Small-cell rule.** Counts 1 to 10 are hidden, but a hidden count can sometimes be worked
  out from a total and its neighbours; check tables before publishing.
- **Not built yet:** the claims-based frailty index and polypharmacy (ATC classes). Each would
  be one more stage folder.

## Mid-semester presentation (October 2026)

| | |
|---|---|
| Video, 9.5 minutes | [`assets/presentation/presentation.mp4`](assets/presentation/presentation.mp4): Rhea on the background and literature, Lifei on progress and challenges, Rama on the website and results |
| Slides | [`assets/presentation/slides.pptx`](assets/presentation/slides.pptx): progress, challenges and next steps |

## Team

Rhea Thomas, Lifei Wang and Rama Krishna Chavali. Stakeholder: Brianne Olivieri-Mui, PhD, MPH.
