"""Contratos e geometria exata do pipeline."""

from __future__ import annotations

import logging

import numpy as np
import pytest

import better_docimage as bdi
import better_docimage.pipeline as pipeline

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
    trim_offset = bdi.Offset(4, 7)
    fine_angle = 0.4

    monkeypatch.setattr(
        pipeline,
        "table_geometry_transform",
        lambda img, params=bdi.DetectionParams(): bdi.TransformPlan(
            geometry.copy(), bdi.Size(width, height)
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "estimate_skew",
        lambda gray, max_angle=5.0, params=None: fine_angle,
    )
    monkeypatch.setattr(
        pipeline,
        "trim_blank_border_with_offset",
        lambda img, params=bdi.DetectionParams(): (img, trim_offset),
    )

    plan = bdi.build_combined_transform(image, None)

    crop_matrix = bdi.translation_matrix(-trim_offset.x, -trim_offset.y)
    fine_rotation = bdi.rotation_matrix(fine_angle, width, height)
    expected = fine_rotation @ crop_matrix @ geometry

    np.testing.assert_allclose(plan.transform, expected)
    assert plan.size == bdi.Size(width, height)
    assert not np.allclose(plan.transform, geometry @ crop_matrix @ fine_rotation)

    point = (12.0, 18.0)
    stepwise = _apply(fine_rotation, _apply(crop_matrix, _apply(geometry, point)))
    np.testing.assert_allclose(_apply(plan.transform, point), stepwise)


def test_combined_transform_is_identity_when_detection_and_skew_are_neutral(monkeypatch):
    image = _solid()
    height, width = image.shape[:2]

    monkeypatch.setattr(
        pipeline, "table_geometry_transform", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        pipeline,
        "estimate_skew",
        lambda gray, max_angle=5.0, params=None: 0.0,
    )

    plan = bdi.build_combined_transform(image, None)

    np.testing.assert_allclose(plan.transform, np.eye(3), atol=1e-10)
    assert plan.size == bdi.Size(width, height)


def test_prepare_input_converts_original_corners_once(monkeypatch):
    image = _solid()
    captured: dict[str, np.ndarray] = {}

    def fake_perspective(img, quad, params=bdi.DetectionParams()):
        captured["quad"] = np.asarray(quad, dtype=np.float32).copy()
        height, width = img.shape[:2]
        return bdi.TransformPlan(np.eye(3, dtype=np.float64), bdi.Size(width, height))

    monkeypatch.setattr(
        pipeline,
        "trim_blank_border_with_offset",
        lambda img, params=bdi.DetectionParams(): (img, bdi.Offset(3, 5)),
    )
    monkeypatch.setattr(pipeline, "perspective_transform", fake_perspective)
    monkeypatch.setattr(
        pipeline,
        "estimate_skew",
        lambda gray, max_angle=5.0, params=None: 0.0,
    )
    corners = np.array([[10, 20], [30, 40], [50, 60], [70, 80]], dtype=np.float32)

    prepared = bdi.prepare_input(image, corners)
    bdi.build_combined_transform(prepared.image, prepared.corners)

    assert prepared.crop == bdi.Offset(3, 5)
    expected = corners.copy()
    expected[:, 0] -= 3
    expected[:, 1] -= 5
    np.testing.assert_allclose(prepared.corners, expected)
    np.testing.assert_allclose(captured["quad"], expected)


def test_prepare_input_without_margins_keeps_zero_offset_and_corners(monkeypatch):
    image = _solid()
    captured: dict[str, np.ndarray] = {}

    def fake_perspective(img, quad, params=bdi.DetectionParams()):
        captured["quad"] = np.asarray(quad, dtype=np.float32).copy()
        height, width = img.shape[:2]
        return bdi.TransformPlan(np.eye(3, dtype=np.float64), bdi.Size(width, height))

    monkeypatch.setattr(pipeline, "perspective_transform", fake_perspective)
    monkeypatch.setattr(
        pipeline,
        "estimate_skew",
        lambda gray, max_angle=5.0, params=None: 0.0,
    )
    corners = np.array([[1, 2], [3, 4], [5, 6], [7, 8]], dtype=np.float32)

    prepared = bdi.prepare_input(image, corners)
    bdi.build_combined_transform(prepared.image, prepared.corners)

    assert prepared.crop == bdi.Offset(0, 0)
    np.testing.assert_allclose(prepared.corners, corners)
    np.testing.assert_allclose(captured["quad"], corners)


def test_prepare_input_on_fully_white_image_returns_zero_offset():
    image = np.full((20, 30, 3), 255, dtype=np.uint8)

    prepared = bdi.prepare_input(image, None)

    assert prepared.crop == bdi.Offset(0, 0)
    assert prepared.corners is None
    np.testing.assert_array_equal(prepared.image, image)


def test_prepare_input_does_not_clamp_corners_outside_the_trimmed_image():
    image = np.full((40, 50, 3), 255, dtype=np.uint8)
    image[10:30, 15:35] = 80
    corners = np.array(
        [[0, 0], [100, 0], [100, 100], [0, 100]],
        dtype=np.float32,
    )

    prepared = bdi.prepare_input(image, corners)

    assert prepared.crop == bdi.Offset(15, 10)
    assert prepared.image.shape == (20, 20, 3)
    expected = corners - np.array([15, 10], dtype=np.float32)
    np.testing.assert_allclose(prepared.corners, expected)


def test_invalid_perspective_logs_the_fallback_reason(monkeypatch, caplog):
    image = _solid()
    corners = np.array([[1, 2], [3, 4], [5, 6], [7, 8]], dtype=np.float32)
    monkeypatch.setattr(pipeline, "perspective_transform", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pipeline,
        "estimate_skew",
        lambda gray, max_angle=5.0, params=None: 0.0,
    )

    with caplog.at_level(logging.WARNING, logger="better_docimage.pipeline"):
        plan = bdi.build_combined_transform(image, corners)

    assert "perspectiva inválida" in caplog.text
    assert plan.size == bdi.Size(image.shape[1], image.shape[0])


def test_missing_table_logs_the_fallback_reason(monkeypatch, caplog):
    image = _solid()
    monkeypatch.setattr(
        pipeline, "table_geometry_transform", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        pipeline,
        "estimate_skew",
        lambda gray, max_angle=5.0, params=None: 0.0,
    )

    with caplog.at_level(logging.WARNING, logger="better_docimage.pipeline"):
        plan = bdi.build_combined_transform(image, None)

    assert "geometria de tabela não detectada" in caplog.text
    assert plan.size == bdi.Size(image.shape[1], image.shape[0])


def test_warp_and_upscale_once_matches_target_width():
    image = _solid(height=20, width=30)
    plan = bdi.TransformPlan(np.eye(3), bdi.Size(30, 20))

    output = bdi.warp_and_upscale_once(image, plan, target_width=60)

    assert output.shape[1] == 60
    assert output.shape[0] == 40
