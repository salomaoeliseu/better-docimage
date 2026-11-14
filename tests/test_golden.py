"""Estrutura do baseline (rápida) e reprodução das 18 saídas (lenta)."""

from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

import pytest

import goldenlib
from goldenlib import (
    ASSETS,
    ENTRYPOINT,
    GOLDEN_DIR,
    MANIFEST_PATH,
    MAX_LEVEL_TOLERANCE,
    MEAN_ABS_TOLERANCE,
    MODES,
    OUTPUT_PREFIX,
    ROOT,
    THUMB_MAX_SIDE,
    compare_thumbnails,
    image_stats,
    load_raster,
    load_thumbnail,
    make_thumbnail,
    normalized_pdf_sha256,
    read_manifest,
    same_pinned_environment,
    sha256_bytes,
    sha256_file,
)


@pytest.mark.fast
def test_pdf_date_normalization_ignores_pillow_timestamps():
    first = b"stream (D:20260101120000Z) end (D:20260101120001Z)"
    second = b"stream (D:20260202120000Z) end (D:20260202120001Z)"
    assert sha256_bytes(goldenlib.normalized_pdf_bytes(first)) == sha256_bytes(
        goldenlib.normalized_pdf_bytes(second)
    )
    assert sha256_bytes(first) != sha256_bytes(second)


@pytest.mark.fast
def test_manifest_records_eighteen_outputs_and_thumbnails():
    manifest = read_manifest()
    outputs = manifest["outputs"]
    assert len(outputs) == 18
    pairs = {(item["source"], item["mode"], item["kind"]) for item in outputs}
    expected = {
        (asset, mode, kind)
        for asset in ASSETS
        for mode in MODES
        for kind in ("png", "pdf")
    }
    assert pairs == expected
    for item in outputs:
        assert len(item["sha256"]) == 64
        assert item["width"] > 0 and item["height"] > 0
        for key in ("mean", "p1", "p99"):
            assert math.isfinite(item[key])
        thumb = GOLDEN_DIR / item["thumbnail"]
        assert thumb.is_file()
        image = load_thumbnail(thumb)
        assert max(image.shape[:2]) == THUMB_MAX_SIDE
    full_images = [
        path
        for path in GOLDEN_DIR.rglob("*")
        if path.suffix.lower() in {".jpg", ".jpeg", ".pdf"}
        or (path.suffix.lower() == ".png" and path.parent == GOLDEN_DIR)
    ]
    assert full_images == []
    recorded_environment = manifest["environment"]
    for key in (
        "opencv_python",
        "opencv_runtime",
        "numpy",
        "pillow",
        "python",
        "platform",
    ):
        assert recorded_environment[key]


@pytest.mark.slow
def test_baseline_outputs_are_reproducible():
    manifest = read_manifest()
    recorded = {(item["source"], item["mode"], item["kind"]): item for item in manifest["outputs"]}
    compare_hashes = same_pinned_environment(manifest["environment"])

    with tempfile.TemporaryDirectory(prefix="better-docimage-check-") as temporary:
        work = Path(temporary)
        for asset in ASSETS:
            subprocess.run(
                [
                    *ENTRYPOINT,
                    str(ROOT / asset),
                    "-o",
                    str(work / OUTPUT_PREFIX),
                    "--modes",
                    ",".join(MODES),
                    "--pdf",
                ],
                check=True,
                cwd=ROOT,
            )
            for mode in MODES:
                png = work / f"{OUTPUT_PREFIX}_{mode}.png"
                pdf = work / f"{OUTPUT_PREFIX}_{mode}.pdf"
                png_record = recorded[(asset, mode, "png")]
                pdf_record = recorded[(asset, mode, "pdf")]
                raster = load_raster(png)
                stats = image_stats(raster)
                for record in (png_record, pdf_record):
                    assert stats["width"] == record["width"]
                    assert stats["height"] == record["height"]
                if compare_hashes:
                    for record in (png_record, pdf_record):
                        assert stats["mean"] == pytest.approx(record["mean"], abs=1e-6)
                        assert stats["p1"] == pytest.approx(record["p1"], abs=1e-6)
                        assert stats["p99"] == pytest.approx(record["p99"], abs=1e-6)
                    assert sha256_file(png) == png_record["sha256"]
                    assert normalized_pdf_sha256(pdf) == pdf_record["sha256_normalized"]
                compare_thumbnails(make_thumbnail(raster), load_thumbnail(GOLDEN_DIR / png_record["thumbnail"]))


@pytest.mark.fast
def test_tolerances_match_the_phase_0_contract():
    assert MEAN_ABS_TOLERANCE == pytest.approx(1 / 255)
    assert MAX_LEVEL_TOLERANCE == 2
