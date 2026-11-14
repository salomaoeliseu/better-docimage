"""Contratos explícitos da Fase 1 e semântica de I/O."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import better_docimage as bdi
import better_docimage.pipeline as pipeline

pytestmark = pytest.mark.fast


def _settings(**overrides) -> bdi.Settings:
    values = {"target_width": 24, "denoise_strength": 0.0}
    values.update(overrides)
    return bdi.Settings(**values)


def _neutral_plan(width: int = 30, height: int = 20) -> bdi.TransformPlan:
    return bdi.TransformPlan(np.eye(3), bdi.Size(width, height))


def test_output_mode_is_the_single_vocabulary_source():
    assert bdi.OutputMode.values() == ("color", "gray", "bw")
    assert bdi.OutputMode.COLOR.is_binary is False
    assert bdi.OutputMode.GRAY.is_binary is False
    assert bdi.OutputMode.BW.is_binary is True


def test_size_and_offset_are_named_values():
    assert bdi.Size(10, 20) == bdi.Size(width=10, height=20)
    assert bdi.Offset(3, 4) == bdi.Offset(x=3, y=4)
    with pytest.raises(ValueError):
        bdi.Size(0, 20)


def test_transform_plan_rejects_non_3x3_matrices():
    with pytest.raises(ValueError):
        bdi.TransformPlan(np.eye(2), bdi.Size(10, 20))


def test_enhancement_result_exposes_only_requested_modes_in_order():
    color = bdi.RenderedImage(np.zeros((2, 2, 3), dtype=np.uint8))
    gray = bdi.RenderedImage(np.zeros((2, 2), dtype=np.uint8))
    result = bdi.EnhancementResult(
        color=color,
        gray=gray,
        requested_modes=(bdi.OutputMode.GRAY, bdi.OutputMode.COLOR),
    )

    assert [mode for mode, _ in result.requested()] == [
        bdi.OutputMode.GRAY,
        bdi.OutputMode.COLOR,
    ]
    assert result[bdi.OutputMode.COLOR] is color
    with pytest.raises(KeyError):
        result[bdi.OutputMode.BW]


def test_enhancement_result_rejects_requested_mode_without_image():
    with pytest.raises(ValueError):
        bdi.EnhancementResult(
            color=None,
            requested_modes=(bdi.OutputMode.COLOR,),
        )


def test_parser_modes_derive_from_the_enum_and_deduplicate():
    parser = bdi.build_parser()
    args = parser.parse_args(["entrada.png", "--modes", "BW, Color,bw"])

    assert args.modes == (bdi.OutputMode.BW, bdi.OutputMode.COLOR)
    help_text = parser.format_help()
    for mode in bdi.OutputMode.values():
        assert mode in help_text


@pytest.mark.parametrize("raw", ["", "   "])
def test_parser_rejects_empty_or_blank_modes(raw: str):
    parser = bdi.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["entrada.png", "--modes", raw])
    assert exc.value.code == 2


def test_parser_invalid_mode_message_lists_the_enum_values(capsys):
    parser = bdi.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["entrada.png", "--modes", "nope"])
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    for mode in bdi.OutputMode.values():
        assert mode in stderr


def test_parser_rejects_invalid_corners_as_usage_error():
    parser = bdi.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["entrada.png", "--corners", "1,2,3"])
    assert exc.value.code == 2


def test_parser_accepts_verbose_flag():
    args = bdi.build_parser().parse_args(["entrada.png", "--verbose"])
    assert args.verbose is True


def test_enhance_only_computes_requested_modes(monkeypatch):
    image = np.full((20, 30, 3), 128, dtype=np.uint8)
    monkeypatch.setattr(
        pipeline,
        "build_combined_transform",
        lambda *args, **kwargs: _neutral_plan(),
    )

    def fail_binarize(*args, **kwargs):
        raise AssertionError("binarize não deveria ser chamado")

    monkeypatch.setattr(pipeline, "binarize", fail_binarize)

    color_only = bdi.enhance(
        image,
        _settings(),
        modes=(bdi.OutputMode.COLOR,),
    )
    assert color_only.color is not None
    assert color_only.gray is None
    assert color_only.bw is None
    assert color_only.requested_modes == (bdi.OutputMode.COLOR,)

    gray_only = bdi.enhance(
        image,
        _settings(),
        modes=(bdi.OutputMode.GRAY,),
    )
    assert gray_only.color is None
    assert gray_only.gray is not None
    assert gray_only.bw is None

    monkeypatch.undo()
    monkeypatch.setattr(
        pipeline,
        "build_combined_transform",
        lambda *args, **kwargs: _neutral_plan(),
    )
    bw_only = bdi.enhance(
        image,
        _settings(),
        modes=(bdi.OutputMode.BW,),
    )
    assert bw_only.color is None
    assert bw_only.gray is None
    assert bw_only.bw is not None
    assert bw_only.bw.is_binary is True
    assert set(np.unique(bw_only.bw.data)) <= {0, 255}


def test_enhance_rejects_empty_mode_list():
    image = np.full((20, 30, 3), 128, dtype=np.uint8)
    with pytest.raises(ValueError):
        bdi.enhance(image, _settings(), modes=())


def test_enhance_does_not_write_to_stdout(capsys, monkeypatch):
    image = np.full((20, 30, 3), 128, dtype=np.uint8)
    monkeypatch.setattr(
        pipeline,
        "build_combined_transform",
        lambda *args, **kwargs: _neutral_plan(),
    )

    bdi.enhance(image, _settings(), modes=(bdi.OutputMode.COLOR,))

    assert capsys.readouterr().out == ""


def test_dpi_is_derived_from_target_width():
    params = bdi.IoParams()
    assert params.dpi_for_width(2480) == pytest.approx(2480 / 8.27)
    with pytest.raises(ValueError):
        params.dpi_for_width(0)


def test_io_uses_rendered_image_semantics_instead_of_scanning_pixels(tmp_path: Path):
    grayscale = bdi.RenderedImage(
        np.array([[0, 255], [255, 0]], dtype=np.uint8),
        is_binary=False,
    )
    binary = bdi.RenderedImage(
        np.array([[0, 255], [255, 0]], dtype=np.uint8),
        is_binary=True,
    )
    gray_path = tmp_path / "gray.png"
    binary_path = tmp_path / "binary.png"

    bdi.save_png(grayscale, gray_path, dpi=123.4)
    bdi.save_png(binary, binary_path, dpi=123.4)

    with Image.open(gray_path) as image:
        assert image.mode == "L"
        assert image.info["dpi"][0] == pytest.approx(123.4, abs=0.5)
    with Image.open(binary_path) as image:
        assert image.mode == "1"


def test_rendered_to_pil_centralizes_color_conversion():
    color = bdi.RenderedImage(np.zeros((2, 2, 3), dtype=np.uint8))
    pil = bdi.rendered_to_pil(color)
    assert pil.mode == "RGB"

    with pytest.raises(ValueError):
        bdi.rendered_to_pil(
            bdi.RenderedImage(np.zeros((2, 2, 3), dtype=np.uint8), is_binary=True)
        )


def test_facade_only_reexports_from_package_modules():
    from better_docimage import cli, io, pipeline as pipeline_module, settings

    assert bdi.Settings is settings.Settings
    assert bdi.OutputMode is pipeline_module.OutputMode
    assert bdi.EnhancementResult is pipeline_module.EnhancementResult
    assert bdi.RenderedImage is io.RenderedImage
    assert bdi.save_png is io.save_png
    assert bdi.enhance is pipeline_module.enhance
    assert bdi.build_parser is cli.build_parser
    assert bdi.main is cli.main
    for name in bdi.__all__:
        assert hasattr(bdi, name)


def test_package_modules_import_without_cycles():
    import importlib

    for name in (
        "better_docimage.settings",
        "better_docimage.io",
        "better_docimage.pipeline",
        "better_docimage.cli",
        "better_docimage.__main__",
    ):
        assert importlib.import_module(name) is not None
