from __future__ import annotations

from pathlib import Path

import pytest

from runner import config


@pytest.fixture
def local_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A config/local.yml stand-in, so tests never need anyone's real settings."""
    path = tmp_path / "local.yml"
    path.write_text("redshift_user: test_user\njdbc_driver_folder: C:/drivers\n", encoding="utf-8")
    monkeypatch.setattr(config, "LOCAL_FILE", path)
    monkeypatch.setattr(config, "EXPLORER_FILE", tmp_path / "explorer.yml")   # absent: Redshift
    return path


# A made-up Komodo snapshot: 150 people (P000-P029 have HIV), every year 2011-2025, column names in
# upper case as in the real parquet files. Nothing here comes from Komodo.
_PEOPLE = "SELECT i, 'P' || lpad(i::VARCHAR, 3, '0') AS id FROM range(150) t(i)"
_YEARS = "SELECT y FROM range(2011, 2026) t(y)"
SYNTHETIC_KOMODO = {
    "patient_demographics": f"""SELECT id AS PATIENT_ID, make_date(1950 + i % 3, 6, 15) AS PATIENT_DOB,
        CASE WHEN i = 148 THEN 'U' WHEN i % 2 = 0 THEN 'M' ELSE 'F' END AS PATIENT_GENDER FROM ({_PEOPLE})""",
    "patient_mortality": f"SELECT id AS PATIENT_ID, DATE '2018-05-01' AS PATIENT_DEATH_DATE FROM ({_PEOPLE}) WHERE i = 149",
    "patient_closed": f"""SELECT id AS PATIENT_ID, closed_type AS CLOSED_TYPE, DATE '2010-01-01' AS CLOSED_START_DATE,
        DATE '2030-12-31' AS CLOSED_END_DATE FROM ({_PEOPLE}), (VALUES ('MX CLOSED'), ('RX CLOSED')) c(closed_type)""",
    "patient_insurance": f"""SELECT id AS PATIENT_ID, DATE '2010-01-01' AS ROW_VALID_START, DATE '2030-12-31' AS ROW_VALID_END,
        'MX1' AS MX_PAYER_ID, 'RX1' AS RX_PAYER_ID FROM ({_PEOPLE})""",
    "patient_geography": f"""SELECT id AS PATIENT_ID, ['MA', 'OH', 'TX', 'CA'][(i // 2) % 4 + 1] AS PATIENT_STATE,
        DATE '2010-01-01' AS VALID_FROM_DATE, NULL::DATE AS VALID_TO_DATE FROM ({_PEOPLE})""",
    "patient_race_ethnicity": f"""SELECT id AS PATIENT_ID,
        ['WHITE', 'BLACK', 'HISPANIC', 'ASIAN'][i % 4 + 1] AS PATIENT_RACE_ETHNICITY FROM ({_PEOPLE})""",
    "inpatient_events": f"""SELECT id AS PATIENT_ID, 'S' || id AS UTILIZATION_ID, 'V' || id AS VISIT_ID,
        CASE WHEN i < 30 THEN DATE '2017-04-01' ELSE DATE '2019-04-01' END AS ADMIT_DATE,
        CASE WHEN i < 30 THEN DATE '2017-04-05' ELSE DATE '2019-04-03' END AS DISCHARGE_DATE,
        CASE WHEN i < 30 THEN '977' ELSE '291' END AS DRG_CODE,
        CASE WHEN i < 30 THEN 'R509' ELSE 'I500' END AS ADMISSION_DIAGNOSIS_CODE,
        CASE WHEN i < 30 THEN 'B20' ELSE 'I500' END AS PRIMARY_DIAGNOSIS_CODE,
        CASE WHEN i < 30 THEN '["I500","N184"]' END AS SECONDARY_DIAGNOSIS_CODES
        FROM ({_PEOPLE}) WHERE i % 3 = 0""",
    "non_inpatient_events": f"""SELECT id AS PATIENT_ID, 'U' || id || '-' || y || '-' || m AS UTILIZATION_ID,
        'V' || id || '-' || y || '-' || m AS VISIT_ID, line AS LINE_NUMBER, make_date(y, m, 1) AS SERVICE_DATE,
        CASE WHEN line = 1 THEN '3470F' ELSE '99213' END AS PROCEDURE_CODE,
        CASE WHEN line = 2 THEN NULL WHEN i < 30 THEN '["B20"]' ELSE '["Z0000"]' END AS PRIMARY_DIAGNOSIS_CODE_ARRAY,
        CASE WHEN line = 2 THEN '[]' WHEN i < 30 THEN '["I10","E119","N184"]' ELSE '["I10","E119"]' END AS DIAGNOSIS_CODES
        FROM ({_PEOPLE}), ({_YEARS}), (VALUES (3), (9)) d(m), (VALUES (1), (2)) l(line)""",
    "pharmacy_events": f"""SELECT id AS PATIENT_ID, make_date(y, m, 1) AS FILL_DATE, generic AS GENERIC_NAME,
        brand AS BRAND_NAME, CASE WHEN m = 6 THEN 'REVERSED' ELSE 'FINAL' END AS TRANSACTION_STATUS,
        'PAID' AS TRANSACTION_RESULT
        FROM ({_PEOPLE}), ({_YEARS}), (VALUES (2), (3), (6)) d(m),
             (VALUES ('BICTEGRAVIR/EMTRICITABINE/TENOFOVIR ALAFENAMIDE', 'BIKTARVY', TRUE),
                     ('LISINOPRIL', 'ZESTRIL', FALSE)) r(generic, brand, hiv_drug)
        WHERE (i < 30 AND y >= 2016) OR NOT hiv_drug""",
}


@pytest.fixture
def komodo_root(tmp_path: Path) -> Path:
    """SYNTHETIC_KOMODO written as <root>/202606/<table>/part0.parquet."""
    duckdb = pytest.importorskip("duckdb")
    root = tmp_path / "komodo"
    with duckdb.connect() as conn:
        for table, select in SYNTHETIC_KOMODO.items():
            folder = root / "202606" / table
            folder.mkdir(parents=True)
            conn.execute(f"COPY ({select}) TO '{(folder / 'part0.parquet').as_posix()}' (FORMAT parquet)")
    return root


@pytest.fixture
def explorer_file(local_file: Path) -> Path:
    """A config/explorer.yml stand-in (DuckDB backend) made from the committed example, with no
    local.yml next to it."""
    local_file.unlink()
    path = config.EXPLORER_FILE
    path.write_text((config.REPO_ROOT / "config" / "explorer.example.yml").read_text(encoding="utf-8"),
                    encoding="utf-8")
    return path


@pytest.fixture
def variables(local_file: Path) -> dict[str, str]:
    return config.sql_variables(config.load())


@pytest.fixture
def synthetic_explorer(explorer_file: Path, komodo_root: Path, tmp_path: Path) -> Path:
    """config/explorer.yml pointing at the made-up snapshot, with extracts in tmp_path."""
    explorer_file.write_text(f"backend: duckdb\nkomodo_root: {komodo_root.as_posix()}\nsnapshot: '202606'\n"
                             f"extracts_dir: {(tmp_path / 'extracts').as_posix()}\nduckdb:\n  threads: 2\n",
                             encoding="utf-8")
    return explorer_file
