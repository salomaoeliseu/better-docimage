"""Gate estrutural da Fase 3: módulos pequenos e pacote enxuto."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

PACKAGE = Path(__file__).resolve().parents[1] / "better_docimage"
PLUMBING = {"__init__.py", "__main__.py"}
CODE_MODULES = (
    "settings.py",
    "io.py",
    "primitives.py",
    "detection.py",
    "quality.py",
    "pipeline.py",
    "cli.py",
)


def _statement_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(isinstance(node, ast.stmt) for node in ast.walk(tree))


def test_package_has_seven_code_modules():
    modules = sorted(
        path.name for path in PACKAGE.glob("*.py") if path.name not in PLUMBING
    )

    assert modules == sorted(CODE_MODULES)


def test_no_module_concentrates_more_than_thirty_percent():
    counts = {name: _statement_count(PACKAGE / name) for name in CODE_MODULES}
    total = sum(counts.values())
    offenders = {
        name: f"{count}/{total} ({count / total:.1%})"
        for name, count in counts.items()
        if count / total > 0.30
    }

    assert not offenders, f"módulos acima de 30% dos statements: {offenders}"
