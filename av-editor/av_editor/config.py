from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .errors import ConfigError
from .models import Config, MasterAudio, Production, SourceState, TimelineEvent, VideoSource
from .util import parse_crop, parse_position, parse_scale, to_float


def _validate_file_readable(file_path: str, ctx: str) -> None:
    p = Path(file_path)
    if not p.exists():
        raise ConfigError(f"{ctx} file not found: {file_path}")
    if not p.is_file():
        raise ConfigError(f"{ctx} is not a file: {file_path}")
    if not os.access(p, os.R_OK):
        raise ConfigError(f"{ctx} file not readable: {file_path}")


def _validate_includes_object(includes: Any) -> None:
    """Validate production.includes structure.

    Required shape:
      includes: {}  (empty -> include everything)
      or:
      includes: {
        "label": [start, end],
        "label2": [[start, end], [start, end]]
      }

    Notes:
    - JSON objects can't have duplicate keys. If you want multiple ranges with the same
      label, use a list-of-ranges under that label.
    """
    if not isinstance(includes, dict):
        raise ConfigError(
            "production.includes must be an object (e.g. {} or {\"label\": [start,end]})"
        )

    for label, spec in includes.items():
        if not isinstance(spec, list):
            raise ConfigError(f"production.includes.{label} must be an array")

        # spec can be [start,end] OR [[start,end], ...]
        if len(spec) == 2 and not any(isinstance(x, list) for x in spec):
            to_float(spec[0], f"production.includes.{label}[0]")
            to_float(spec[1], f"production.includes.{label}[1]")
            continue

        if not spec:
            raise ConfigError(
                f"production.includes.{label} cannot be an empty array (use {{}} for include-all)"
            )

        for i, pair in enumerate(spec):
            if not (isinstance(pair, list) and len(pair) == 2):
                raise ConfigError(f"production.includes.{label}[{i}] must be [start, end]")
            to_float(pair[0], f"production.includes.{label}[{i}][0]")
            to_float(pair[1], f"production.includes.{label}[{i}][1]")


def _parse_timeline_events(raw_events: Any, ctx: str) -> List[TimelineEvent]:
    if raw_events is None:
        return []
    if not isinstance(raw_events, list):
        raise ConfigError(f"{ctx} must be an array")

    events: List[TimelineEvent] = []
    for i, ev in enumerate(raw_events):
        if not isinstance(ev, dict):
            raise ConfigError(f"{ctx}[{i}] must be an object")
        if 'at' not in ev:
            raise ConfigError(f"{ctx}[{i}] missing 'at'")
        at = to_float(ev['at'], f"{ctx}[{i}].at")

        has_change = False
        z_index = None
        pos = None
        scale_pct = None
        crop = None

        if 'z_index' in ev:
            z_index = to_float(ev['z_index'], f"{ctx}[{i}].z_index")
            has_change = True
        if 'position' in ev:
            pos = parse_position(ev['position'], f"{ctx}[{i}].position")
            has_change = True
        if 'scale' in ev:
            scale_pct = parse_scale(ev['scale'], f"{ctx}[{i}].scale")
            has_change = True
        if 'crop' in ev:
            crop = parse_crop(ev['crop'], f"{ctx}[{i}].crop")
            has_change = True

        if not has_change:
            raise ConfigError(
                f"{ctx}[{i}] must include at least one of 'z_index', 'position', 'scale', or 'crop'"
            )

        events.append(TimelineEvent(at=at, z_index=z_index, position=pos, scale_pct=scale_pct, crop=crop))

    # Stable sort by time
    events.sort(key=lambda e: e.at)
    return events


def load_config(config_path: str) -> Config:
    """Load and validate JSON config file."""
    _validate_file_readable(config_path, ctx='Config')

    with open(config_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in {config_path}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError("Config root must be an object")

    # master_audio
    if 'master_audio' not in data:
        raise ConfigError("Config missing 'master_audio' section")
    ma = data['master_audio']
    if not isinstance(ma, dict):
        raise ConfigError("master_audio must be an object")
    if 'file' not in ma:
        raise ConfigError("master_audio missing 'file'")
    if 'clap_time' not in ma:
        raise ConfigError("master_audio missing 'clap_time'")

    master_file = str(ma['file'])
    master_clap = to_float(ma['clap_time'], 'master_audio.clap_time')

    # video_sources
    if 'video_sources' not in data or not data['video_sources']:
        raise ConfigError("Config missing 'video_sources' (need at least one)")
    vs = data['video_sources']
    if not isinstance(vs, dict):
        raise ConfigError("video_sources must be an object with named sources")

    video_sources: List[VideoSource] = []
    for name, src in vs.items():
        if not isinstance(src, dict):
            raise ConfigError(f"video_sources.{name} must be an object")
        if 'file' not in src:
            raise ConfigError(f"video_sources.{name} missing 'file'")
        if 'clap_time' not in src:
            raise ConfigError(f"video_sources.{name} missing 'clap_time'")
        if 'z_index' not in src:
            raise ConfigError(f"video_sources.{name} missing 'z_index'")

        file_path = str(src['file'])
        clap_time = to_float(src['clap_time'], f"video_sources.{name}.clap_time")
        z_index = to_float(src['z_index'], f"video_sources.{name}.z_index")

        pos_x, pos_y = parse_position(src.get('position', [0.0, 0.0]), f"video_sources.{name}.position")
        scale_pct = parse_scale(src.get('scale', 100.0), f"video_sources.{name}.scale")
        crop_l, crop_r, crop_t, crop_b = parse_crop(src.get('crop', [0.0, 0.0, 0.0, 0.0]), f"video_sources.{name}.crop")

        default_state = SourceState(
            z_index=z_index,
            position_x_pct=pos_x,
            position_y_pct=pos_y,
            scale_pct=scale_pct,
            crop_left_pct=crop_l,
            crop_right_pct=crop_r,
            crop_top_pct=crop_t,
            crop_bottom_pct=crop_b,
        )

        timeline = _parse_timeline_events(src.get('timeline'), ctx=f"video_sources.{name}.timeline")

        video_sources.append(
            VideoSource(
                name=name,
                file=file_path,
                clap_time=clap_time,
                default_state=default_state,
                timeline=timeline,
            )
        )

    # production
    if 'production' not in data:
        raise ConfigError("Config missing 'production' section")
    prod = data['production']
    if not isinstance(prod, dict):
        raise ConfigError("production must be an object")

    for req in ('output_file', 'start', 'end'):
        if req not in prod:
            raise ConfigError(f"production missing '{req}'")

    start = to_float(prod['start'], 'production.start')
    end = to_float(prod['end'], 'production.end')

    if end <= start:
        raise ConfigError(f"Invalid production range: start={start}, end={end} (end must be > start)")

    output_file = str(prod['output_file'])
    width = int(prod.get('width', 1920))
    height = int(prod.get('height', 1080))

    if 'includes' not in prod:
        raise ConfigError("production missing required 'includes' (use {} to include everything)")
    includes = prod.get('includes')
    _validate_includes_object(includes)

    cfg = Config(
        master_audio=MasterAudio(file=master_file, clap_time=master_clap),
        video_sources=video_sources,
        production=Production(
            start=start,
            end=end,
            output_file=output_file,
            width=width,
            height=height,
            includes=includes,
        ),
    )

    # File readability checks (keep consistent with old behavior: fail early)
    _validate_file_readable(cfg.master_audio.file, ctx='master_audio')
    for src in cfg.video_sources:
        _validate_file_readable(src.file, ctx=f"video_sources.{src.name}")

    return cfg
