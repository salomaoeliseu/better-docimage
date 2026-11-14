"""A saída final nasce de uma única chamada a warpPerspective."""

from __future__ import annotations

import numpy as np
import pytest

import better_docimage_refactored as bdi

pytestmark = pytest.mark.fast


def test_warp_and_upscale_once_calls_warp_perspective_exactly_once(monkeypatch):
    calls = {"n": 0}
    real = bdi.cv2.warpPerspective

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(bdi.cv2, "warpPerspective", wrapped)
    image = np.full((20, 30, 3), 90, dtype=np.uint8)

    bdi.warp_and_upscale_once(image, np.eye(3), (30, 20), target_width=40)

    assert calls["n"] == 1


def test_enhance_resamples_the_final_image_exactly_once(monkeypatch):
    state = {"in_final": False, "final_warps": 0, "upscale_calls": 0}
    real_warp = bdi.cv2.warpPerspective
    real_upscale = bdi.warp_and_upscale_once

    def warp(*args, **kwargs):
        if state["in_final"]:
            state["final_warps"] += 1
        return real_warp(*args, **kwargs)

    def upscale(*args, **kwargs):
        state["upscale_calls"] += 1
        state["in_final"] = True
        try:
            return real_upscale(*args, **kwargs)
        finally:
            state["in_final"] = False

    monkeypatch.setattr(bdi.cv2, "warpPerspective", warp)
    monkeypatch.setattr(bdi, "warp_and_upscale_once", upscale)
    image = np.full((48, 64, 3), 140, dtype=np.uint8)
    settings = bdi.Settings(target_width=32, denoise_strength=0.0)

    bdi.enhance(image, settings, corners=None)

    assert state["upscale_calls"] == 1
    assert state["final_warps"] == 1
