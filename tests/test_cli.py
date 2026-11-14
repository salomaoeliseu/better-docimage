"""Validação antecipada da CLI: argumentos falham antes de qualquer I/O."""

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


def _run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "better_docimage", *args],
        cwd=goldenlib.ROOT,
        capture_output=True,
        text=True,
    )


def _assert_usage_error(result: subprocess.CompletedProcess[str], fragment: str) -> None:
    assert result.returncode == 2
    assert fragment in result.stderr
    assert "Traceback" not in result.stderr


def test_unknown_mode_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--modes", "color,nope")

    _assert_usage_error(result, "inválido")
    assert not missing.exists()


def test_empty_modes_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--modes", "")

    _assert_usage_error(result, "pelo menos um modo")
    assert not missing.exists()


def test_duplicate_modes_are_processed_once(tmp_path: Path):
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
    assert result.stdout.count("ok ->") == 1
    assert (tmp_path / "saida_gray.png").is_file()
    assert not (tmp_path / "saida_color.png").exists()


def test_corners_with_wrong_arity_exit_2_without_traceback(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--corners", "1,2,3")

    _assert_usage_error(result, "8 valores")
    assert not missing.exists()


def test_non_numeric_corners_exit_2_without_traceback(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--corners", "a,b,c,d,e,f,g,h")

    _assert_usage_error(result, "números")
    assert not missing.exists()


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


def test_negative_sharpen_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--sharpen", "-1")

    _assert_usage_error(result, "sharpen")
    assert not missing.exists()


def test_zero_gamma_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--gamma", "0")

    _assert_usage_error(result, "gamma")
    assert not missing.exists()


def test_zero_width_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--width", "0")

    _assert_usage_error(result, "width")
    assert not missing.exists()


def test_negative_denoise_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--denoise", "-1")

    _assert_usage_error(result, "denoise")
    assert not missing.exists()


def test_non_finite_gamma_exits_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--gamma", "nan")

    _assert_usage_error(result, "finito")
    assert not missing.exists()


def test_non_finite_corners_exit_2_before_reading_the_image(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(
        str(missing),
        "--corners",
        "nan,0,1,0,1,1,0,1",
    )

    _assert_usage_error(result, "finitos")
    assert not missing.exists()


def test_missing_input_exits_1_without_traceback(tmp_path: Path):
    missing = tmp_path / "ausente.png"
    result = _run(str(missing), "--denoise", "0")

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert str(missing) in result.stderr


def test_module_entry_point_shows_help():
    result = _run_module("--help")

    assert result.returncode == 0
    assert "--modes" in result.stdout
    assert "Traceback" not in result.stderr


def test_module_and_wrapper_produce_identical_output(tmp_path: Path):
    source = _write_input(tmp_path)
    common = [str(source), "--modes", "gray", "--denoise", "0", "--width", "32"]

    wrapper = _run(*common, "-o", str(tmp_path / "wrapper"))
    module = _run_module(*common, "-o", str(tmp_path / "module"))

    assert wrapper.returncode == 0
    assert module.returncode == 0
    assert (tmp_path / "wrapper_gray.png").read_bytes() == (
        tmp_path / "module_gray.png"
    ).read_bytes()

