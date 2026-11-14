"""Métricas, miniaturas e hashes compartilhados pelo baseline e pela suíte lenta."""

from __future__ import annotations

import hashlib
import json
import platform
import re
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden"
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"
SCRIPT = ROOT / "better_docimage.py"
THUMB_MAX_SIDE = 600
MEAN_ABS_TOLERANCE = 1 / 255
MAX_LEVEL_TOLERANCE = 2
MODES = ("color", "gray", "bw")
ASSETS = (
    "assets/ficha_19_capa.jpg",
    "assets/ficha_19_historico.jpg",
    "assets/teste_0_color (1).png",
)
OUTPUT_PREFIX = "baseline"
PDF_DATE = re.compile(br"\(D:\d{14}Z\)")


def environment() -> dict[str, str]:
    return {
        "opencv_python": version("opencv-python"),
        "opencv_runtime": cv2.__version__,
        "numpy": version("numpy"),
        "pillow": version("pillow"),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def same_pinned_environment(recorded: dict[str, str]) -> bool:
    current = environment()
    keys = ("opencv_python", "numpy", "pillow", "platform")
    return all(current[key] == recorded[key] for key in keys)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_pdf_bytes(data: bytes) -> bytes:
    """Remove CreationDate/ModDate, que o Pillow grava com a hora da execução."""
    return PDF_DATE.sub(b"(D:NORMALIZED)", data)


def normalized_pdf_sha256(path: Path) -> str:
    return sha256_bytes(normalized_pdf_bytes(path.read_bytes()))


def load_raster(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f"não foi possível ler {path}")
    return image


def image_stats(img: np.ndarray) -> dict[str, float | int]:
    flat = img.astype(np.float64).ravel()
    return {
        "width": int(img.shape[1]),
        "height": int(img.shape[0]),
        "mean": float(flat.mean()),
        "p1": float(np.percentile(flat, 1)),
        "p99": float(np.percentile(flat, 99)),
    }


def make_thumbnail(img: np.ndarray, max_side: int = THUMB_MAX_SIDE) -> np.ndarray:
    height, width = img.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return img.copy()
    scale = max_side / float(longest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)


def save_thumbnail(img: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    thumb = make_thumbnail(img)
    if thumb.ndim == 2:
        Image.fromarray(thumb).save(path)
        return
    Image.fromarray(cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)).save(path)


def load_thumbnail(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        array = np.asarray(source)
    if array.ndim == 3:
        return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    return array


def thumbnail_name(source: Path, mode: str) -> str:
    stem = "".join(char if char.isalnum() or char in "-_" else "_" for char in source.stem)
    stem = stem.strip("_")
    return f"thumbs/{stem}_{mode}.png"


def compare_thumbnails(actual: np.ndarray, expected: np.ndarray) -> None:
    if actual.shape != expected.shape:
        raise AssertionError(f"miniatura {actual.shape} != baseline {expected.shape}")
    difference = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
    mean_difference = float(difference.mean()) / 255.0
    max_difference = int(difference.max())
    if mean_difference > MEAN_ABS_TOLERANCE or max_difference > MAX_LEVEL_TOLERANCE:
        raise AssertionError(
            "miniatura fora da tolerância: "
            f"média {mean_difference:.6f} (limite {MEAN_ABS_TOLERANCE:.6f}), "
            f"máximo {max_difference} níveis (limite {MAX_LEVEL_TOLERANCE})"
        )


def write_manifest(payload: dict) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
