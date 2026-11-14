"""Contratos e primitivas geométricas do pipeline.

Este módulo concentra o espaço de coordenadas dos cantos, as matrizes, o
recorte sem reamostragem e a única operação de reamostragem da saída. A
detecção e a composição de transformações ficam em `detection.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .settings import DetectionParams


@dataclass(frozen=True)
class Size:
    """Dimensões em pixels, com nome explícito para largura e altura."""

    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("largura e altura devem ser positivas.")


@dataclass(frozen=True)
class Offset:
    """Deslocamento inteiro no espaço de pixels da imagem."""

    x: int
    y: int


@dataclass(frozen=True)
class TransformPlan:
    """Transformação 3x3 e o canvas em que ela deve ser aplicada."""

    transform: np.ndarray
    size: Size

    def __post_init__(self) -> None:
        if self.transform.shape != (3, 3):
            raise ValueError("transform deve ser uma matriz 3x3.")


@dataclass(frozen=True)
class PreparedInput:
    """Imagem preparada e cantos no mesmo espaço de coordenadas."""

    image: np.ndarray
    corners: np.ndarray | None
    crop: Offset


def trim_blank_border_with_offset(
    img: np.ndarray,
    params: DetectionParams = DetectionParams(),
) -> tuple[np.ndarray, Offset]:
    """Recorta margens brancas e retorna também o offset do recorte na origem."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    non_white = gray < params.trim_white_level

    rows = np.where(non_white.mean(axis=1) > params.trim_min_ratio)[0]
    cols = np.where(non_white.mean(axis=0) > params.trim_min_ratio)[0]
    if rows.size == 0 or cols.size == 0:
        return img, Offset(0, 0)

    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    return img[y0:y1, x0:x1], Offset(x0, y0)


def prepare_input(
    source: np.ndarray,
    corners: np.ndarray | None,
    params: DetectionParams = DetectionParams(),
) -> PreparedInput:
    """Recorta a origem e converte os cantos para o espaço da imagem recortada.

    Os cantos entram sempre no espaço da imagem original, antes do recorte.
    Esta é a única função que converte coordenadas entre os dois espaços.
    """
    image, offset = trim_blank_border_with_offset(source, params)
    if corners is not None:
        adjusted = np.asarray(corners, dtype=np.float32).reshape(4, 2).copy()
        adjusted[:, 0] -= offset.x
        adjusted[:, 1] -= offset.y
        corners = adjusted
    return PreparedInput(image=image, corners=corners, crop=offset)


def translation_matrix(x: float, y: float) -> np.ndarray:
    return np.array(
        [[1.0, 0.0, x], [0.0, 1.0, y], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def rotation_matrix(angle: float, width: int, height: int) -> np.ndarray:
    """Matriz fonte->destino; mantém o mesmo tamanho de tela da versão anterior."""
    affine = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    matrix = np.eye(3, dtype=np.float64)
    matrix[:2, :] = affine
    return matrix


def warp_and_upscale_once(
    img: np.ndarray,
    plan: TransformPlan,
    target_width: int,
) -> np.ndarray:
    """Aplica geometria e escala em uma única reamostragem da imagem-fonte."""
    canvas_width, canvas_height = plan.size.width, plan.size.height
    if target_width <= 0 or canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("A largura e as dimensões do canvas devem ser positivas.")

    scale = target_width / float(canvas_width)
    output_height = max(1, int(round(canvas_height * scale)))
    scale_matrix = np.array(
        [[scale, 0.0, 0.0], [0.0, scale, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    final_transform = scale_matrix @ plan.transform

    return cv2.warpPerspective(
        img,
        final_transform,
        (int(target_width), output_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


__all__ = [
    "Size",
    "Offset",
    "TransformPlan",
    "PreparedInput",
    "trim_blank_border_with_offset",
    "prepare_input",
    "translation_matrix",
    "rotation_matrix",
    "warp_and_upscale_once",
]
