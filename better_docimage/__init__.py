"""Fachada pública do pacote `better_docimage`.

Aqui não há lógica de domínio: apenas reexports estáveis e o `__all__`.
Importar daqui mantém o custo de mudança baixo enquanto os módulos internos
evoluem.
"""
from __future__ import annotations

from .cli import build_parser, main, parse_corners, parse_modes, run
from .io import RenderedImage, load_image, rendered_to_pil, save_pdf, save_png
from .pipeline import (
    EnhancementResult,
    Offset,
    OutputMode,
    PreparedInput,
    Size,
    TransformPlan,
    binarize,
    build_combined_transform,
    enhance,
    estimate_skew,
    flatten_illumination,
    perspective_transform,
    prepare_input,
    rotation_matrix,
    stretch_contrast,
    table_geometry_transform,
    translation_matrix,
    trim_blank_border_with_offset,
    unsharp,
    warp_and_upscale_once,
)
from .settings import (
    A4_WIDTH_300DPI,
    MAX_LEVEL,
    MIN_LEVEL,
    DetectionParams,
    IoParams,
    QualityParams,
    Settings,
)

__all__ = [
    # Configuração e tuning
    "A4_WIDTH_300DPI",
    "MIN_LEVEL",
    "MAX_LEVEL",
    "Settings",
    "DetectionParams",
    "QualityParams",
    "IoParams",
    # Contratos e pipeline
    "OutputMode",
    "Size",
    "Offset",
    "TransformPlan",
    "EnhancementResult",
    "PreparedInput",
    "enhance",
    # I/O
    "RenderedImage",
    "load_image",
    "rendered_to_pil",
    "save_png",
    "save_pdf",
    # Geometria (temporariamente em pipeline.py)
    "trim_blank_border_with_offset",
    "prepare_input",
    "translation_matrix",
    "rotation_matrix",
    "table_geometry_transform",
    "perspective_transform",
    "estimate_skew",
    "build_combined_transform",
    "warp_and_upscale_once",
    # Qualidade (temporariamente em pipeline.py)
    "flatten_illumination",
    "stretch_contrast",
    "unsharp",
    "binarize",
    # CLI
    "parse_modes",
    "parse_corners",
    "build_parser",
    "run",
    "main",
]
