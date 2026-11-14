"""Leitura e escrita de imagens, com a semântica de cor resolvida na fronteira."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .settings import IoParams


@dataclass(frozen=True)
class RenderedImage:
    """Imagem de saída com a semântica de cor já resolvida pelo pipeline."""

    data: np.ndarray
    is_binary: bool = False


def load_image(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        pil = ImageOps.exif_transpose(source).convert("RGB")
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def rendered_to_pil(image: RenderedImage) -> Image.Image:
    """Centraliza a conversão para PIL e a decisão de modo binário."""
    data = image.data
    if data.ndim == 3:
        if image.is_binary:
            raise ValueError("imagem binária deve ser monocromática.")
        return Image.fromarray(cv2.cvtColor(data, cv2.COLOR_BGR2RGB))
    if data.ndim != 2:
        raise ValueError("a imagem deve ter 2 ou 3 dimensões.")

    pil = Image.fromarray(data)
    if image.is_binary:
        pil = pil.convert("1")
    return pil


def save_png(
    image: RenderedImage,
    path: Path,
    dpi: float,
    params: IoParams = IoParams(),
) -> None:
    rendered_to_pil(image).save(
        path,
        dpi=(dpi, dpi),
        optimize=params.png_optimize,
    )


def save_pdf(image: RenderedImage, path: Path, dpi: float) -> None:
    rendered_to_pil(image).save(path, "PDF", resolution=dpi)


__all__ = [
    "RenderedImage",
    "load_image",
    "rendered_to_pil",
    "save_png",
    "save_pdf",
]
