-- Figure 1: How big is the dataset
-- One row: all patients, all providers, and patients aged 50+.
-- Aged 50+ = born in 1975 or earlier (50 or older by 2025).

SELECT
    (SELECT COUNT(DISTINCT patient_id)
     FROM komodo_202606.patient_demographics) AS total_patients,
    (SELECT COUNT(DISTINCT npi)
     FROM komodo_202606.providers) AS total_providers,
    (SELECT COUNT(DISTINCT patient_id)
     FROM komodo_202606.patient_demographics
     WHERE EXTRACT(YEAR FROM patient_dob) <= 1975) AS patients_50_plus;