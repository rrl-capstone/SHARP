# Plan

## 1. Get set up

- Get access to the Komodo Research Dataset, the lab's HIV drug list (HIVDrugAbbrev.xlsx in the Olivieri-Mui Lab General folder), and Nemo's code for HIV medication refills and the frailty index
- Download the claims-based frailty index program from Harvard Dataverse (link in Supplement 2)
- Set up a shared project folder; patient-level data stays in the approved environment only
- Start the project log (decision, date, reason) and the code check log (cohort development check, analysis check, final code review)
- Agree with the PI on the items the protocol leaves open:
  - Study years
  - Primary and secondary outcomes
  - Statistical methods and sensitivity analyses (Part III is blank)
  - Frailty cut-points (Part II and Supplement 2 give different ones)
  - Where commercial plans fit in the primary insurance categories
  - Whether HIV medicines count toward the 5+ class polypharmacy cutoff, and how
  - Matching details: birth cohort width, geography level (state, 3-digit zip, or region), and whether matching is redone each year
  - What "same plan" means in the data (same payer, same plan type) and whether a closed-claims span is also required
  - How to handle measures that need lab or vital results (HbA1c, blood pressure, LVEF), since the data has no lab results table
  - Whether an UNKNOWN race and ethnicity value counts as missing demographics
  - Age cutoff: the protocol says both "over 50" and "50+"
  - When hospitalization and death are measured relative to each year

## 2. Prepare the reference lists

- Turn the ATC Level 3 list (Supplement 5) into a simple table: class code, class name, include yes/no
- Fill in the "Include in Analysis" column with the PI (it is empty in the protocol)
- A15 (appetite stimulants) and V20 (surgical dressings) have no Level 3 code in the list, so decide how to handle drugs that map there
- Turn the HIV drug list into a simple table of drug names and abbreviations, with a lamivudine flag
- Turn Supplement 1 into a table of HIV codes (ICD-10, ICD-9, MS-DRG), noting the R75 rule
- Build code lists for the ten conditions (CCW definitions, Supplement 4) and the Charlson index
- Turn Table 1 into a code table for each measure's denominator and numerator; check the codes are valid for the study years (for example, CPT 99201 was deleted in 2021)

## 3. Find people with HIV

- **Inpatient route:** at least one claim in `INPATIENT_EVENTS` with an HIV code in `ADMISSION_DIAGNOSIS_CODE`, `PRIMARY_DIAGNOSIS_CODE`, or `SECONDARY_DIAGNOSIS_CODES`, or an HIV MS-DRG in `DRG_CODE`
- **Outpatient route:** at least two claims in `NON_INPATIENT_EVENTS` with an HIV code in `DIAGNOSIS_CODES` and `SERVICE_DATE` at least 7 days apart. Count distinct `UTILIZATION_ID`, not rows, since this table has one row per service line
- **Medication route:** two successive refills of an HIV medicine other than lamivudine in `PHARMACY_EVENTS` (Nemo's code)
- Count R75 only when the person has a second qualifying claim that is not R75
- Add a yes/no flag for each route plus an overall flag; one person can have more than one
- Save the most recent date each person is known to have HIV

## 4. Apply the yearly eligibility rules

For each study year, keep people who:

- Are 50 or older (study year minus birth year from `PATIENT_DOB`)
- Are alive the whole year (no `PATIENT_DEATH_DATE` in `PATIENT_MORTALITY` in or before that year)
- Have medical and prescription coverage from the same plan for the whole year in `PATIENT_INSURANCE`: periods (`ROW_VALID_START` to `ROW_VALID_END`) cover January 1 to December 31 with no gaps, both the `MX_` (medical) and `RX_` (prescription) fields are filled, and the payer does not change
- Have no missing demographics (`PATIENT_GENDER`, `PATIENT_DOB`, geography, race and ethnicity)
- Record how many people are left after each step, by year and HIV status, for the study flowchart

## 5. Build the comparison group

- Start from eligible people with no HIV evidence by any route, in any year of data
- Match 1:1 to people with HIV on birth cohort, sex, and geography (from `PATIENT_GEOGRAPHY`, as of December 31)
- Check that the two groups are balanced, and record how many people with HIV could not be matched

## 6. Clean the pharmacy data

- Keep final claims only (`TRANSACTION_STATUS`) that were paid (`TRANSACTION_RESULT`)
- Remove rows with a missing drug code (`NDC11`)
- Remove exact duplicate fills

## 7. Map drugs to ATC classes and flag polypharmacy

- Match each `NDC11` and `GENERIC_NAME` to an ATC code, then roll it up to Level 3
- Tag HIV drugs using the lab's HIV list
- Keep a list of drugs that did not match, and review the most common ones by hand
- Drop the classes marked "No" in the include list
- A person takes a class in a year if they have at least one fill for it between January 1 and December 31
- Flag polypharmacy as 5 or more classes, using the rule agreed with the PI for HIV medicines

## 8. Flag conditions and calculate the indexes

- Flag each of the ten conditions for each person each year
- Flag CCW conditions and calculate the Charlson index
- Calculate the frailty index from the 12 months of claims in each year (Nemo's code), as a score and a level
- Set the primary insurance category from `MX_INSURANCE_GROUP` and `MX_INSURANCE_SEGMENT`
- Flag dual eligibility when `MX_INSURANCE_GROUP` and `MX_SECONDARY_INSURANCE_GROUP` are Medicare and Medicaid, in either order

## 9. Calculate the care quality measures

- For each measure and each person each year: in the denominator yes/no, met the numerator yes/no
- Use `PROCEDURE_CODE` in `NON_INPATIENT_EVENTS` and diagnosis codes for assessments, exams, and screenings
- Reuse the drug mapping from step 7 for medication-based numerators. Some need a finer level than ATC Level 3 (PPIs are only part of A02B, and long-acting anticholinergics only part of R03B), so match these on generic name
- Handle the measures that need lab or vital results (HbA1c, blood pressure, LVEF) the way agreed with the PI
- Note that the diabetes measure counts poor control, so a higher rate means worse care

## 10. Build the analysis table

- One row per person per year with: HIV status, route flags, most recent HIV date, matched pair ID, age, sex, race and ethnicity, geography, insurance category, dual eligibility, condition flags, Charlson index, CCW count, frailty score and level, number of ATC classes, polypharmacy flag, denominator and numerator flags for each measure, hospitalization, and death

## 11. Analyze

- Characteristics of people with and without HIV
- How common each condition is, by HIV status and age group
- Care quality for each measure by year, HIV status, and age, and how it changes over the years
- Charlson index, CCW conditions, frailty, and polypharmacy by HIV status
- Factors linked with low care quality
- Links between care quality patterns and hospitalization and mortality
- Models and sensitivity analyses to be set with the PI; ones to propose: a different polypharmacy cutoff, and limiting people with HIV to those found by more than one route
- Optional, not in the PI's outline: most common medication classes and pairs of classes taken together, shown as a heatmap

## 12. Write up

- Fill in the code check log at each checkpoint
- Methods: how people were selected and matched, how conditions, measures, and drug classes were defined
- Results: tables and charts
- Supplement: study flowchart, final include list, drug-matching rates, and code lists
- Share with the PI for review

