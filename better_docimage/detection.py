"""Detecção de geometria e composição da transformação única.

As funções deste módulo apenas estimam a transformação. A aplicação à imagem
acontece uma única vez em `primitives.warp_and_upscale_once`.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import primitives
from .settings import MAX_LEVEL, MIN_LEVEL, DetectionParams

logger = logging.getLogger(__name__)


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
) -> primitives.TransformPlan | None:
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
    return primitives.TransformPlan(
        matrix, primitives.Size(int(size[0]), int(size[1]))
    )


def perspective_transform(
    img: np.ndarray,
    quad: np.ndarray,
    params: DetectionParams = DetectionParams(),
) -> primitives.TransformPlan | None:
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

    matrix = (
        primitives.translation_matrix(-float(min_xy[0]), -float(min_xy[1]))
        @ homography
    )
    return primitives.TransformPlan(
        matrix, primitives.Size(int(size[0]), int(size[1]))
    )


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


def build_combined_transform(
    img: np.ndarray,
    corners_in_input: np.ndarray | None,
    params: DetectionParams = DetectionParams(),
) -> primitives.TransformPlan:
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
    geometry_size = primitives.Size(width, height)

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
            geometry = primitives.rotation_matrix(initial_angle, width, height)
            geometry_size = primitives.Size(width, height)

    # Prévia descartável: serve apenas para estimar crop e deskew fino.
    if np.allclose(
        geometry, np.eye(3), atol=params.identity_atol
    ) and geometry_size == primitives.Size(width, height):
        preview = img
    else:
        preview = cv2.warpPerspective(
            img,
            geometry,
            (geometry_size.width, geometry_size.height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    preview_trimmed, trim_offset = primitives.trim_blank_border_with_offset(
        preview, params
    )
    trimmed_height, trimmed_width = preview_trimmed.shape[:2]
    crop_matrix = primitives.translation_matrix(-trim_offset.x, -trim_offset.y)

    fine_angle = estimate_skew(
        cv2.cvtColor(preview_trimmed, cv2.COLOR_BGR2GRAY),
        max_angle=params.fine_skew_max_angle,
        params=params,
    )
    if abs(fine_angle) >= params.fine_skew_min_angle:
        fine_rotation = primitives.rotation_matrix(
            fine_angle, trimmed_width, trimmed_height
        )
    else:
        fine_rotation = np.eye(3, dtype=np.float64)

    # Ordem: geometria -> recorte do preview -> rotação fina.
    combined = fine_rotation @ crop_matrix @ geometry
    return primitives.TransformPlan(
        combined, primitives.Size(trimmed_width, trimmed_height)
    )


__all__ = [
    "table_geometry_transform",
    "perspective_transform",
    "estimate_skew",
    "build_combined_transform",
]
