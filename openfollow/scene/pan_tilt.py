# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Moving-light pan / tilt: aim a fixture at a stage point, and find a fixture from marks.

A fixture's frame has its pan axis along +Z (out of the base, towards the
head) and pan zero along +X. The beam at pan ``p`` and tilt ``t`` points
along ``(sin t cos p, sin t sin p, cos t)`` in that frame, so tilt 0 is
straight out of the base. The fixture-to-world rotation comes from how it is
mounted (hung under a bar, base up; or standing on the floor), its heading
(the stage bearing of pan zero: 0 = upstage, 90 = stage left) and two small
base corrections (pitch about pan zero, roll about the axis beside it).

DMX values are fractions 0..1 of each channel's travel: 0.5 is the centre,
and a fixture with ``pan_range`` degrees of pan reaches ``±pan_range / 2``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

MOUNTINGS = ("hung", "floor")
# Below this sine of the tilt, pan has no meaning (the beam is on the pan axis).
_PAN_SINGULAR = 1e-6


@dataclass(frozen=True)
class FixturePose:
    """Where a fixture hangs and which way it faces, in PSN-absolute metres and degrees."""

    x: float
    y: float
    z: float
    heading: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    mounting: str = "hung"

    def rotation(self) -> npt.NDArray[np.float64]:
        """Fixture-to-world rotation (columns are the fixture's X, Y, Z axes in world)."""
        h = math.radians(self.heading)
        x_axis = np.array([math.sin(h), math.cos(h), 0.0])
        z_axis = np.array([0.0, 0.0, -1.0 if self.mounting == "hung" else 1.0])
        y_axis = np.cross(z_axis, x_axis)
        base = np.column_stack([x_axis, y_axis, z_axis])
        p, r = math.radians(self.pitch), math.radians(self.roll)
        # Pitch tips pan zero up or down (about the fixture's Y); roll about its X.
        rot_y = np.array([[math.cos(p), 0.0, math.sin(p)], [0.0, 1.0, 0.0], [-math.sin(p), 0.0, math.cos(p)]])
        rot_x = np.array([[1.0, 0.0, 0.0], [0.0, math.cos(r), -math.sin(r)], [0.0, math.sin(r), math.cos(r)]])
        return np.asarray(base @ rot_x @ rot_y, dtype=np.float64)


def beam_direction(pose: FixturePose, pan_deg: float, tilt_deg: float) -> npt.NDArray[np.float64]:
    """Unit beam direction in world for a pan / tilt in degrees."""
    p, t = math.radians(pan_deg), math.radians(tilt_deg)
    local = np.array([math.sin(t) * math.cos(p), math.sin(t) * math.sin(p), math.cos(t)])
    return np.asarray(pose.rotation() @ local, dtype=np.float64)


def aim_angles(pose: FixturePose, target: tuple[float, float, float]) -> tuple[float, float] | None:
    """The pan and tilt (degrees, tilt 0..180) that point the beam at ``target``.

    ``None`` when the target is at the fixture itself. When the target lies on
    the pan axis, any pan works and 0 is returned.
    """
    v = np.array(target, dtype=np.float64) - np.array([pose.x, pose.y, pose.z])
    norm = float(np.linalg.norm(v))
    if norm < 1e-9:
        return None
    local = pose.rotation().T @ (v / norm)
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(local[2])))))
    if math.hypot(float(local[0]), float(local[1])) < _PAN_SINGULAR:
        return 0.0, tilt
    return math.degrees(math.atan2(float(local[1]), float(local[0]))), tilt


@dataclass(frozen=True)
class Travel:
    """A fixture's pan and tilt travel in degrees, and which way each channel turns."""

    pan_range: float = 540.0
    tilt_range: float = 270.0
    invert_pan: bool = False
    invert_tilt: bool = False

    def to_fractions(self, pan_deg: float, tilt_deg: float) -> tuple[float, float]:
        pan = pan_deg / self.pan_range
        tilt = tilt_deg / self.tilt_range
        return 0.5 + (-pan if self.invert_pan else pan), 0.5 + (-tilt if self.invert_tilt else tilt)

    def to_degrees(self, pan_frac: float, tilt_frac: float) -> tuple[float, float]:
        pan = (pan_frac - 0.5) * self.pan_range
        tilt = (tilt_frac - 0.5) * self.tilt_range
        return (-pan if self.invert_pan else pan), (-tilt if self.invert_tilt else tilt)


def fractions_for(
    pose: FixturePose,
    travel: Travel,
    target: tuple[float, float, float],
    previous: tuple[float, float] | None = None,
) -> tuple[float, float] | None:
    """The DMX pan / tilt fractions that aim at ``target``, or ``None`` when out of reach.

    Every aim has two solutions (``(p, t)`` and ``(p + 180, -t)``) and pan
    repeats every 360 degrees; of those inside the travel, the one closest to
    ``previous`` wins, so a light following someone never swings round the
    long way. Without a previous value the one nearest the centre wins.
    """
    angles = aim_angles(pose, target)
    if angles is None:
        return None
    pan, tilt = angles
    if previous is not None and math.sin(math.radians(tilt)) < _PAN_SINGULAR:
        pan = travel.to_degrees(*previous)[0]
    half_pan, half_tilt = travel.pan_range / 2.0, travel.tilt_range / 2.0
    candidates: list[tuple[float, float]] = []
    for base_pan, base_tilt in ((pan, tilt), (pan + 180.0, -tilt)):
        if abs(base_tilt) > half_tilt + 1e-9:
            continue
        for turns in range(-3, 4):
            candidate = base_pan + 360.0 * turns
            if abs(candidate) <= half_pan + 1e-9:
                candidates.append(travel.to_fractions(candidate, base_tilt))
    if not candidates:
        return None
    reference = previous if previous is not None else (0.5, 0.5)
    return min(candidates, key=lambda c: (c[0] - reference[0]) ** 2 + (c[1] - reference[1]) ** 2)


def to_dmx(fraction: float, fine: bool) -> tuple[int, ...]:
    """A channel fraction as one 8-bit value, or a coarse / fine 16-bit pair."""
    fraction = min(max(fraction, 0.0), 1.0)
    if not fine:
        return (round(fraction * 255),)
    value = round(fraction * 65535)
    return value >> 8, value & 0xFF


@dataclass(frozen=True)
class CalibrationMark:
    """A stage point and the pan / tilt fractions that put the beam on it."""

    x: float
    y: float
    z: float
    pan: float
    tilt: float


@dataclass(frozen=True)
class CalibrationResult:
    pose: FixturePose
    # Per-mark angle between where the solved fixture would point and the mark, in degrees.
    errors_deg: tuple[float, ...]

    @property
    def worst_deg(self) -> float:
        return max(self.errors_deg)


MIN_MARKS = 4


def _residuals(
    params: npt.NDArray[np.float64], mounting: str, marks: list[CalibrationMark], travel: Travel
) -> npt.NDArray[np.float64]:
    x, y, z, heading, pitch, roll = (float(v) for v in params)
    pose = FixturePose(x, y, z, heading, pitch, roll, mounting)
    out = []
    for mark in marks:
        beam = beam_direction(pose, *travel.to_degrees(mark.pan, mark.tilt))
        v = np.array([mark.x - pose.x, mark.y - pose.y, mark.z - pose.z])
        n = float(np.linalg.norm(v))
        out.append(beam - (v / n if n > 1e-9 else v))
    return np.concatenate(out) if out else np.zeros(0)


def _angle_deg(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))))))


def solve_pose(
    marks: list[CalibrationMark],
    travel: Travel,
    initial: FixturePose,
    *,
    iterations: int = 100,
) -> CalibrationResult | None:
    """Fit a fixture's position, heading and base tilt to marks it was pointed at.

    Starts from ``initial`` (the operator's rough position and mounting decide
    which of the mirror-image solutions is found). ``None`` with fewer than
    :data:`MIN_MARKS` marks, or when the fit does not settle on a finite pose.
    """
    if len(marks) < MIN_MARKS:
        return None
    params = np.array([initial.x, initial.y, initial.z, initial.heading, initial.pitch, initial.roll], dtype=np.float64)
    damping = 1e-3
    cost = float(np.sum(_residuals(params, initial.mounting, marks, travel) ** 2))
    steps = np.array([1e-4, 1e-4, 1e-4, 1e-3, 1e-3, 1e-3])
    for _ in range(iterations):
        r = _residuals(params, initial.mounting, marks, travel)
        jac = np.empty((r.size, params.size))
        for i, h in enumerate(steps):
            nudged = params.copy()
            nudged[i] += h
            jac[:, i] = (_residuals(nudged, initial.mounting, marks, travel) - r) / h
        normal = jac.T @ jac
        gradient = jac.T @ r
        improved = False
        for _attempt in range(10):
            try:
                delta = np.linalg.solve(normal + damping * np.diag(np.diag(normal) + 1e-9), -gradient)
            except np.linalg.LinAlgError:
                return None
            trial = params + delta
            trial_cost = float(np.sum(_residuals(trial, initial.mounting, marks, travel) ** 2))
            if np.all(np.isfinite(trial)) and trial_cost < cost:
                params, cost = trial, trial_cost
                damping = max(damping / 3.0, 1e-9)
                improved = True
                break
            damping *= 4.0
        if not improved or float(np.linalg.norm(delta)) < 1e-10:
            break
    if not np.all(np.isfinite(params)):
        return None
    heading = (float(params[3]) + 180.0) % 360.0 - 180.0
    pose = FixturePose(
        float(params[0]),
        float(params[1]),
        float(params[2]),
        heading,
        float(params[4]),
        float(params[5]),
        initial.mounting,
    )
    errors = []
    for mark in marks:
        beam = beam_direction(pose, *travel.to_degrees(mark.pan, mark.tilt))
        errors.append(_angle_deg(beam, np.array([mark.x - pose.x, mark.y - pose.y, mark.z - pose.z])))
    return CalibrationResult(pose, tuple(errors))
