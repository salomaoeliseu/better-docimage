#!/usr/bin/env python3
"""
better_docimage.py

Melhora documentos fotografados sem modelos generativos.

Mudança principal em relação à versão anterior:
- recorte, correção afim/perspectiva, deskew fino e upscale são representados
  por matrizes e compostos;
- a imagem final é reamostrada uma única vez, diretamente da imagem de origem;
- uma prévia geométrica é criada apenas para estimar o deskew fino e detectar
  os limites do documento. Essa prévia nunca é usada como origem da saída final.

Instalação:
    python -m pip install opencv-python numpy pillow

Uso:
    python better_docimage.py entrada.png -o saida --pdf

Os cantos manuais devem ser informados na imagem original, antes do recorte:
    python better_docimage.py entrada.png \
        --corners 100,278,1265,262,1265,1125,80,1100

Para testar sem denoising (útil quando os caracteres são muito pequenos):
    python better_docimage.py entrada.png --denoise 0
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

A4_WIDTH_300DPI = 2480
MIN_LEVEL = 0
MAX_LEVEL = 255


# --------------------------------------------------------------------------- #
# Contratos de domínio
# --------------------------------------------------------------------------- #
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
class RenderedImage:
    """Imagem de saída com a semântica de cor já resolvida pelo pipeline."""

    data: np.ndarray
    is_binary: bool = False


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


@dataclass(frozen=True)
class PreparedInput:
    """Imagem preparada e cantos no mesmo espaço de coordenadas."""

    image: np.ndarray
    corners: np.ndarray | None
    crop: Offset


# --------------------------------------------------------------------------- #
# Configuração e parâmetros de tuning
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Settings:
    """Configuração exposta ao usuário da CLI."""

    target_width: int = A4_WIDTH_300DPI
    denoise_strength: float = 4.0
    gamma: float = 1.5
    sharpen_amount: float = 0.9
    bw_offset: int = 0


@dataclass(frozen=True)
class DetectionParams:
    """Parâmetros internos de recorte, detecção e deskew."""

    max_geometry_side: int = 6000
    min_perspective_side: int = 2
    identity_atol: float = 1e-10

    trim_white_level: int = 252
    trim_min_ratio: float = 0.02

    adaptive_block_size: int = 31
    table_adaptive_c: float = 12.0
    skew_adaptive_c: float = 15.0

    horizontal_kernel_divisor: int = 20
    vertical_kernel_divisor: int = 40
    horizontal_min_length_divisor: int = 6
    vertical_min_length_divisor: int = 12

    hough_rho: float = 1.0
    hough_theta: float = math.pi / 1800
    hough_threshold: int = 150
    hough_max_line_gap: int = 25
    dominant_angle_limit: float = 8.0
    dominant_min_segments: int = 5

    skew_scale_width: float = 1000.0
    skew_min_side: int = 32
    skew_coarse_step: float = 0.5
    skew_fine_step: float = 0.05
    skew_fine_radius: float = 0.5
    initial_skew_max_angle: float = 5.0
    fine_skew_max_angle: float = 1.5
    fine_skew_min_angle: float = 0.03


@dataclass(frozen=True)
class QualityParams:
    """Parâmetros internos de denoise, iluminação, contraste e nitidez."""

    denoise_template_window: int = 7
    denoise_search_window: int = 21

    flatten_kernel_min: int = 15
    flatten_kernel_divisor: int = 40
    flatten_blur_sigma_divisor: float = 2.0

    contrast_black_percentile: float = 0.5
    contrast_white_percentile: float = 90.0
    contrast_min_range: float = 1.0

    unsharp_sigma: float = 1.6


@dataclass(frozen=True)
class IoParams:
    """Metadados e opções de escrita; o DPI deriva da largura alvo."""

    a4_width_inches: float = 8.27
    png_optimize: bool = True

    def dpi_for_width(self, target_width: int) -> float:
        if target_width <= 0:
            raise ValueError("target_width deve ser maior que zero.")
        if self.a4_width_inches <= 0:
            raise ValueError("a4_width_inches deve ser maior que zero.")
        return target_width / self.a4_width_inches


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Recorte sem reamostragem
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Estimativa de geometria
# --------------------------------------------------------------------------- #
def _dominant_line_angle(
    mask: np.ndarray,
    min_length: int,
    vertical: bool,
    params: DetectionParams,
) -> float | None:
    orientation = "vertical" if vertical else "horizontal"
    segments = cv2.HoughLinesP(
        mask,
        params.hough_rho,
        params.hough_theta,
        threshold=params.hough_threshold,
        minLineLength=max(1, min_length),
        maxLineGap=params.hough_max_line_gap,
    )
    if segments is None:
        logger.warning("nenhuma linha %s detectada", orientation)
        return None

    angles: list[float] = []
    weights: list[float] = []
    for x1, y1, x2, y2 in segments.reshape(-1, 4):
        dx, dy = (x2 - x1), (y2 - y1)
        angle = np.degrees(
            np.arctan2(dx, dy) if vertical else np.arctan2(dy, dx)
        )
        angle = (angle + 90) % 180 - 90
        if vertical:
            angle = angle if abs(angle) < 45 else angle - np.sign(angle) * 180
        if abs(angle) < params.dominant_angle_limit:
            angles.append(float(angle))
            weights.append(float(np.hypot(dx, dy)))

    if len(angles) < params.dominant_min_segments:
        logger.warning(
            "linhas %s insuficientes (%d < %d)",
            orientation,
            len(angles),
            params.dominant_min_segments,
        )
        return None

    order = np.argsort(angles)
    ordered_weights = np.asarray(weights)[order]
    cumulative = np.cumsum(ordered_weights)
    median_index = int(np.searchsorted(cumulative, cumulative[-1] / 2))
    return float(np.asarray(angles)[order][median_index])


def table_geometry_transform(
    img: np.ndarray,
    params: DetectionParams = DetectionParams(),
) -> TransformPlan | None:
    """Retorna a transformação afim da tabela sem aplicá-la à imagem original."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    binary = cv2.adaptiveThreshold(
        gray,
        MAX_LEVEL,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        params.adaptive_block_size,
        params.table_adaptive_c,
    )
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(1, width // params.horizontal_kernel_divisor), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(1, height // params.vertical_kernel_divisor))
    )
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, horizontal_kernel
    )
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)

    angle_h = _dominant_line_angle(
        horizontal,
        width // params.horizontal_min_length_divisor,
        vertical=False,
        params=params,
    )
    angle_v = _dominant_line_angle(
        vertical,
        height // params.vertical_min_length_divisor,
        vertical=True,
        params=params,
    )
    if angle_h is None or angle_v is None:
        logger.warning("geometria de tabela não detectada: linhas ausentes")
        return None

    a, b = np.radians(angle_h), np.radians(angle_v)
    basis = np.array(
        [[np.cos(a), np.sin(b)], [np.sin(a), np.cos(b)]],
        dtype=np.float64,
    )
    try:
        linear = np.linalg.inv(basis)
    except np.linalg.LinAlgError:
        logger.warning("geometria de tabela não detectada: base linear singular")
        return None

    corners = np.array(
        [[0, 0], [width, 0], [width, height], [0, height]],
        dtype=np.float64,
    )
    moved = corners @ linear.T
    offset = -moved.min(axis=0)
    size = np.ceil(moved.max(axis=0) - moved.min(axis=0)).astype(int)
    if np.any(size <= 0) or size.max() > params.max_geometry_side:
        logger.warning(
            "geometria de tabela ignorada: canvas %dx%d inválido ou acima de %d px",
            int(size[0]),
            int(size[1]),
            params.max_geometry_side,
        )
        return None

    matrix = np.eye(3, dtype=np.float64)
    matrix[:2, :2] = linear
    matrix[:2, 2] = offset
    return TransformPlan(matrix, Size(int(size[0]), int(size[1])))


def perspective_transform(
    img: np.ndarray,
    quad: np.ndarray,
    params: DetectionParams = DetectionParams(),
) -> TransformPlan | None:
    """Retorna homografia e canvas, sem reamostrar a imagem."""
    points = np.ascontiguousarray(quad, dtype=np.float32).reshape(4, 2)
    tl, tr, br, bl = points

    width = int(round((np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2))
    height = int(round((np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2))
    if width < params.min_perspective_side or height < params.min_perspective_side:
        logger.warning(
            "perspectiva ignorada: dimensões calculadas inválidas (%dx%d)",
            width,
            height,
        )
        return None

    destination = np.ascontiguousarray(
        np.array(
            [[0, 0], [width, 0], [width, height], [0, height]],
            dtype=np.float32,
        )
    )
    homography = cv2.getPerspectiveTransform(points, destination)
    if not np.isfinite(homography).all():
        logger.warning("perspectiva ignorada: homografia não finita")
        return None

    image_height, image_width = img.shape[:2]
    image_corners = np.array(
        [[0, 0], [image_width, 0], [image_width, image_height], [0, image_height]],
        dtype=np.float32,
    ).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(image_corners, homography).reshape(-1, 2)
    if not np.isfinite(transformed).all():
        logger.warning("perspectiva ignorada: cantos transformados não finitos")
        return None

    min_xy = transformed.min(axis=0)
    max_xy = transformed.max(axis=0)
    size = np.ceil(max_xy - min_xy).astype(int)
    if np.any(size <= 0) or size.max() > params.max_geometry_side:
        logger.warning(
            "perspectiva ignorada: canvas %dx%d inválido ou acima de %d px",
            int(size[0]),
            int(size[1]),
            params.max_geometry_side,
        )
        return None

    matrix = translation_matrix(-float(min_xy[0]), -float(min_xy[1])) @ homography
    return TransformPlan(matrix, Size(int(size[0]), int(size[1])))


def estimate_skew(
    gray: np.ndarray,
    max_angle: float = 5.0,
    params: DetectionParams = DetectionParams(),
) -> float:
    """Estima o ângulo que maximiza a concentração das linhas horizontais."""
    if gray.size == 0 or gray.shape[1] == 0:
        return 0.0

    scale = params.skew_scale_width / gray.shape[1]
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    small = cv2.resize(
        gray, None, fx=scale, fy=scale, interpolation=interpolation
    )

    if min(small.shape[:2]) < params.skew_min_side:
        return 0.0

    binary = cv2.adaptiveThreshold(
        small,
        MAX_LEVEL,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        params.adaptive_block_size,
        params.skew_adaptive_c,
    )
    height, width = binary.shape

    def score(angle: float) -> float:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        rotated = cv2.warpAffine(
            binary,
            matrix,
            (width, height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=MIN_LEVEL,
        )
        profile = rotated.sum(axis=1).astype(np.float64)
        return float(np.var(np.diff(profile)))

    coarse_values = np.arange(
        -max_angle,
        max_angle + params.skew_coarse_step / 2,
        params.skew_coarse_step,
    )
    coarse = float(max(coarse_values, key=score))
    fine_values = np.arange(
        coarse - params.skew_fine_radius,
        coarse + params.skew_fine_radius + params.skew_fine_step / 2,
        params.skew_fine_step,
    )
    return float(max(fine_values, key=score))


# --------------------------------------------------------------------------- #
# Transformação geométrica única
# --------------------------------------------------------------------------- #
def build_combined_transform(
    img: np.ndarray,
    corners_in_input: np.ndarray | None,
    params: DetectionParams = DetectionParams(),
) -> TransformPlan:
    """
    Compõe geometria, recorte intermediário e deskew fino.

    `corners_in_input` está no mesmo espaço de `img`; a conversão a partir da
    imagem original acontece uma única vez em `prepare_input`.

    A prévia é usada exclusivamente para determinar o segundo recorte e o
    ângulo fino. A matriz retornada sempre transforma a imagem de entrada
    diretamente para o canvas final, sem encadear reamostragens.
    """
    height, width = img.shape[:2]
    geometry = np.eye(3, dtype=np.float64)
    geometry_size = Size(width, height)

    if corners_in_input is not None:
        result = perspective_transform(img, corners_in_input, params)
        if result is not None:
            geometry, geometry_size = result.transform, result.size
        else:
            logger.warning(
                "perspectiva inválida; usando transformação identidade em vez de --corners"
            )
    else:
        result = table_geometry_transform(img, params)
        if result is not None:
            geometry, geometry_size = result.transform, result.size
        else:
            logger.warning(
                "geometria de tabela não detectada; usando deskew inicial"
            )
            initial_angle = estimate_skew(
                cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
                max_angle=params.initial_skew_max_angle,
                params=params,
            )
            geometry = rotation_matrix(initial_angle, width, height)
            geometry_size = Size(width, height)

    # Prévia descartável: serve apenas para estimar crop e deskew fino.
    if np.allclose(
        geometry, np.eye(3), atol=params.identity_atol
    ) and geometry_size == Size(width, height):
        preview = img
    else:
        preview = cv2.warpPerspective(
            img,
            geometry,
            (geometry_size.width, geometry_size.height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    preview_trimmed, trim_offset = trim_blank_border_with_offset(preview, params)
    trimmed_height, trimmed_width = preview_trimmed.shape[:2]
    crop_matrix = translation_matrix(-trim_offset.x, -trim_offset.y)

    fine_angle = estimate_skew(
        cv2.cvtColor(preview_trimmed, cv2.COLOR_BGR2GRAY),
        max_angle=params.fine_skew_max_angle,
        params=params,
    )
    if abs(fine_angle) >= params.fine_skew_min_angle:
        fine_rotation = rotation_matrix(fine_angle, trimmed_width, trimmed_height)
    else:
        fine_rotation = np.eye(3, dtype=np.float64)

    # Ordem: geometria -> recorte do preview -> rotação fina.
    combined = fine_rotation @ crop_matrix @ geometry
    return TransformPlan(combined, Size(trimmed_width, trimmed_height))


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


# --------------------------------------------------------------------------- #
# Qualidade de imagem
# --------------------------------------------------------------------------- #
def flatten_illumination(
    img: np.ndarray,
    params: QualityParams = QualityParams(),
) -> np.ndarray:
    """Uniformiza gradientes lentos de iluminação sem binarizar o documento."""
    kernel_size = max(
        params.flatten_kernel_min,
        (img.shape[1] // params.flatten_kernel_divisor) | 1,
    )
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
    )
    background = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)
    background = cv2.GaussianBlur(
        background,
        (0, 0),
        kernel_size / params.flatten_blur_sigma_divisor,
    )
    return cv2.divide(img, background, scale=MAX_LEVEL)


def stretch_contrast(
    img: np.ndarray,
    gamma: float,
    params: QualityParams = QualityParams(),
) -> np.ndarray:
    if gamma <= 0:
        raise ValueError("gamma deve ser maior que zero.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    black = float(np.percentile(gray, params.contrast_black_percentile))
    white = float(np.percentile(gray, params.contrast_white_percentile))
    denominator = max(white - black, params.contrast_min_range)
    scaled = np.clip((img.astype(np.float32) - black) / denominator, 0.0, 1.0)
    return (float(MAX_LEVEL) * np.power(scaled, gamma)).astype(np.uint8)


def unsharp(
    img: np.ndarray,
    amount: float,
    params: QualityParams = QualityParams(),
) -> np.ndarray:
    if amount <= 0:
        return img
    blurred = cv2.GaussianBlur(img, (0, 0), params.unsharp_sigma)
    return cv2.addWeighted(img, 1.0 + amount, blurred, -amount, 0)


def binarize(gray: np.ndarray, offset: int) -> np.ndarray:
    threshold, _ = cv2.threshold(
        gray, MIN_LEVEL, MAX_LEVEL, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    _, binary = cv2.threshold(
        gray,
        min(max(threshold + offset, MIN_LEVEL), MAX_LEVEL),
        MAX_LEVEL,
        cv2.THRESH_BINARY,
    )
    return binary


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
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


if __name__ == "__main__":
    raise SystemExit(main())
