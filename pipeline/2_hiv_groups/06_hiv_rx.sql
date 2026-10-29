-- 06: People with 2 successive refills of HIV medications that identify HIV ("List 3").

-- HIV drugs: from HIVDrugAbbrev.xlsx (Supplement 6), listed in reference/hiv_drugs.csv.
-- A fill counts if either:
--   (1) its generic_name contains at least one ingredient marked identifies_hiv = yes, or
--   (2) its brand_name contains a brand marked identifies_hiv = yes.
-- Not used to identify HIV (identifies_hiv = no), because they are also given to people without
-- HIV; they are used later, when treatment regimens are studied:
--   lamivudine    also treats hepatitis B (protocol)
--   ritonavir     a booster, also in Paxlovid (COVID-19) and hepatitis C regimens (PI, Oct 2026)
--   tenofovir     hepatitis B on its own (Viread, Vemlidy), and PrEP with emtricitabine (PI, Oct 2026)
--   emtricitabine PrEP with tenofovir (Truvada, Descovy) (PI, Oct 2026)
--   cabotegravir  PrEP on its own (Apretude) (PI, Oct 2026)
--   lenacapavir   PrEP on its own (Yeztugo) (PI, Oct 2026)
-- As with lamivudine before, a product that ALSO contains an identifying ingredient still counts:
--   Biktarvy (bictegravir/emtricitabine/tenofovir) -> counted, via bictegravir
--   Kaletra (lopinavir/ritonavir)                  -> counted, via lopinavir
--   Truvada, Descovy, Viread, Vemlidy, Apretude, Paxlovid, Norvir -> not counted
-- So someone taking tenofovir as part of a treatment regimen is still found, through the other
-- drugs in the regimen.

-- Only final, paid claims are fills (config pharmacy: STANDALONE or FINAL, and PAID);
-- reversed and rejected claims were never dispensed.
-- A refill counts as successive if it is 1-90 days after the previous one
-- (confirmed by the professor: within 90 days).
-- Only looks at eligible people (File 03), and at their fills from any study year.

-- Speed-up (same rules as before, like the old File 03):
--   the big pharmacy table is read only ONCE, in Step 1.
--   Step 1 keeps every HIV drug fill (a much smaller table),
--   then Steps 2 and 3 work only on that small table.

-- Outputs:
--   ${work_schema}.hiv_rx_fills_all${sfx}  (Step 1: all identifying HIV drug fills in the study years, everyone)
--   ${work_schema}.hiv_rx_drug_names${sfx} (Step 2: the HIV drug names found; open it to check the list)
--   ${work_schema}.hiv_rx${sfx}            (Step 3: one row per person)


-- Step 1: read the pharmacy table once, keep only identifying HIV drug fills

DROP TABLE IF EXISTS ${work_schema}.hiv_rx_fills_all${sfx};

CREATE TABLE ${work_schema}.hiv_rx_fills_all${sfx} AS
SELECT patient_id, fill_date, generic_name, brand_name
FROM ${komodo_schema}.pharmacy_events
WHERE (
      -- (1) identifying HIV ingredients (reference/hiv_drugs.csv)
      generic_name ~* ${hiv_identifying_ingredients}
      -- (2) identifying HIV brand names (reference/hiv_drugs.csv)
   OR brand_name ~* ${hiv_identifying_brands}
      )
  -- final, paid claims only
  AND UPPER(transaction_status) IN (${pharmacy_final_status})
  AND UPPER(transaction_result) = ${pharmacy_paid_result}
  AND fill_date >= '${study_start}' AND fill_date < '${study_end}';


-- Step 2: the HIV drug names found (same list as before)

DROP TABLE IF EXISTS ${work_schema}.hiv_rx_drug_names${sfx};

CREATE TABLE ${work_schema}.hiv_rx_drug_names${sfx} AS
SELECT DISTINCT generic_name, brand_name
FROM ${work_schema}.hiv_rx_fills_all${sfx};

-- check: the HIV drug names found (short list, safe to look at)
-- result: hiv_drug_names
SELECT generic_name, brand_name FROM ${work_schema}.hiv_rx_drug_names${sfx} ORDER BY 1, 2;


-- Step 3: eligible people only, then look for successive refills

DROP TABLE IF EXISTS ${work_schema}.hiv_rx${sfx};

CREATE TABLE ${work_schema}.hiv_rx${sfx} AS
WITH fills AS (
    SELECT DISTINCT patient_id, fill_date
    FROM ${work_schema}.hiv_rx_fills_all${sfx}
    WHERE patient_id IN (SELECT patient_id FROM ${work_schema}.eligible_ids${sfx})   -- only eligible people (File 03)
),
pairs AS (
    SELECT patient_id, fill_date,
           LAG(fill_date) OVER (PARTITION BY patient_id ORDER BY fill_date) AS prev_fill_date
    FROM fills
)
SELECT patient_id,
       MIN(prev_fill_date) AS first_date,
       MAX(fill_date)      AS last_date
FROM pairs
WHERE fill_date - prev_fill_date BETWEEN 1 AND 90   -- change the gap here
GROUP BY patient_id;

-- check
-- result: hiv_rx_people
SELECT COUNT(*) AS people FROM ${work_schema}.hiv_rx${sfx};
