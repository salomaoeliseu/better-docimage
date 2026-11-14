"""Interface de linha de comando: parser, validação antecipada e execução."""
from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

from .io import load_image, save_pdf, save_png
from .pipeline import OutputMode, enhance
from .settings import A4_WIDTH_300DPI, IoParams, Settings

logger = logging.getLogger(__name__)


def parse_modes(raw: str) -> tuple[OutputMode, ...]:
    tokens = [token.strip().lower() for token in raw.split(",") if token.strip()]
    valid = OutputMode.values()
    if not tokens:
        raise argparse.ArgumentTypeError(
            f"--modes exige pelo menos um modo: {', '.join(valid)}"
        )

    unknown = sorted({token for token in tokens if token not in valid})
    if unknown:
        raise argparse.ArgumentTypeError(
            f"modo(s) inválido(s): {', '.join(unknown)}; válidos: {', '.join(valid)}"
        )
    return tuple(dict.fromkeys(OutputMode(token) for token in tokens))


def parse_corners(raw: str) -> np.ndarray:
    try:
        values = [float(value.strip()) for value in raw.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--corners deve conter apenas números separados por vírgula"
        ) from exc

    if len(values) != 8:
        raise argparse.ArgumentTypeError(
            "--corners exige 8 valores: TLx,TLy,TRx,TRy,BRx,BRy,BLx,BLy"
        )
    points = np.asarray(values, dtype=np.float32)
    if not np.isfinite(points).all():
        raise argparse.ArgumentTypeError("--corners deve conter apenas números finitos")
    return points.reshape(4, 2)


def _positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("deve ser um inteiro") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("deve ser maior que zero")
    return value


def _positive_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("deve ser um número") from exc
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("deve ser um número finito")
    if value <= 0:
        raise argparse.ArgumentTypeError("deve ser maior que zero")
    return value


def _non_negative_float(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("deve ser um número") from exc
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("deve ser um número finito")
    if value < 0:
        raise argparse.ArgumentTypeError("não pode ser negativo")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Melhora a legibilidade de documentos fotografados."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None, help="prefixo de saída")
    parser.add_argument(
        "--modes",
        type=parse_modes,
        default=(OutputMode.COLOR, OutputMode.GRAY),
        metavar="MODO[,MODO...]",
        help=(
            "modos separados por vírgula: "
            f"{', '.join(OutputMode.values())} "
            "(bw pode eliminar traços finos)"
        ),
    )
    parser.add_argument("--width", type=_positive_int, default=A4_WIDTH_300DPI)
    parser.add_argument("--gamma", type=_positive_float, default=Settings.gamma)
    parser.add_argument("--sharpen", type=_non_negative_float, default=Settings.sharpen_amount)
    parser.add_argument("--denoise", type=_non_negative_float, default=Settings.denoise_strength)
    parser.add_argument("--bw-offset", type=int, default=Settings.bw_offset)
    parser.add_argument(
        "--corners",
        type=parse_corners,
        default=None,
        metavar="TLx,TLy,TRx,TRy,BRx,BRy,BLx,BLy",
        help="cantos na imagem original, antes do recorte automático",
    )
    parser.add_argument(
        "--pdf", action="store_true", help="também gera PDF com o mesmo DPI do PNG"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="mostra diagnóstico detalhado em stderr",
    )
    return parser


def run(args: argparse.Namespace) -> tuple[Path, ...]:
    settings = Settings(
        target_width=args.width,
        denoise_strength=args.denoise,
        gamma=args.gamma,
        sharpen_amount=args.sharpen,
        bw_offset=args.bw_offset,
    )

    input_image = load_image(args.input)
    result = enhance(input_image, settings, args.corners, args.modes)

    prefix = args.output or args.input.with_suffix("")
    io_params = IoParams()
    dpi = io_params.dpi_for_width(settings.target_width)

    written: list[Path] = []
    for mode, rendered in result.requested():
        png_path = Path(f"{prefix}_{mode.value}.png")
        save_png(rendered, png_path, dpi, io_params)
        if args.pdf:
            save_pdf(rendered, png_path.with_suffix(".pdf"), dpi)
        written.append(png_path)
    return tuple(written)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        written = run(args)
        for png_path in written:
            print(f"ok -> {png_path} ({png_path.stat().st_size / 1024:.0f} KB)")
    except Exception as exc:
        logger.error("%s", exc, exc_info=args.verbose)
        return 1
    return 0


__all__ = [
    "parse_modes",
    "parse_corners",
    "build_parser",
    "run",
    "main",
]
