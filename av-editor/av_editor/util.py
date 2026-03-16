from __future__ import annotations

import re
from typing import Any, Tuple

from .errors import ConfigError


def is_numberish(x: Any) -> bool:
    return isinstance(x, (int, float)) or (isinstance(x, str) and x.strip() != "")


def to_float(x: Any, ctx: str) -> float:
    if not is_numberish(x):
        raise ConfigError(f"{ctx} must be a number, got {type(x).__name__}")
    try:
        return float(x)
    except ValueError as e:
        raise ConfigError(f"{ctx} must be a number, got {x!r}") from e


def parse_position(value: Any, ctx: str) -> Tuple[float, float]:
    if not (isinstance(value, list) and len(value) == 2):
        raise ConfigError(f"{ctx} must be [x_percent, y_percent]")
    x_pct = to_float(value[0], f"{ctx}[0]")
    y_pct = to_float(value[1], f"{ctx}[1]")
    # Allow off-canvas placement (negative or >100) for framing workflows.
    return (x_pct, y_pct)


def parse_scale(value: Any, ctx: str) -> float:
    scale_pct = to_float(value, ctx)
    if scale_pct <= 0.0:
        raise ConfigError(f"{ctx} must be > 0")
    return scale_pct


def parse_crop(value: Any, ctx: str) -> Tuple[float, float, float, float]:
    """Parse crop percentages [left, right, top, bottom]."""
    if not (isinstance(value, list) and len(value) == 4):
        raise ConfigError(f"{ctx} must be [left, right, top, bottom]")

    left_pct = to_float(value[0], f"{ctx}[0]")
    right_pct = to_float(value[1], f"{ctx}[1]")
    top_pct = to_float(value[2], f"{ctx}[2]")
    bottom_pct = to_float(value[3], f"{ctx}[3]")

    for idx, v in enumerate((left_pct, right_pct, top_pct, bottom_pct)):
        if not (0.0 <= v <= 100.0):
            raise ConfigError(f"{ctx}[{idx}] must be between 0 and 100")

    if left_pct + right_pct >= 100.0:
        raise ConfigError(f"{ctx} left+right must be < 100")
    if top_pct + bottom_pct >= 100.0:
        raise ConfigError(f"{ctx} top+bottom must be < 100")

    return (left_pct, right_pct, top_pct, bottom_pct)


def safe_label(text: str) -> str:
    """Make a string safe for ffmpeg filter labels."""
    return re.sub(r"[^0-9A-Za-z_]", "_", text)


def normalize_time(t: float, precision: int = 6) -> float:
    """Normalize time values for stable dictionary keys.

    We use floats throughout, but for grouping events that should be at the same
    timestamp, rounding helps avoid tiny representation differences.
    """
    return round(float(t), precision)
