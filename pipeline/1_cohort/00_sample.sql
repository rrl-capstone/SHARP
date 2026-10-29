-- 00: Pick the people for this run.
-- The profile (python -m runner --profile ...) picks who: sample_1pct and sample_30pct keep the
-- people whose MD5 of the ID starts below '03' or '4d'; full keeps everyone. MD5 picks the same
-- people every time, so results are repeatable, and the 1% sample is inside the 30% one.
-- Output: ${work_schema}.study_ids${sfx} (one row per person)

DROP TABLE IF EXISTS ${work_schema}.study_ids${sfx};

CREATE TABLE ${work_schema}.study_ids${sfx} AS
SELECT patient_id
FROM ${komodo_schema}.patient_demographics
WHERE ${sample_filter}   -- e.g. MD5(CAST(patient_id AS VARCHAR)) < '03' for the 1% sample; TRUE for full
;

-- check
-- result: study_people
SELECT COUNT(*) AS people FROM ${work_schema}.study_ids${sfx};
