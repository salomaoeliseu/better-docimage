"""Congela a CLI atual. A fase 1 troca estas expectativas pela validação antecipada."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import goldenlib

pytestmark = pytest.mark.fast


def _write_input(directory: Path) -> Path:
    path = directory / "entrada.png"
    Image.new("RGB", (32, 24), (180, 180, 180)).save(path)
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(goldenlib.SCRIPT), *args],
        cwd=goldenlib.ROOT,
        capture_output=True,
        text=True,
    )


def test_unknown_mode_exits_2(tmp_path: Path):
    source = _write_input(tmp_path)
    prefix = tmp_path / "saida"
    result = _run(
        str(source),
        "-o",
        str(prefix),
        "--modes",
        "color,nope",
        "--denoise",
        "0",
        "--width",
        "32",
    )
    assert result.returncode == 2
    assert "inválido" in result.stderr


def test_empty_modes_exits_0_without_writing_files(tmp_path: Path):
    source = _write_input(tmp_path)
    prefix = tmp_path / "saida"
    result = _run(
        str(source),
        "-o",
        str(prefix),
        "--modes",
        "",
        "--denoise",
        "0",
        "--width",
        "32",
    )
    assert result.returncode == 0
    assert list(tmp_path.glob("saida_*.png")) == []


def test_duplicate_modes_are_processed_twice(tmp_path: Path):
    source = _write_input(tmp_path)
    prefix = tmp_path / "saida"
    result = _run(
        str(source),
        "-o",
        str(prefix),
        "--modes",
        "gray,gray",
        "--denoise",
        "0",
        "--width",
        "32",
    )
    assert result.returncode == 0
    assert result.stdout.count("ok ->") == 2
    assert (tmp_path / "saida_gray.png").is_file()
    assert not (tmp_path / "saida_color.png").exists()


def test_corners_with_wrong_arity_exit_1_with_traceback(tmp_path: Path):
    source = _write_input(tmp_path)
    result = _run(
        str(source),
        "--corners",
        "1,2,3",
        "--denoise",
        "0",
        "--width",
        "32",
    )
    assert result.returncode == 1
    assert "Traceback" in result.stderr
    assert "8 valores" in result.stderr


def test_non_numeric_corners_exit_1_with_traceback(tmp_path: Path):
    source = _write_input(tmp_path)
    result = _run(
        str(source),
        "--corners",
        "a,b,c,d,e,f,g,h",
        "--denoise",
        "0",
        "--width",
        "32",
    )
    assert result.returncode == 1
    assert "Traceback" in result.stderr
    assert "números" in result.stderr


def test_pdf_flag_adds_pdf_without_changing_the_png(tmp_path: Path):
    source = _write_input(tmp_path)
    with_pdf = tmp_path / "com_pdf"
    without_pdf = tmp_path / "sem_pdf"
    common = [
        str(source),
        "--modes",
        "color",
        "--denoise",
        "0",
        "--width",
        "32",
    ]

    result_with_pdf = _run(*common, "-o", str(with_pdf), "--pdf")
    result_without_pdf = _run(*common, "-o", str(without_pdf))

    assert result_with_pdf.returncode == 0
    assert result_without_pdf.returncode == 0
    png_with_pdf = tmp_path / "com_pdf_color.png"
    png_without_pdf = tmp_path / "sem_pdf_color.png"
    assert png_with_pdf.read_bytes() == png_without_pdf.read_bytes()
    assert (tmp_path / "com_pdf_color.pdf").is_file()
    assert not (tmp_path / "sem_pdf_color.pdf").exists()


def test_negative_sharpen_is_accepted(tmp_path: Path):
    source = _write_input(tmp_path)
    prefix = tmp_path / "saida"
    result = _run(
        str(source),
        "-o",
        str(prefix),
        "--sharpen",
        "-1",
        "--denoise",
        "0",
        "--width",
        "32",
    )
    assert result.returncode == 0
    assert (tmp_path / "saida_color.png").is_file()


def test_zero_gamma_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--gamma", "0")
    assert result.returncode == 2
    assert "gamma" in result.stderr
    assert "Traceback" not in result.stderr
    assert not missing.exists()
