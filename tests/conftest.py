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
    return path


@pytest.fixture
def variables(local_file: Path) -> dict[str, str]:
    return config.sql_variables(config.load())
