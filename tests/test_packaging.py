"""Contratos da Fase 4: metadados, pins, entry point e documentação."""

from __future__ import annotations

import json
import subprocess
import sysconfig
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
MANIFEST = ROOT / "tests" / "golden" / "manifest.json"


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def _exact_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for requirement in _project()["dependencies"]:
        name, separator, version = requirement.partition("==")
        assert separator and version, f"dependência sem pin exato: {requirement}"
        pins[name] = version
    return pins


def _console_script() -> Path | None:
    scripts = Path(sysconfig.get_path("scripts"))
    for name in ("better-docimage", "better-docimage.exe"):
        candidate = scripts / name
        if candidate.is_file():
            return candidate
    return None


def test_runtime_pins_match_the_golden_environment():
    environment = json.loads(MANIFEST.read_text(encoding="utf-8"))["environment"]

    assert _exact_pins() == {
        "opencv-python": environment["opencv_python"],
        "numpy": environment["numpy"],
        "pillow": environment["pillow"],
    }


def test_dev_extra_pins_pytest():
    assert "pytest==9.2.0" in _project()["optional-dependencies"]["dev"]


def test_pyproject_declares_the_console_script():
    assert _project()["scripts"] == {
        "better-docimage": "better_docimage.cli:main",
    }


def test_requirements_files_were_replaced_by_pyproject():
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "requirements-dev.txt").exists()


def test_installed_console_script_shows_help():
    script = _console_script()
    if script is None:
        pytest.skip("pacote não instalado; rode python -m pip install -e '.[dev]'")

    result = subprocess.run(
        [str(script), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--modes" in result.stdout
    assert "Traceback" not in result.stderr


def test_readme_covers_installation_usage_tests_and_docs():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = (
        'pip install -e ".[dev]"',
        "better-docimage --help",
        "pytest -m fast",
        "pytest -m slow",
        "docs/adr/README.md",
        "docs/roadmap-refatoracao.md",
    )

    missing = [fragment for fragment in required if fragment not in text]
    assert not missing, f"README sem os trechos obrigatórios: {missing}"
