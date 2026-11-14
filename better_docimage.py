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
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

A4_WIDTH_300DPI = 2480
MAX_GEOMETRY_SIDE = 6000


@dataclass(frozen=True)
class Settings:
    target_width: int = A4_WIDTH_300DPI
    denoise_strength: float = 4.0
    gamma: float = 1.5
    sharpen_amount: float = 0.9
    bw_offset: int = 0


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def load_image(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        pil = ImageOps.exif_transpose(source).convert("RGB")
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def save_png(img: np.ndarray, path: Path) -> None:
    if img.ndim == 3:
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    else:
        pil = Image.fromarray(img)
        if set(np.unique(img)) <= {0, 255}:
            pil = pil.convert("1")
    pil.save(path, dpi=(300, 300), optimize=True)


def save_pdf(img: np.ndarray, path: Path) -> None:
    if img.ndim == 3:
        Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(
            path, "PDF", resolution=300.0, quality=92
        )
        return

    pil = Image.fromarray(img)
    if set(np.unique(img)) <= {0, 255}:
        pil = pil.convert("1")
    pil.save(path, "PDF", resolution=300.0)


# --------------------------------------------------------------------------- #
# Recorte sem reamostragem
# --------------------------------------------------------------------------- #
def trim_blank_border_with_offset(
    img: np.ndarray,
    white: int = 252,
    min_ratio: float = 0.02,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Recorta margens brancas e retorna também (x, y) do recorte na origem."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    non_white = gray < white

    rows = np.where(non_white.mean(axis=1) > min_ratio)[0]
    cols = np.where(non_white.mean(axis=0) > min_ratio)[0]
    if rows.size == 0 or cols.size == 0:
        return img, (0, 0)

    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    return img[y0:y1, x0:x1], (x0, y0)


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
) -> float | None:
    segments = cv2.HoughLinesP(
        mask,
        1,
        np.pi / 1800,
        threshold=150,
        minLineLength=max(1, min_length),
        maxLineGap=25,
    )
    if segments is None:
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
        if abs(angle) < 8:
            angles.append(float(angle))
            weights.append(float(np.hypot(dx, dy)))

    if len(angles) < 5:
        return None

    order = np.argsort(angles)
    ordered_weights = np.asarray(weights)[order]
    cumulative = np.cumsum(ordered_weights)
    median_index = int(np.searchsorted(cumulative, cumulative[-1] / 2))
    return float(np.asarray(angles)[order][median_index])


def table_geometry_transform(
    img: np.ndarray,
    max_side: int = MAX_GEOMETRY_SIDE,
) -> tuple[np.ndarray, tuple[int, int]] | None:
    """Retorna a transformação afim da tabela sem aplicá-la à imagem original."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        12,
    )
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(1, width // 20), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(1, height // 40))
    )
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, horizontal_kernel
    )
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)

    angle_h = _dominant_line_angle(horizontal, width // 6, vertical=False)
    angle_v = _dominant_line_angle(vertical, height // 12, vertical=True)
    if angle_h is None or angle_v is None:
        return None

    a, b = np.radians(angle_h), np.radians(angle_v)
    basis = np.array(
        [[np.cos(a), np.sin(b)], [np.sin(a), np.cos(b)]],
        dtype=np.float64,
    )
    try:
        linear = np.linalg.inv(basis)
    except np.linalg.LinAlgError:
        return None

    corners = np.array(
        [[0, 0], [width, 0], [width, height], [0, height]],
        dtype=np.float64,
    )
    moved = corners @ linear.T
    offset = -moved.min(axis=0)
    size = np.ceil(moved.max(axis=0) - moved.min(axis=0)).astype(int)
    if np.any(size <= 0) or size.max() > max_side:
        return None

    matrix = np.eye(3, dtype=np.float64)
    matrix[:2, :2] = linear
    matrix[:2, 2] = offset
    return matrix, (int(size[0]), int(size[1]))


def perspective_transform(
    img: np.ndarray,
    quad: np.ndarray,
    max_side: int = MAX_GEOMETRY_SIDE,
) -> tuple[np.ndarray, tuple[int, int]] | None:
    """Retorna homografia e canvas, sem reamostrar a imagem."""
    points = np.ascontiguousarray(quad, dtype=np.float32).reshape(4, 2)
    tl, tr, br, bl = points

    width = int(round((np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2))
    height = int(round((np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2))
    if width < 2 or height < 2:
        return None

    destination = np.ascontiguousarray(
        np.array(
            [[0, 0], [width, 0], [width, height], [0, height]],
            dtype=np.float32,
        )
    )
    homography = cv2.getPerspectiveTransform(points, destination)
    if not np.isfinite(homography).all():
        return None

    image_height, image_width = img.shape[:2]
    image_corners = np.array(
        [[0, 0], [image_width, 0], [image_width, image_height], [0, image_height]],
        dtype=np.float32,
    ).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(image_corners, homography).reshape(-1, 2)
    if not np.isfinite(transformed).all():
        return None

    min_xy = transformed.min(axis=0)
    max_xy = transformed.max(axis=0)
    size = np.ceil(max_xy - min_xy).astype(int)
    if np.any(size <= 0) or size.max() > max_side:
        return None

    matrix = translation_matrix(-float(min_xy[0]), -float(min_xy[1])) @ homography
    return matrix, (int(size[0]), int(size[1]))


def estimate_skew(gray: np.ndarray, max_angle: float = 5.0) -> float:
    """Estima o ângulo que maximiza a concentração das linhas horizontais."""
    if gray.size == 0 or gray.shape[1] == 0:
        return 0.0

    scale = 1000.0 / gray.shape[1]
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    small = cv2.resize(
        gray, None, fx=scale, fy=scale, interpolation=interpolation
    )

    if min(small.shape[:2]) < 32:
        return 0.0

    binary = cv2.adaptiveThreshold(
        small,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
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
            borderValue=0,
        )
        profile = rotated.sum(axis=1).astype(np.float64)
        return float(np.var(np.diff(profile)))

    coarse_values = np.arange(-max_angle, max_angle + 0.25, 0.5)
    coarse = float(max(coarse_values, key=score))
    fine_values = np.arange(coarse - 0.5, coarse + 0.51, 0.05)
    return float(max(fine_values, key=score))


# --------------------------------------------------------------------------- #
# Transformação geométrica única
# --------------------------------------------------------------------------- #
def build_combined_transform(
    img: np.ndarray,
    corners: np.ndarray | None,
    original_crop_offset: tuple[int, int],
) -> tuple[np.ndarray, tuple[int, int]]:
    """
    Compõe geometria, recorte intermediário e deskew fino.

    A prévia é usada exclusivamente para determinar o segundo recorte e o
    ângulo fino. A matriz retornada sempre transforma a imagem de entrada
    diretamente para o canvas final, sem encadear reamostragens.
    """
    height, width = img.shape[:2]
    geometry = np.eye(3, dtype=np.float64)
    geometry_size = (width, height)

    if corners is not None:
        # --corners é definido em coordenadas da imagem original, antes do trim.
        adjusted_corners = np.asarray(corners, dtype=np.float32).reshape(4, 2).copy()
        crop_x, crop_y = original_crop_offset
        adjusted_corners[:, 0] -= crop_x
        adjusted_corners[:, 1] -= crop_y
        result = perspective_transform(img, adjusted_corners)
        if result is not None:
            geometry, geometry_size = result
        else:
            print("aviso: perspectiva inválida ou grande demais; ignorando --corners")
    else:
        result = table_geometry_transform(img)
        if result is not None:
            geometry, geometry_size = result
        else:
            initial_angle = estimate_skew(
                cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), max_angle=5.0
            )
            geometry = rotation_matrix(initial_angle, width, height)
            geometry_size = (width, height)

    # Prévia descartável: serve apenas para estimar crop e deskew fino.
    if np.allclose(geometry, np.eye(3), atol=1e-10) and geometry_size == (width, height):
        preview = img
    else:
        preview = cv2.warpPerspective(
            img,
            geometry,
            geometry_size,
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    preview_trimmed, (trim_x, trim_y) = trim_blank_border_with_offset(preview)
    trimmed_height, trimmed_width = preview_trimmed.shape[:2]
    crop_matrix = translation_matrix(-trim_x, -trim_y)

    fine_angle = estimate_skew(
        cv2.cvtColor(preview_trimmed, cv2.COLOR_BGR2GRAY), max_angle=1.5
    )
    if abs(fine_angle) >= 0.03:
        fine_rotation = rotation_matrix(fine_angle, trimmed_width, trimmed_height)
    else:
        fine_rotation = np.eye(3, dtype=np.float64)

    # Ordem: geometria -> recorte do preview -> rotação fina.
    combined = fine_rotation @ crop_matrix @ geometry
    return combined, (trimmed_width, trimmed_height)


def warp_and_upscale_once(
    img: np.ndarray,
    transform: np.ndarray,
    canvas_size: tuple[int, int],
    target_width: int,
) -> np.ndarray:
    """Aplica geometria e escala em uma única reamostragem da imagem-fonte."""
    canvas_width, canvas_height = canvas_size
    if target_width <= 0 or canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("A largura e as dimensões do canvas devem ser positivas.")

    scale = target_width / float(canvas_width)
    output_height = max(1, int(round(canvas_height * scale)))
    scale_matrix = np.array(
        [[scale, 0.0, 0.0], [0.0, scale, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    final_transform = scale_matrix @ transform

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
def flatten_illumination(img: np.ndarray) -> np.ndarray:
    """Uniformiza gradientes lentos de iluminação sem binarizar o documento."""
    kernel_size = max(15, (img.shape[1] // 40) | 1)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
    )
    background = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)
    background = cv2.GaussianBlur(background, (0, 0), kernel_size / 2)
    return cv2.divide(img, background, scale=255)


def stretch_contrast(img: np.ndarray, gamma: float) -> np.ndarray:
    if gamma <= 0:
        raise ValueError("gamma deve ser maior que zero.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    black = float(np.percentile(gray, 0.5))
    white = float(np.percentile(gray, 90.0))
    denominator = max(white - black, 1.0)
    scaled = np.clip((img.astype(np.float32) - black) / denominator, 0.0, 1.0)
    return (255.0 * np.power(scaled, gamma)).astype(np.uint8)


def unsharp(img: np.ndarray, amount: float, sigma: float) -> np.ndarray:
    if amount <= 0:
        return img
    blurred = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1.0 + amount, blurred, -amount, 0)


def binarize(gray: np.ndarray, offset: int) -> np.ndarray:
    threshold, _ = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    _, binary = cv2.threshold(
        gray,
        min(max(threshold + offset, 0), 255),
        255,
        cv2.THRESH_BINARY,
    )
    return binary


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def enhance(
    source: np.ndarray,
    settings: Settings,
    corners: np.ndarray | None,
) -> dict[str, np.ndarray]:
    # Recorte é apenas uma visualização de uma região da matriz: não interpola.
    img, crop_offset = trim_blank_border_with_offset(source)

    transform, canvas_size = build_combined_transform(
        img,
        corners,
        crop_offset,
    )

    # Denoise antes da única reamostragem. Use --denoise 0 para desativá-lo.
    if settings.denoise_strength > 0:
        strength = settings.denoise_strength
        img = cv2.fastNlMeansDenoisingColored(
            img, None, strength, strength, 7, 21
        )

    img = warp_and_upscale_once(
        img,
        transform,
        canvas_size,
        settings.target_width,
    )

    img = flatten_illumination(img)
    img = stretch_contrast(img, settings.gamma)
    img = unsharp(img, settings.sharpen_amount, sigma=1.6)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return {
        "color": img,
        "gray": gray,
        "bw": binarize(gray, settings.bw_offset),
    }


def parse_corners(raw: str | None) -> np.ndarray | None:
    if not raw:
        return None

    try:
        values = [float(value.strip()) for value in raw.split(",")]
    except ValueError as exc:
        raise ValueError("--corners deve conter apenas números separados por vírgula") from exc

    if len(values) != 8:
        raise ValueError(
            "--corners exige 8 valores: TLx,TLy,TRx,TRy,BRx,BRy,BLx,BLy"
        )
    return np.asarray(values, dtype=np.float32).reshape(4, 2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Melhora a legibilidade de documentos fotografados."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None, help="prefixo de saída")
    parser.add_argument(
        "--modes",
        default="color,gray",
        help="color,gray,bw (bw pode eliminar traços finos)",
    )
    parser.add_argument("--width", type=int, default=A4_WIDTH_300DPI)
    parser.add_argument("--gamma", type=float, default=Settings.gamma)
    parser.add_argument("--sharpen", type=float, default=Settings.sharpen_amount)
    parser.add_argument("--denoise", type=float, default=Settings.denoise_strength)
    parser.add_argument("--bw-offset", type=int, default=Settings.bw_offset)
    parser.add_argument("--corners", default=None)
    parser.add_argument(
        "--pdf", action="store_true", help="também gera PDF (300 DPI)"
    )
    args = parser.parse_args()

    if args.width <= 0:
        parser.error("--width deve ser maior que zero")
    if args.denoise < 0:
        parser.error("--denoise não pode ser negativo")
    if args.gamma <= 0:
        parser.error("--gamma deve ser maior que zero")

    settings = Settings(
        target_width=args.width,
        denoise_strength=args.denoise,
        gamma=args.gamma,
        sharpen_amount=args.sharpen,
        bw_offset=args.bw_offset,
    )

    input_image = load_image(args.input)
    results = enhance(input_image, settings, parse_corners(args.corners))

    prefix = args.output or args.input.with_suffix("")
    valid_modes = {"color", "gray", "bw"}
    modes = [mode.strip().lower() for mode in args.modes.split(",") if mode.strip()]
    unknown_modes = set(modes) - valid_modes
    if unknown_modes:
        parser.error(f"modo(s) inválido(s): {', '.join(sorted(unknown_modes))}")

    for mode in modes:
        png_path = Path(f"{prefix}_{mode}.png")
        save_png(results[mode], png_path)
        if args.pdf:
            save_pdf(results[mode], png_path.with_suffix(".pdf"))
        print(f"ok -> {png_path} ({png_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
