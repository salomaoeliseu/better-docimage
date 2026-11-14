"""Operações de qualidade de imagem: iluminação, contraste, nitidez e binário."""
from __future__ import annotations

import cv2
import numpy as np

from .settings import MAX_LEVEL, MIN_LEVEL, QualityParams


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


__all__ = [
    "flatten_illumination",
    "stretch_contrast",
    "unsharp",
    "binarize",
]
