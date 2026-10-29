# Methods notes for the protocol

Decisions made with the PI that the protocol document should state. Each is implemented in
the pipeline as noted (paths are under `pipeline/`).

## Identifying people with HIV (Dr. Olivieri-Mui, October 2026)

**Three routes, compared.** A person is identified as having HIV through any of three routes:
(1) an inpatient HIV diagnosis or HIV MS-DRG, (2) two outpatient HIV diagnoses at least seven
days apart, or (3) two fills of HIV medicines within 90 days. The three lists usually overlap
heavily.

**Drugs that do not identify HIV (lab meeting, late October 2026).** Some HIV medicines are
also given to people without HIV, so for the medication route (List 3) they are treated the way
lamivudine always was: they do not identify an HIV case on their own, and are used later, when
treatment regimens are studied.

| Not used to identify HIV | Why |
|---|---|
| lamivudine | also treats hepatitis B (protocol) |
| ritonavir | a booster: also in Paxlovid (COVID-19) and the hepatitis C regimens Technivie and Viekira |
| tenofovir | hepatitis B on its own (Viread, Vemlidy); PrEP with emtricitabine |
| emtricitabine | PrEP with tenofovir (Truvada, Descovy) |
| cabotegravir | PrEP on its own (Apretude) |
| lenacapavir | PrEP on its own (Yeztugo) |

A product that also contains another HIV medicine still counts (Biktarvy through bictegravir,
Kaletra through lopinavir), so people taking any of these as part of a treatment regimen are
still identified through the other drugs in the regimen. This replaces the earlier rules that
removed Paxlovid and the hepatitis C regimens by name and reviewed PrEP-only people by hand.
Still to confirm: the PI hesitated over Viread and Vemlidy, which are also used for HIV in
combination; under this rule those people are identified through their other HIV drugs.
*Pipeline: `reference/hiv_drugs.csv` (`identifies_hiv`), used by Step 1 of
`2_hiv_groups/06_hiv_rx.sql`.*

**Start of HIV status.** A person counts as having HIV from the year the definition is first
met onward, including later years without HIV claims.

**Most recent date known to have HIV.** This is the last date on which the HIV definition is
met: the last qualifying inpatient claim, the last outpatient HIV claim once two claims at
least seven days apart exist, or the last HIV medicine fill that follows another within 90
days. A later HIV record that does not on its own meet the definition (for example a single
medicine fill) does not change this date. *Pipeline: `last_hiv_date` in
`2_hiv_groups/07_pwh_cohort.sql`.*

## People without HIV (lab meeting, late October 2026)

**Anyone who is not an HIV case can be a control**, including people with a single HIV
medicine fill or code, because the control pool should not be limited and propensity matching
handles the confounding. HIV cases are left out of the pool in every year, including the years
before their HIV was first found. *Pipeline: `2_hiv_groups/09_nonhiv_pool.sql`; the number of
controls with some HIV record is saved as `controls_with_some_hiv_record`.* Still to confirm:
whether this also covers people with HIV diagnosis codes that do not meet the definition (the
PI's words were "anybody who is not a case of HIV").

## Matching (lab meeting, late October 2026)

**1:1 propensity score matching, one study year at a time.** Matching variables are those in
the protocol: birth cohort (birth year), sex (matched exactly) and geography, plus race and
ethnicity. Geography is the four census regions (Northeast, Midwest, South, West), not the
state. Comorbidity (Gagne) and frailty are not matching variables; matching comes before those
are developed. *Pipeline: `4_matching/10_ps_input.sql` (census region from
`reference/census_regions.csv`) and `4_matching/11_ps_matching.R` (`config/study.yml`
`matching`).*

**How matching is reported.** The characteristics of the HIV group and the control pool before
matching and of the matched groups after (`characteristics_before_and_after_matching`,
`age_before_and_after_matching`), and the standardized mean difference of each matching
variable before and after (`balance_smd.csv`, from MatchIt).

**CONSORT diagram.** For the first study year, how many people each inclusion and exclusion
step leaves, from everyone in Komodo to the matched groups (`consort_first_year`).

## Care quality over time (lab meeting, late October 2026)

Care quality is a trend analysis: each year is calculated independently, as the share of people
with a condition who receive the recommended care, by HIV status. Following individuals over
time (accumulating conditions) is a possible later project.
