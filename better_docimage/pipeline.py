"""Orquestração do pipeline e contratos de saída.

O pipeline apenas coordena as etapas: preparação da entrada, detecção,
reamostragem única e qualidade. Geometria e qualidade vivem em módulos
próprios e não são reimplementadas aqui.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Iterator

import cv2
import numpy as np

from .detection import build_combined_transform
from .io import RenderedImage
from .primitives import Offset, prepare_input, warp_and_upscale_once
from .quality import binarize, flatten_illumination, stretch_contrast, unsharp
from .settings import DetectionParams, QualityParams, Settings

logger = logging.getLogger(__name__)


class OutputMode(StrEnum):
    """Vocabulário único dos modos de saída."""

    COLOR = "color"
    GRAY = "gray"
    BW = "bw"

    @property
    def is_binary(self) -> bool:
        return self is OutputMode.BW

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(mode.value for mode in cls)


@dataclass(frozen=True)
class EnhancementResult:
    """Saídas solicitadas, com `None` para os modos não pedidos."""

    color: RenderedImage | None = None
    gray: RenderedImage | None = None
    bw: RenderedImage | None = None
    crop: Offset = Offset(0, 0)
    requested_modes: tuple[OutputMode, ...] = ()

    def __post_init__(self) -> None:
        if not self.requested_modes:
            present = tuple(
                mode for mode in OutputMode if getattr(self, mode.value) is not None
            )
            object.__setattr__(self, "requested_modes", present)
        missing = [
            mode.value
            for mode in self.requested_modes
            if getattr(self, mode.value) is None
        ]
        if missing:
            raise ValueError(f"modos solicitados sem imagem: {', '.join(missing)}")

    def __getitem__(self, mode: OutputMode | str) -> RenderedImage:
        selected = OutputMode(mode)
        image = getattr(self, selected.value)
        if image is None:
            raise KeyError(f"modo não solicitado: {selected.value}")
        return image

    def requested(self) -> Iterator[tuple[OutputMode, RenderedImage]]:
        """Itera os modos na ordem em que foram solicitados."""
        for mode in self.requested_modes:
            yield mode, getattr(self, mode.value)


def enhance(
    source: np.ndarray,
    settings: Settings,
    corners: np.ndarray | None = None,
    modes: Iterable[OutputMode] = (OutputMode.COLOR, OutputMode.GRAY),
    detection: DetectionParams = DetectionParams(),
    quality: QualityParams = QualityParams(),
) -> EnhancementResult:
    requested = tuple(dict.fromkeys(OutputMode(mode) for mode in modes))
    if not requested:
        raise ValueError("pelo menos um modo de saída deve ser solicitado.")
    logger.debug("modos solicitados: %s", ", ".join(mode.value for mode in requested))

    prepared = prepare_input(source, corners, detection)
    logger.debug(
        "recorte aplicado: x=%d, y=%d",
        prepared.crop.x,
        prepared.crop.y,
    )

    plan = build_combined_transform(prepared.image, prepared.corners, detection)

    img = prepared.image
    # Denoise antes da única reamostragem. Use --denoise 0 para desativá-lo.
    if settings.denoise_strength > 0:
        strength = settings.denoise_strength
        img = cv2.fastNlMeansDenoisingColored(
            img,
            None,
            strength,
            strength,
            quality.denoise_template_window,
            quality.denoise_search_window,
        )

    img = warp_and_upscale_once(img, plan, settings.target_width)

    img = flatten_illumination(img, quality)
    img = stretch_contrast(img, settings.gamma, quality)
    img = unsharp(img, settings.sharpen_amount, quality)

    color = (
        RenderedImage(img, is_binary=OutputMode.COLOR.is_binary)
        if OutputMode.COLOR in requested
        else None
    )
    gray = None
    bw = None
    if OutputMode.GRAY in requested or OutputMode.BW in requested:
        gray_data = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if OutputMode.GRAY in requested:
            gray = RenderedImage(gray_data, is_binary=OutputMode.GRAY.is_binary)
        if OutputMode.BW in requested:
            bw = RenderedImage(
                binarize(gray_data, settings.bw_offset),
                is_binary=OutputMode.BW.is_binary,
            )

    return EnhancementResult(
        color=color,
        gray=gray,
        bw=bw,
        crop=prepared.crop,
        requested_modes=requested,
    )


__all__ = [
    "OutputMode",
    "EnhancementResult",
    "enhance",
]
