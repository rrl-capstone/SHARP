# Proposal

## Background

### HIV today

Thanks to modern HIV treatment, people with HIV can now live long, healthy lives. HIV has become a long-term condition that is managed with daily medicine, much like diabetes or high blood pressure. As a result, the group of people living with HIV is getting older, and many now live into their 60s, 70s, and beyond.

### Age-related conditions start earlier

Living longer also means more time to develop other health conditions. People with HIV often get conditions linked to older age, such as heart disease, high blood pressure, diabetes, arthritis, and dementia, and they often get them years earlier than people without HIV. Most providers do not expect to see these conditions in younger patients. Because of this, the care these conditions receive may be lower in quality for people with HIV than for people without HIV.

### More conditions, more medicines

Each condition usually brings its own medicine. Having several conditions at the same time can lead to **polypharmacy**, which in this study means taking medicines from five or more ATC Level 3 classes. Polypharmacy is not always a problem, since many people genuinely need several medicines. But it does raise some real risks:

- **Drug interactions.** Some HIV medicines change how the body processes other drugs, which can make those drugs too strong or too weak.
- **Side effects.** More medicines mean more chances of side effects such as dizziness, falls, or confusion, especially in older adults.
- **Missed doses.** The more pills someone has to manage, the harder it is to take them all on time. Missing HIV doses can cause the treatment to stop working.
- **Cost.** More prescriptions mean higher costs for patients and for insurers.

### Treating every condition is not always best

Standard care quality measures are built one condition at a time: they ask whether each condition got its recommended care. Geriatric care models take a different view and put what matters most to the patient first. For someone with many conditions, treating some conditions rather than all of them may sometimes lead to better health. This study aims to understand the mix and intensity of treatment that goes with the best health outcomes, by looking at which conditions people have, how many are being treated, and how that changes over time.

### Using claims data

Insurance claims data shows every prescription a person fills at a pharmacy, along with their diagnoses, procedures, age, insurance, and where they live. Because it covers millions of people across the country, it can show real-world care patterns that small clinical studies cannot. This project uses the **Komodo Research Dataset**, a large US claims database.

### Measuring care quality

For each of ten common conditions, the lab protocol defines a care quality measure (Table 1 of the protocol). Each measure has a **denominator**, the people who should receive a type of care, and a **numerator**, the people who actually received it. We calculate each measure for each person in each year, which lets us follow care quality over time.

| Condition | What the measure checks |
|---|---|
| Rheumatoid arthritis | Periodic disease assessment; glucocorticoid assessment |
| Osteoarthritis | Function and pain assessment; over-the-counter pain medication assessment |
| Dementia | Cognition assessment in the last 12 months |
| Diabetes | Poor control: most recent HbA1c above 9.0%, missing, or not tested (a higher rate means worse care) |
| GERD | Prescribed a PPI; endoscopy for people with an alarm symptom |
| Coronary artery disease | ACE inhibitor or ARB for people who also have diabetes or LVEF below 40% |
| Hypertension | Antihypertensive prescribed, or blood pressure controlled (below 140/90) |
| Peripheral neuropathy | Lower-extremity neurological exam for people with diabetes |
| COPD | Long-acting inhaled anticholinergic bronchodilator |
| Hearing and vision | Hearing and vision screening for people 50 and older |

### Grouping medicines into classes

One challenge with prescription data is that it is very detailed. The same medicine can appear under many brand names, strengths, and package sizes, which results in thousands of different drug codes. Counting individual codes would make the results hard to read and hard to compare.

To solve this, we group each medicine into a class using the WHO **ATC system** (Anatomical Therapeutic Chemical). ATC is the international standard for grouping medicines. It sorts them in levels, from broad to specific:

- **Level 1** is the body system, for example "Cardiovascular system" (C).
- **Level 2** is the main treatment group, for example "Agents acting on the renin-angiotensin system" (C09).
- **Level 3** is a more specific group, for example "ACE inhibitors, plain" (C09A).

We work at **ATC Level 3**, which has 267 classes in the lab's list (Supplement 5). The protocol defines polypharmacy at this level.

Not every ATC class is useful for this study. Some classes cover items that are not regular medicines, such as diagnostic agents, contrast dyes used for scans, and surgical dressings. These are left out using the "Include in Analysis" column of Supplement 5, which will be filled in with the PI.

### Handling HIV medicines separately

ATC places almost all HIV medicines into one broad class of antiviral drugs. That is too general to tell different HIV treatments apart. So HIV medicines are identified and grouped separately using the lab's own HIV drug list (Supplement 6). Whether HIV medicines count toward the five-class polypharmacy cutoff, and if so as one class or several, still needs to be decided *TBD)*. This matters because the comparison group does not take HIV medicines.

## Research question and hypothesis

This is an exploratory study that characterizes comorbidity profiles and care quality trajectories in people with HIV aged 50 and older, compared with matched people without HIV.

**Hypothesis:** Comorbidity profiles and care quality trajectories differ significantly between people with and without HIV. For example, more people with HIV will have age-related conditions, and care quality will be lower at younger ages than at older ages.

Specific questions:

1. How common is each of the ten chronic conditions in people with and without HIV, and how does this vary by age?
2. For each condition, what share of people receive the recommended care each year, and how does this change over time in each group?
3. How do comorbidity burden (Charlson index, CCW conditions), frailty, and polypharmacy differ between people with and without HIV?
4. Which factors are linked with low care quality?
5. How are patterns of care quality linked with hospitalizations and mortality?

**Primary and secondary outcomes:** not yet specified in the protocol *TBD)*.

## Study design

| Item | Definition |
|---|---|
| Comparison | HIV status: people with HIV vs. matched people without HIV |
| Measurement period | Each calendar year, January 1 to December 31 |
| Index date | December 31 of each year |
| Follow-up | One year, January 1 to December 31 |
| Censoring | None; only people alive and insured for the whole year are included |
| Study years | *TBD* |

## Data

We use the **Komodo Research Dataset**. The tables we need are:

| Table | What we use it for |
|---|---|
| `PHARMACY_EVENTS` | Prescription fills: drug code (NDC11), generic name, fill date, days supply; HIV medication refills |
| `INPATIENT_EVENTS` | Diagnosis and DRG codes, used to find people with HIV and their conditions; hospitalizations |
| `NON_INPATIENT_EVENTS` | Diagnosis and procedure codes (CPT, HCPCS), used to find people with HIV, their conditions, care quality measures, and the frailty index |
| `PATIENT_DEMOGRAPHICS` | Birth year and gender |
| `PATIENT_RACE_ETHNICITY` | Race and ethnicity |
| `PATIENT_INSURANCE` | Medical and prescription plan periods, primary and secondary insurance; used for enrollment, insurance type, and dual eligibility |
| `PATIENT_GEOGRAPHY` | State and 3-digit zip; used for matching and geography |
| `PATIENT_MORTALITY` | Month and year of death |
| `PATIENT_CLOSED` | Periods when a patient's claims are fully captured *TBD whether this is also required)* |

We also use the reference lists in the protocol supplements: HIV codes (Supplement 1), the claims-based frailty index (Supplement 2), CCW chronic conditions (Supplement 4), ATC Level 3 classes (Supplement 5), the lab's HIV drug list (Supplement 6), and the care quality measures (Table 1). Existing lab code from Nemo is used to identify HIV medication refills and to calculate the frailty index.

## Who is in the study

### People with HIV

Anyone who meets at least one of these:

- At least one inpatient claim with an HIV diagnosis
- At least two outpatient claims with an HIV diagnosis, at least one week apart
- At least two successive refills of an HIV medicine other than lamivudine (lamivudine is left out because it is also used to treat hepatitis B)

HIV codes come from Supplement 1: ICD-10 B20, B21–B24, B97.35, Z21, and R75 (R75 is a screening code, so it only counts with a second qualifying claim that is not R75); MS-DRG 969, 970, 974, 975, 976, and 977; and ICD-9 codes for any data before October 2015.

For each person we record which route identified them (inpatient, outpatient, medication, and overall, even when routes overlap) and the most recent date we know they have HIV.

### People without HIV

Matched 1:1 to people with HIV by birth cohort, sex, and geography, with no evidence of HIV by any route. The exact birth cohort and geography definitions are still to be set *TBD)*.

### Both groups, each year

- Aged 50 or older
- Alive for the whole year
- Enrolled in the same insurance plan, for both medical and prescription coverage, for the whole year; people who switch payers are excluded

### Exclusions

- Missing demographics
- Missing variables needed to calculate the frailty index, Charlson index, CCW conditions, or polypharmacy, for the analysis that uses them

## Measurements

- **Demographics:** age, sex, geography, race and ethnicity
- **Chronic conditions:** arthritis (rheumatoid and osteoarthritis), dementia, diabetes, gastrointestinal disease (GERD), heart disease (coronary artery disease), hypertension, peripheral neuropathy, respiratory conditions (COPD), hearing and vision deficits
- **Care quality:** the Table 1 measures, for each person each year
- **Comorbidity:** Charlson comorbidity index; CCW chronic and disabling conditions
- **Frailty:** claims-based frailty index, as a score and a level: non-frail (below 0.25), mildly frail (0.25–0.34), moderately-to-severely frail (0.35 and above). Supplement 2 suggests different cut-points *TBD)*.
- **Polypharmacy:** medicines from 5 or more ATC Level 3 classes
- **Primary insurance:** Medicare (fee-for-service, Advantage), Medicaid (state, managed), Other (IHS, VA), Unknown. The protocol describes the data as commercial claims but does not list a commercial category *TBD)*.
- **Dual eligibility:** Medicare and Medicaid as the primary and secondary insurance, in either order
- **Hospitalizations and mortality**

## Approach

1. **Find people with HIV** using the three routes, with a flag for each route and the most recent HIV date.
2. **Apply the yearly rules:** aged 50+, alive all year, same medical and prescription plan all year, no missing demographics.
3. **Build the matched comparison group** of people without HIV.
4. **Group medicines:** keep final, paid prescription claims, group each drug into its ATC Level 3 class (HIV drugs tagged separately), drop excluded classes, and count classes per person per year.
5. **Flag chronic conditions** and calculate the Charlson index, CCW conditions, and frailty index.
6. **Calculate the care quality measures** for each person each year.
7. **Analyze** differences by HIV status and age, care quality over time, factors linked with low care quality, and links with hospitalization and mortality. Statistical methods and sensitivity analyses are still to be set *TBD; Part III of the protocol is blank)*.

## Expected results

- Comorbidity profiles of people with and without HIV, by age
- Care quality for each condition by year, for each group
- Comparisons of comorbidity burden, frailty, and polypharmacy by HIV status
- Factors linked with low care quality
- A reusable drug-to-ATC mapping table and code lists the lab can use in future studies

## Why it matters

This work shows whether people with HIV, who develop age-related conditions earlier, receive lower-quality care for those conditions, and how care patterns relate to hospital stays and death. It can help clinicians and researchers decide when treating every condition makes sense and when a simpler plan focused on what matters most to the patient may be better.