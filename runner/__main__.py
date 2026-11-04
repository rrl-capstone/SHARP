"""Runs the pipeline:  python -m runner [--check | --dry-run] [--from STEP | --only STEP]

  python -m runner --profile full   run for everyone (also: sample_1pct, sample_30pct)
  python -m runner --check          test the connection (or, on Explorer, the files) and your settings
  python -m runner --dry-run        write every rendered statement to build/rendered/, no database
  python -m runner                  run everything for the profile in config/study.yml (run.profile)
  python -m runner --from 4_matching  resume from a stage or step after a failure
  python -m runner --only 07_pwh_cohort.sql   run one stage or step

Each profile has its own tables (suffix _s1, _s30, none) and results folder, so the three can
run at the same time in separate terminals.
Results (aggregates only, counts 1 to 10 hidden) go to results/<profile>/<stage>/, with
run_info.json recording when, from which commit, and with which settings.
After each step the row count of every table it built goes to build/parity/<profile>.json (not
committed), so a Redshift run and an Explorer run can be compared exactly, table by table.
The backend (Redshift or DuckDB) comes from your personal settings file (runner/config.py).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from runner import config, db, dialect, duckdb_backend, results, sql, steps

log = logging.getLogger("runner")
BUILD_DIR = config.REPO_ROOT / "build"


class CheckFailed(RuntimeError):
    """A '-- expect:' check did not hold."""


def _check(df: pd.DataFrame, expect: tuple[str, str], where: str) -> None:
    left, right = expect
    if left not in df.columns or not (right.isdigit() or right in df.columns):
        raise CheckFailed(f"{where}: '-- expect: {left} = {right}' names a column the query does not return.")
    wanted = int(right) if right.isdigit() else df[right]
    bad = df[df[left] != wanted]
    if not bad.empty:
        raise CheckFailed(f"{where}: expected {left} = {right}, but got\n{bad.to_string(index=False)}")


def _year_range(cfg: config.Config, which: str | None) -> list[int | None]:
    if which is None:
        return [None]
    first = cfg.first_year if which == "study" else cfg.lookback_first_year
    return list(range(first, cfg.last_year + 1))


def _rendered(statement: sql.Statement, variables: dict[str, str], year: int | None, where: str) -> str:
    extra = {} if year is None else {"year": str(year), "next_year": str(year + 1)}
    return sql.render(statement.text, {**variables, **extra}, where)


def _run_sql_step(conn: db.Connection, cfg: config.Config, step: steps.Step,
                  variables: dict[str, str], results_dir: Path) -> None:
    for statement in steps.statements(step, variables):
        for year in _year_range(cfg, statement.for_each_year):
            label = step.path + (f" {year}" if year else "")
            text = _rendered(statement, variables, year, step.path)
            if not statement.is_query:
                db.execute(conn, text, label)
                continue
            df = db.query(conn, text, label)
            if statement.expect:
                _check(df, statement.expect, f"{step.path} {statement.result_name}")
            assert statement.result_name is not None
            saved = results.save(df, results_dir / step.stage / f"{statement.result_name}.csv")
            log.info("%s\n%s", statement.result_name, saved.head(25).to_string(index=False))


def _child_env(cfg: config.Config, secret: str, results_dir: Path) -> dict[str, str]:
    """Settings for Rhea's Gagne scripts, passed in their environment only (never as
    command-line arguments, which other processes can read). On DuckDB they open the profile's
    file with the runner's settings and translate their SQL with runner/dialect.py (PYTHONPATH)."""
    duck = {} if cfg.backend != "duckdb" else {
        "SHARP_BACKEND": "duckdb",
        "SHARP_DUCKDB_FILE": cfg.duckdb_file,
        "SHARP_DUCKDB_SETTINGS": json.dumps(duckdb_backend.resource_settings(cfg)),
        "PYTHONPATH": os.pathsep.join(p for p in (str(config.REPO_ROOT), os.environ.get("PYTHONPATH")) if p),
    }
    return {
        **os.environ,
        **duck,
        "REDSHIFT_HOST": cfg.host,
        "REDSHIFT_PORT": str(cfg.port),
        "REDSHIFT_DATABASE": cfg.database,
        "REDSHIFT_USER": cfg.redshift_user,
        "REDSHIFT_PASSWORD": secret,
        "SHARP_WORK_SCHEMA": cfg.work_schema,
        "SHARP_TABLE_SUFFIX": cfg.table_suffix,
        "SHARP_SAMPLE_FILTER": cfg.sample_filter,
        "SHARP_KOMODO_SCHEMA": cfg.komodo_schema,
        "SHARP_FIRST_YEAR": str(cfg.first_year),
        "SHARP_LAST_YEAR": str(cfg.last_year),
        "SHARP_MATCH_RATIO": str(cfg.match_ratio),
        "SHARP_GAGNE_PLOTS_DIR": str(results_dir / "5_gagne" / "plots"),
    }


def _run_script(cfg: config.Config, step: steps.Step, secret: str, results_dir: Path) -> None:
    subprocess.run([sys.executable, str(step.file)], cwd=step.file.parent,
                   env=_child_env(cfg, secret, results_dir), check=True)


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=config.REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_run_info(path: Path, cfg: config.Config, chosen: list[steps.Step], started: datetime,
                    status: str) -> None:
    study = config.STUDY_FILE.read_text(encoding="utf-8")
    info = {
        "run": cfg.run_name,
        "status": status,
        "backend": cfg.backend,
        "komodo_schema": cfg.komodo_schema,
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_uncommitted_changes": _git("status", "--porcelain") not in ("", "unknown"),
        "steps": [s.path for s in chosen],
        "config_study_yml": study,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, indent=2), encoding="utf-8")


def _record_parity(conn: db.Connection, cfg: config.Config, step: steps.Step, variables: dict[str, str]) -> None:
    """Row counts of the tables the step built, in build/parity/<profile>.json: counts only, never
    rows, and not rounded like results/, so two backends' runs can be compared exactly. Kept
    across resumed runs; sorted, so `diff` of two files shows only the counts that differ."""
    counts = {name: int(db.query(conn, f"SELECT COUNT(*) AS n FROM {cfg.work_schema}.{name}",
                                 f"parity {name}")["n"].iloc[0])
              for name in steps.created_tables(step, variables)}   # names come from the step files
    if not counts:
        return
    path = BUILD_DIR / "parity" / f"{cfg.profile}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        log.warning("%s was not valid JSON; starting it again", path.as_posix())
        data = {}
    data.update({"profile": cfg.profile, "backend": cfg.backend, "komodo_schema": cfg.komodo_schema})
    data.setdefault("row_counts", {})[step.path] = counts
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dry_run(cfg: config.Config, chosen: list[steps.Step], variables: dict[str, str]) -> None:
    out_dir = BUILD_DIR / "rendered"
    for step in chosen:
        target = out_dir / (step.path + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        if step.kind in ("python", "python_script"):
            target.write_text(f"{step.kind}: {step.path} runs Python (no SQL file to render)\n", encoding="utf-8")
            continue
        parts = []
        for statement in steps.statements(step, variables):
            for year in _year_range(cfg, statement.for_each_year):
                text = _rendered(statement, variables, year, step.path)
                parts.append((dialect.to_duckdb(text) if cfg.backend == "duckdb" else text) + "\n;")
        target.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    log.info("rendered %d steps to %s", len(chosen), out_dir.as_posix())


def _check_duckdb(cfg: config.Config) -> int:
    """--check on Explorer: files, folders and column types only (runner/duckdb_backend.check)."""
    import duckdb

    problems = duckdb_backend.check(cfg)
    for problem in problems:
        log.error("check: %s", problem)
    if problems:
        return 1
    log.info("Ready: DuckDB %s; Komodo %s/%s read as %s; profile %s; tables go to %s (schema %s, suffix %r); "
             "results to results/%s.", duckdb.__version__, cfg.komodo_root, cfg.snapshot, cfg.komodo_schema,
             cfg.profile, cfg.duckdb_file, cfg.work_schema, cfg.table_suffix, cfg.run_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runner", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="test the connection and settings")
    mode.add_argument("--dry-run", action="store_true", help="render the SQL to build/rendered/")
    parser.add_argument("--profile", choices=list(config.PROFILES),
                        help="which people to run on (default: run.profile in config/study.yml)")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--from", dest="start", help="run from this stage or step on")
    where.add_argument("--only", help="run only this stage or step")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    try:
        cfg = config.load(profile=args.profile)
        variables = config.sql_variables(cfg)
        chosen = steps.select(args.start, args.only)
        if args.dry_run:
            _dry_run(cfg, chosen, variables)
            return 0
        if args.check and cfg.backend == "duckdb":
            return _check_duckdb(cfg)
        driver_errors = db.errors(cfg)
    except (config.ConfigError, sql.StepError, dialect.DialectError) as error:
        log.error("%s", error)
        return 1
    secret = db.password() if cfg.backend == "redshift" else ""
    try:
        conn: db.Connection | None = db.connect(cfg, secret)
    except driver_errors as error:
        if cfg.backend == "duckdb":
            log.error("Could not open %s (is another run of %s using it?): %s", cfg.duckdb_file, cfg.profile, error)
        else:
            log.error("Could not connect to Redshift as %s: %s", cfg.redshift_user, error)
        return 1

    results_dir = results.RESULTS_DIR / cfg.run_name
    started, current = datetime.now(timezone.utc), None
    try:
        if args.check:
            # identifiers below were validated by config.load()
            db.query(conn, f"SELECT 1 AS ok FROM {cfg.komodo_schema}.patient_demographics LIMIT 1", "check")
            can_write = db.query(conn, f"SELECT HAS_SCHEMA_PRIVILEGE('{cfg.work_schema}', 'CREATE') AS ok",
                                 "check")["ok"].iloc[0]
            if not can_write:
                log.error("Connected, but you cannot create tables in %s.", cfg.work_schema)
                return 1
            log.info("Connected as %s; profile %s; tables go to %s (suffix %r); results to %s.",
                     cfg.redshift_user, cfg.profile, cfg.work_schema, cfg.table_suffix,
                     results_dir.relative_to(config.REPO_ROOT).as_posix())
            return 0
        log.info("Run %s: %d steps, tables in %s with suffix %r", cfg.run_name, len(chosen),
                 cfg.work_schema, cfg.table_suffix)
        for current in chosen:
            log.info("START %s", current.path)
            if current.kind in ("sql", "sql_from_python"):
                _run_sql_step(conn, cfg, current, variables, results_dir)
            elif current.kind == "python":
                steps.load_module(current).run(conn, cfg, variables, results_dir / current.stage)
            else:
                # The script opens its own connection. DuckDB allows one writer per file, so close
                # ours until it finishes; reconnecting reuses the password already given.
                conn.close()
                conn = None
                _run_script(cfg, current, secret, results_dir)
                conn = db.connect(cfg, secret)
            _record_parity(conn, cfg, current, variables)
            log.info("DONE  %s", current.path)
        _write_run_info(results_dir / "run_info.json", cfg, chosen, started, "complete")
        return 0
    except (config.ConfigError, sql.StepError, dialect.DialectError, CheckFailed, results.UnsafeResultError,
            subprocess.CalledProcessError, OSError, *driver_errors) as error:
        failed = current.path if current else "start"
        log.error("FAILED at %s: %s", failed, error)
        log.error("Fix it, then resume with:  python -m runner --profile %s --from %s", cfg.profile, failed)
        _write_run_info(results_dir / "run_info.json", cfg, chosen, started, f"failed at {failed}")
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())