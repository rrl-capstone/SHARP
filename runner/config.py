"""Reads config/study.yml and config/local.yml, checks every value, and turns them into the
${variables} the SQL steps use. Every value that ends up inside SQL is validated here."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDY_FILE = REPO_ROOT / "config" / "study.yml"
LOCAL_FILE = REPO_ROOT / "config" / "local.yml"
REFERENCE_DIR = REPO_ROOT / "reference"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_UPPER_WORD = re.compile(r"^[A-Z_]+$")
_HOST = re.compile(r"^[A-Za-z0-9.-]+$")
_DX_PREFIX = re.compile(r"^[A-Z][0-9A-Z]{1,6}$")
_PROCEDURE_CODE = re.compile(r"^[0-9A-Z]{5}$")
_DRUG_PATTERN = re.compile(r"^[A-Z][A-Z0-9 -]*$")   # plain words: nothing a regular expression treats specially

# The three runs. The MD5 of the patient ID picks the same people every time, and the 1% sample
# is always inside the 30% one. Each profile has its own table names (suffix) and results folder,
# so all three can run at the same time in one work schema.
#   profile        people kept: first two hex digits of MD5 below   table suffix
PROFILES: dict[str, tuple[str | None, str]] = {
    "sample_1pct": ("03", "_s1"),     # 3/256, about 1.2%
    "sample_30pct": ("4d", "_s30"),   # 77/256, about 30.1%
    "full": (None, ""),               # everyone
}


class ConfigError(ValueError):
    """A setting or code list that cannot be used."""


@dataclass(frozen=True)
class Config:
    profile: str
    host: str
    port: int
    database: str
    redshift_user: str
    work_schema: str
    komodo_schema: str
    first_year: int
    last_year: int
    final_status: tuple[str, ...]
    paid_result: str
    min_inpatient_claims: int
    min_outpatient_claims: int
    match_ratio: int
    caliper_sd: float
    gagne_level_tops: tuple[int, ...]
    lookback_years: int
    jdbc_driver_folder: str
    rscript: str

    @property
    def run_name(self) -> str:
        return self.profile

    @property
    def table_suffix(self) -> str:
        return PROFILES[self.profile][1]

    @property
    def sample_filter(self) -> str:
        md5_below = PROFILES[self.profile][0]
        return f"MD5(CAST(patient_id AS VARCHAR)) < '{md5_below}'" if md5_below else "TRUE"

    @property
    def study_years(self) -> list[int]:
        return list(range(self.first_year, self.last_year + 1))

    @property
    def lookback_first_year(self) -> int:
        return self.first_year - self.lookback_years


def _get(data: dict, path: str):
    node = data
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(f"Missing setting {path!r}.")
        node = node[key]
    return node


def _int(data: dict, path: str, low: int, high: int) -> int:
    value = _get(data, path)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigError(f"{path} must be a whole number from {low} to {high}, not {value!r}.")
    return value


def _identifier(value, what: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.match(value):
        raise ConfigError(f"{what} must be lowercase letters, digits and _, not {value!r}.")
    return value


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        hint = " Copy config/local.example.yml to config/local.yml and fill it in." \
            if path.name == "local.yml" else ""
        raise ConfigError(f"{path.as_posix()} not found.{hint}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path.as_posix()} must be a list of settings.")
    return data


def load(study_file: Path | None = None, local_file: Path | None = None,
         profile: str | None = None) -> Config:
    """Paths default to config/study.yml and config/local.yml (read at call time, for tests).
    profile overrides run.profile in study.yml (python -m runner --profile ...)."""
    study, local = _read_yaml(study_file or STUDY_FILE), _read_yaml(local_file or LOCAL_FILE)

    chosen = profile or _get(study, "run.profile")
    if not isinstance(chosen, str) or chosen not in PROFILES:
        raise ConfigError(f"The profile must be one of {', '.join(PROFILES)}, not {chosen!r}.")
    host = _get(study, "redshift.host")
    if not isinstance(host, str) or not _HOST.match(host):
        raise ConfigError(f"redshift.host is not a host name: {host!r}.")
    user = _identifier(_get(local, "redshift_user"), "redshift_user in config/local.yml")
    work_schema = _identifier(local.get("work_schema") or f"work_{user}", "work_schema")

    first = _int(study, "study_years.first", 2016, 2100)
    last = _int(study, "study_years.last", first, 2100)
    final_status = _get(study, "pharmacy.final_status")
    if not isinstance(final_status, list) or not final_status or \
            not all(isinstance(s, str) and _UPPER_WORD.match(s) for s in final_status):
        raise ConfigError("pharmacy.final_status must be a list of capitalised words, e.g. [FINAL].")
    paid = _get(study, "pharmacy.paid_result")
    if not isinstance(paid, str) or not _UPPER_WORD.match(paid):
        raise ConfigError("pharmacy.paid_result must be a capitalised word, e.g. PAID.")

    caliper = _get(study, "matching.caliper_sd")
    if isinstance(caliper, bool) or not isinstance(caliper, (int, float)) or not 0 < caliper <= 5:
        raise ConfigError(f"matching.caliper_sd must be a number above 0, not {caliper!r}.")
    tops = _get(study, "gagne.level_tops")
    if not isinstance(tops, list) or not tops or \
            not all(isinstance(t, int) and not isinstance(t, bool) for t in tops) or tops != sorted(set(tops)):
        raise ConfigError("gagne.level_tops must be whole numbers in increasing order, e.g. [0, 2, 4].")

    jdbc = local.get("jdbc_driver_folder") or ""
    rscript = local.get("rscript") or "Rscript"
    if not isinstance(jdbc, str) or not isinstance(rscript, str):
        raise ConfigError("jdbc_driver_folder and rscript in config/local.yml must be text.")

    return Config(
        profile=chosen,
        host=host,
        port=_int(study, "redshift.port", 1, 65535),
        database=_identifier(_get(study, "redshift.database"), "redshift.database"),
        redshift_user=user,
        work_schema=work_schema,
        komodo_schema=_identifier(_get(study, "komodo_schema"), "komodo_schema"),
        first_year=first,
        last_year=last,
        final_status=tuple(final_status),
        paid_result=paid,
        min_inpatient_claims=_int(study, "conditions.min_inpatient_claims", 1, 100),
        min_outpatient_claims=_int(study, "conditions.min_outpatient_claims", 1, 100),
        match_ratio=_int(study, "matching.ratio", 1, 20),
        caliper_sd=float(caliper),
        gagne_level_tops=tuple(tops),
        lookback_years=_int(study, "measures.lookback_years", 0, 10),
        jdbc_driver_folder=jdbc,
        rscript=rscript,
    )


def sql_quote(value: str) -> str:
    """A text value as a SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def read_reference(name: str) -> list[dict[str, str]]:
    """Rows of reference/<name>, with blank and #comment rows skipped."""
    path = REFERENCE_DIR / name
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]
    return [r for r in rows if any(r.values()) and not next(iter(r.values())).startswith("#")]


def condition_roots() -> list[str]:
    """First three characters of every diagnosis prefix in reference/conditions.csv: the cheap
    filter inside the big diagnosis scan (exact prefixes are applied later, on distinct codes)."""
    roots = set()
    for row in read_reference("conditions.csv"):
        for prefix in row["prefixes"].split():
            if not _DX_PREFIX.match(prefix):
                raise ConfigError(f"conditions.csv: {prefix!r} is not an ICD-10-CM prefix without dots.")
            roots.add(prefix[:3])
    return sorted(roots)


def procedure_codes() -> list[str]:
    """Every CPT/HCPCS code in reference/procedure_codes.csv: the literal filter inside the
    procedure scan."""
    codes = set()
    for row in read_reference("procedure_codes.csv"):
        for code in row["codes"].split():
            if not _PROCEDURE_CODE.match(code):
                raise ConfigError(f"procedure_codes.csv: {code!r} is not a 5-character CPT or HCPCS code.")
            codes.add(code)
    return sorted(codes)


def drug_patterns_regex() -> str:
    """Every word in reference/drug_patterns.csv as one case-insensitive alternation, e.g.
    'OMEPRAZOLE|LISINOPRIL|...': the filter inside the pharmacy scan, so only fills that can
    match a drug concept leave Spectrum (concepts are assigned later, on distinct names)."""
    words = set()
    for row in read_reference("drug_patterns.csv"):
        for word in row["patterns"].split():
            if not _DRUG_PATTERN.match(word):
                raise ConfigError(f"drug_patterns.csv: {word!r} must be capital letters, digits, spaces or -.")
            words.add(word)
    if not words:
        raise ConfigError("drug_patterns.csv has no drug names.")
    return "|".join(sorted(words))


_HIV_DRUG = re.compile(r"^[a-z][a-z0-9 ]*$")   # plain words: nothing a regular expression treats specially
_STATE = re.compile(r"^[A-Z]{2}$")
_REGION = re.compile(r"^[A-Z][a-z]+$")


def hiv_identifying_regex(drug_type: str) -> str:
    """The ingredients or brands in reference/hiv_drugs.csv with identifies_hiv = yes, as one
    case-insensitive alternation for File 06. Drugs marked no (lamivudine, ritonavir, the PrEP
    and hepatitis B drugs) never identify HIV on their own; a product that also contains an
    identifying ingredient still counts."""
    names = []
    for row in read_reference("hiv_drugs.csv"):
        if row["type"] not in ("ingredient", "brand") or row["identifies_hiv"] not in ("yes", "no"):
            raise ConfigError(f"hiv_drugs.csv: {row['name']!r} needs type ingredient/brand and identifies_hiv yes/no.")
        if not _HIV_DRUG.match(row["name"]):
            raise ConfigError(f"hiv_drugs.csv: {row['name']!r} must be lowercase letters, digits and spaces.")
        if row["identifies_hiv"] == "no" and not row["why_not"]:
            raise ConfigError(f"hiv_drugs.csv: say why {row['name']!r} does not identify HIV.")
        if row["type"] == drug_type and row["identifies_hiv"] == "yes":
            names.append(row["name"])
    if not names:
        raise ConfigError(f"hiv_drugs.csv has no identifying {drug_type}s.")
    return "|".join(sorted(names))


def census_region_sql(column: str) -> str:
    """CASE expression giving the census region (Northeast, Midwest, South, West) of a two-letter
    state code, from reference/census_regions.csv. Anything else (territories, unknown codes) is
    'Other', so nobody drops out of matching for a missing region."""
    by_region: dict[str, list[str]] = {}
    for row in read_reference("census_regions.csv"):
        if not _STATE.match(row["state"]) or not _REGION.match(row["census_region"]):
            raise ConfigError(f"census_regions.csv: bad row {row}.")
        by_region.setdefault(row["census_region"], []).append(row["state"])
    whens = " ".join(f"WHEN {column} IN ({', '.join(sql_quote(s) for s in states)}) THEN '{region}'"
                     for region, states in by_region.items())
    return f"(CASE {whens} ELSE 'Other' END)::VARCHAR(20)"


def gagne_level_sql(tops: tuple[int, ...], column: str) -> str:
    """CASE expression that names each Gagne level, e.g. tops (0, 2, 4) ->
    '0 or less', '1-2', '3-4', '5+'."""
    parts, low = [], None
    for top in tops:
        label = f"{top} or less" if low is None else (str(top) if low == top else f"{low}-{top}")
        parts.append(f"WHEN {column} <= {top} THEN '{label}'")
        low = top + 1
    return "CASE " + " ".join(parts) + f" ELSE '{low}+' END"


def sql_variables(cfg: Config) -> dict[str, str]:
    """Every ${name} the SQL steps may use. Per-year statements also get ${year} and ${next_year}."""
    years = cfg.study_years
    return {
        "work_schema": cfg.work_schema,
        "komodo_schema": cfg.komodo_schema,
        "sfx": cfg.table_suffix,
        "sample_filter": cfg.sample_filter,
        "first_year": str(cfg.first_year),
        "last_year": str(cfg.last_year),
        "study_start": f"{cfg.first_year}-01-01",
        "study_end": f"{cfg.last_year + 1}-01-01",
        "study_years_select": " UNION ALL ".join(
            f"SELECT {years[0]} AS yr" if i == 0 else f"SELECT {y}" for i, y in enumerate(years)),
        "lookback_start": f"{cfg.lookback_first_year}-01-01",
        "pharmacy_final_status": ", ".join(sql_quote(s) for s in cfg.final_status),
        "pharmacy_paid_result": sql_quote(cfg.paid_result),
        "min_inpatient_claims": str(cfg.min_inpatient_claims),
        "min_outpatient_claims": str(cfg.min_outpatient_claims),
        "condition_roots": ", ".join(sql_quote(r) for r in condition_roots()),
        "procedure_codes": ", ".join(sql_quote(c) for c in procedure_codes()),
        "drug_patterns_regex": sql_quote(drug_patterns_regex()),
        "hiv_identifying_ingredients": sql_quote(hiv_identifying_regex("ingredient")),
        "hiv_identifying_brands": sql_quote(hiv_identifying_regex("brand")),
        "census_region": census_region_sql("patient_state"),
        "gagne_level": gagne_level_sql(cfg.gagne_level_tops, "g.gagne_score_excl_hiv"),
    }
