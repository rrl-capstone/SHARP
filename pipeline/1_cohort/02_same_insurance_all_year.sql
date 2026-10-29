-- 02: Exclude person-years not enrolled in the same insurance (medical AND pharmacy)
-- for the entire year, including payer switchers.

-- A person-year passes only if both are true:
--   Part 1: medical and pharmacy closed records from Jan 1 to Dec 31
--           (patient_closed: MX CLOSED = medical, RX CLOSED = pharmacy), and
--   Part 2: only one medical payer and one pharmacy payer all year, with no gaps
--           (Komodo has no plan ID, so "same plan" is checked at the payer level).
-- (For people with HIV, File 07 also checks they stayed closed from the HIV date onward.)

-- Input: age50_alive (File 01)
-- Output: ${work_schema}.same_insurance${sfx} (one row per person-year that passes)

DROP TABLE IF EXISTS ${work_schema}.same_insurance${sfx};

CREATE TABLE ${work_schema}.same_insurance${sfx} AS
-- Part 1: closed all year
SELECT py.patient_id, py.yr
FROM ${work_schema}.age50_alive${sfx} py
JOIN ${komodo_schema}.patient_closed c ON c.patient_id = py.patient_id
WHERE c.closed_start_date <= py.year_start
  AND c.closed_end_date   >= py.year_end
GROUP BY py.patient_id, py.yr
HAVING MAX(CASE WHEN c.closed_type = 'MX CLOSED' THEN 1 ELSE 0 END) = 1
   AND MAX(CASE WHEN c.closed_type = 'RX CLOSED' THEN 1 ELSE 0 END) = 1
INTERSECT   -- keep only person-years that pass both parts
-- Part 2: same payer all year
SELECT py.patient_id, py.yr
FROM ${work_schema}.age50_alive${sfx} py
JOIN ${komodo_schema}.patient_insurance i ON i.patient_id = py.patient_id
WHERE i.row_valid_start <= py.year_end
  AND i.row_valid_end   >= py.year_start
GROUP BY py.patient_id, py.yr
HAVING COUNT(DISTINCT i.mx_payer_id) = 1
   AND COUNT(DISTINCT i.rx_payer_id) = 1
   AND SUM(CASE WHEN i.mx_payer_id IS NULL OR i.rx_payer_id IS NULL THEN 1 ELSE 0 END) = 0;

-- check
-- result: same_insurance_by_year
SELECT yr, COUNT(*) AS people FROM ${work_schema}.same_insurance${sfx} GROUP BY yr ORDER BY yr;
