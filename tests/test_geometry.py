"""Geometria exata do pipeline atual, sem alterar better_docimage_refactored.py."""

from __future__ import annotations

import numpy as np
import pytest

import better_docimage_refactored as bdi

pytestmark = pytest.mark.fast


def _solid(height: int = 40, width: int = 50, value: int = 128) -> np.ndarray:
    return np.full((height, width, 3), value, dtype=np.uint8)


def _apply(matrix: np.ndarray, point: tuple[float, float]) -> np.ndarray:
    homogeneous = matrix @ np.array([point[0], point[1], 1.0], dtype=np.float64)
    return homogeneous[:2] / homogeneous[2]


def test_combined_transform_is_fine_rotation_then_crop_then_geometry(monkeypatch):
    image = _solid()
    height, width = image.shape[:2]
    geometry = np.array(
        [[1.0, 0.2, 3.0], [0.0, 1.0, -5.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    trim_offset = (4, 7)
    fine_angle = 0.4

    monkeypatch.setattr(
        bdi,
        "table_geometry_transform",
        lambda img, max_side=bdi.MAX_GEOMETRY_SIDE: (geometry.copy(), (width, height)),
    )
    monkeypatch.setattr(bdi, "estimate_skew", lambda gray, max_angle=5.0: fine_angle)
    monkeypatch.setattr(
        bdi,
        "trim_blank_border_with_offset",
        lambda img, white=252, min_ratio=0.02: (img, trim_offset),
    )

    combined, canvas = bdi.build_combined_transform(image, None, (0, 0))

    crop_matrix = bdi.translation_matrix(-trim_offset[0], -trim_offset[1])
    fine_rotation = bdi.rotation_matrix(fine_angle, width, height)
    expected = fine_rotation @ crop_matrix @ geometry

    np.testing.assert_allclose(combined, expected)
    assert canvas == (width, height)
    assert not np.allclose(combined, geometry @ crop_matrix @ fine_rotation)

    point = (12.0, 18.0)
    stepwise = _apply(fine_rotation, _apply(crop_matrix, _apply(geometry, point)))
    np.testing.assert_allclose(_apply(combined, point), stepwise)


def test_combined_transform_is_identity_when_detection_and_skew_are_neutral(monkeypatch):
    image = _solid()
    height, width = image.shape[:2]

    monkeypatch.setattr(bdi, "table_geometry_transform", lambda *args, **kwargs: None)
    monkeypatch.setattr(bdi, "estimate_skew", lambda gray, max_angle=5.0: 0.0)

    combined, canvas = bdi.build_combined_transform(image, None, (0, 0))

    np.testing.assert_allclose(combined, np.eye(3), atol=1e-10)
    assert canvas == (width, height)


def test_manual_corners_are_converted_by_subtracting_the_original_crop_offset(monkeypatch):
    image = _solid()
    captured: dict[str, np.ndarray] = {}

    def fake_perspective(img, quad, max_side=bdi.MAX_GEOMETRY_SIDE):
        captured["quad"] = np.asarray(quad, dtype=np.float32).copy()
        height, width = img.shape[:2]
        return np.eye(3, dtype=np.float64), (width, height)

    monkeypatch.setattr(bdi, "perspective_transform", fake_perspective)
    monkeypatch.setattr(bdi, "estimate_skew", lambda gray, max_angle=5.0: 0.0)
    corners = np.array([[10, 20], [30, 40], [50, 60], [70, 80]], dtype=np.float32)

    bdi.build_combined_transform(image, corners, (3, 5))

    expected = corners.copy()
    expected[:, 0] -= 3
    expected[:, 1] -= 5
    np.testing.assert_allclose(captured["quad"], expected)


def test_zero_crop_offset_leaves_manual_corners_unchanged(monkeypatch):
    image = _solid()
    captured: dict[str, np.ndarray] = {}

    def fake_perspective(img, quad, max_side=bdi.MAX_GEOMETRY_SIDE):
        captured["quad"] = np.asarray(quad, dtype=np.float32).copy()
        height, width = img.shape[:2]
        return np.eye(3, dtype=np.float64), (width, height)

    monkeypatch.setattr(bdi, "perspective_transform", fake_perspective)
    monkeypatch.setattr(bdi, "estimate_skew", lambda gray, max_angle=5.0: 0.0)
    corners = np.array([[1, 2], [3, 4], [5, 6], [7, 8]], dtype=np.float32)

    bdi.build_combined_transform(image, corners, (0, 0))

    np.testing.assert_allclose(captured["quad"], corners)


def test_warp_and_upscale_once_matches_target_width():
    image = _solid(height=20, width=30)
    output = bdi.warp_and_upscale_once(image, np.eye(3), (30, 20), target_width=60)
    assert output.shape[1] == 60
    assert output.shape[0] == 40
