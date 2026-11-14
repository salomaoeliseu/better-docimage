"""Fachada pública do pacote `better_docimage`.

Aqui não há lógica de domínio: apenas reexports estáveis e o `__all__`.
Importar daqui mantém o custo de mudança baixo enquanto os módulos internos
evoluem.

API pública estável:
- configuração: `Settings`, `DetectionParams`, `QualityParams`, `IoParams`;
- contratos: `OutputMode`, `Size`, `Offset`, `TransformPlan`, `PreparedInput`,
  `EnhancementResult`;
- pipeline: `enhance`;
- geometria: `prepare_input`, `build_combined_transform`, `estimate_skew`,
  `table_geometry_transform`, `perspective_transform`, `translation_matrix`,
  `rotation_matrix`, `trim_blank_border_with_offset`, `warp_and_upscale_once`;
- qualidade: `flatten_illumination`, `stretch_contrast`, `unsharp`, `binarize`;
- I/O: `RenderedImage`, `load_image`, `rendered_to_pil`, `save_png`, `save_pdf`;
- CLI: `parse_modes`, `parse_corners`, `build_parser`, `run`, `main`.
"""
from __future__ import annotations

from .cli import build_parser, main, parse_corners, parse_modes, run
from .detection import (
    build_combined_transform,
    estimate_skew,
    perspective_transform,
    table_geometry_transform,
)
from .io import RenderedImage, load_image, rendered_to_pil, save_pdf, save_png
from .pipeline import EnhancementResult, OutputMode, enhance
from .primitives import (
    Offset,
    PreparedInput,
    Size,
    TransformPlan,
    prepare_input,
    rotation_matrix,
    translation_matrix,
    trim_blank_border_with_offset,
    warp_and_upscale_once,
)
from .quality import binarize, flatten_illumination, stretch_contrast, unsharp
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
    # Geometria
    "trim_blank_border_with_offset",
    "prepare_input",
    "translation_matrix",
    "rotation_matrix",
    "table_geometry_transform",
    "perspective_transform",
    "estimate_skew",
    "build_combined_transform",
    "warp_and_upscale_once",
    # Qualidade
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
