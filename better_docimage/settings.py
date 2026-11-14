"""Configuração do usuário e parâmetros internos de tuning.

Este módulo contém apenas valores imutáveis e os defaults documentados de cada
etapa. Funções de processamento pertencem a `primitives.py`, `detection.py`,
`quality.py`, `pipeline.py` e `io.py`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

A4_WIDTH_300DPI = 2480
MIN_LEVEL = 0
MAX_LEVEL = 255


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


__all__ = [
    "A4_WIDTH_300DPI",
    "MIN_LEVEL",
    "MAX_LEVEL",
    "Settings",
    "DetectionParams",
    "QualityParams",
    "IoParams",
]
