from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .errors import ConfigError
from .models import Chunk, IncludeRange, SourceState, StateSegment, TimelineEvent, VideoSource
from .util import normalize_time, to_float


def parse_includes(includes: Dict[str, Any], *, production_start: float, production_end: float, verbose: bool = False) -> List[IncludeRange]:
    """Turn production.includes into a sorted, merged list of ranges.

    - Empty {} => include full [production_start, production_end]
    - Non-empty => include union of the specified ranges (clipped to start/end)

    Input format:
      includes: {
        "label": [start, end],
        "label2": [[start, end], [start, end]]
      }

    Times are in absolute master-audio seconds.
    """
    if includes is None:
        raise ConfigError("production.includes is required (use {} to include everything)")
    if not isinstance(includes, dict):
        raise ConfigError("production.includes must be an object")

    if len(includes) == 0:
        return [IncludeRange(start=production_start, end=production_end)]

    raw: List[Tuple[str, float, float]] = []
    for label, spec in includes.items():
        if not isinstance(spec, list):
            raise ConfigError(f"production.includes.{label} must be an array")

        if len(spec) == 2 and not any(isinstance(x, list) for x in spec):
            s = to_float(spec[0], f"production.includes.{label}[0]")
            e = to_float(spec[1], f"production.includes.{label}[1]")
            raw.append((label, s, e))
            continue

        for i, pair in enumerate(spec):
            if not (isinstance(pair, list) and len(pair) == 2):
                raise ConfigError(f"production.includes.{label}[{i}] must be [start, end]")
            s = to_float(pair[0], f"production.includes.{label}[{i}][0]")
            e = to_float(pair[1], f"production.includes.{label}[{i}][1]")
            raw.append((label, s, e))

    # Clip and normalize
    clipped: List[IncludeRange] = []
    for label, s, e in raw:
        if e < s:
            raise ConfigError(f"Invalid includes range for label {label!r}: start {s} > end {e}")

        cs = max(production_start, s)
        ce = min(production_end, e)
        if ce <= cs:
            if verbose:
                print(
                    f"[WARN] Dropping includes range {label!r} [{s:.3f}, {e:.3f}] "
                    f"(outside production window [{production_start:.3f}, {production_end:.3f}])"
                )
            continue

        if verbose and (cs != s or ce != e):
            print(
                f"[INFO] Clipped includes range {label!r} [{s:.3f}, {e:.3f}] -> [{cs:.3f}, {ce:.3f}]"
            )
        clipped.append(IncludeRange(start=cs, end=ce))

    if not clipped:
        raise ConfigError("production.includes produced no usable ranges (all were empty/outside start..end)")

    clipped.sort(key=lambda r: (r.start, r.end))

    # Merge overlaps/touching
    merged: List[IncludeRange] = []
    for r in clipped:
        if not merged:
            merged.append(r)
            continue
        prev = merged[-1]
        if r.start <= prev.end:
            merged[-1] = IncludeRange(start=prev.start, end=max(prev.end, r.end))
        else:
            merged.append(r)

    return merged


def _apply_event_to_state(state: SourceState, ev: TimelineEvent) -> None:
    if ev.z_index is not None:
        state.z_index = float(ev.z_index)
    if ev.position is not None:
        state.position_x_pct = float(ev.position[0])
        state.position_y_pct = float(ev.position[1])
    if ev.scale_pct is not None:
        state.scale_pct = float(ev.scale_pct)
    if ev.crop is not None:
        state.crop_left_pct = float(ev.crop[0])
        state.crop_right_pct = float(ev.crop[1])
        state.crop_top_pct = float(ev.crop[2])
        state.crop_bottom_pct = float(ev.crop[3])


def build_state_segments(
    sources: List[VideoSource],
    *,
    production_start: float,
    production_end: float,
    verbose: bool = False,
) -> List[StateSegment]:
    """Build segments where *all* source states are constant.

    Timeline semantics:
    - Defaults apply at all times.
    - Timeline events apply at their exact `at` time and persist.

    Returns absolute-time segments in [production_start, production_end].
    """

    # Clone default states
    state_by_source: Dict[str, SourceState] = {
        s.name: SourceState(**vars(s.default_state)) for s in sources
    }

    # Build a global event index: time -> list of (source_name, event)
    events_by_time: Dict[float, List[Tuple[str, TimelineEvent]]] = {}
    for src in sources:
        for ev in src.timeline:
            if ev.at > production_end:
                break
            t = normalize_time(ev.at)
            events_by_time.setdefault(t, []).append((src.name, ev))

    # Deterministic ordering for events at same timestamp: preserve source order
    source_order = {src.name: i for i, src in enumerate(sources)}
    for t, items in events_by_time.items():
        items.sort(key=lambda pair: source_order.get(pair[0], 0))

    # Establish initial state at production_start (apply events <= start)
    for t in sorted(events_by_time.keys()):
        if t > normalize_time(production_start):
            break
        for name, ev in events_by_time[t]:
            _apply_event_to_state(state_by_source[name], ev)

    # Build change points strictly inside (start, end)
    change_times = [t for t in sorted(events_by_time.keys()) if normalize_time(production_start) < t < normalize_time(production_end)]

    # Segment boundaries: start, all change times, end
    boundaries = [normalize_time(production_start)] + change_times + [normalize_time(production_end)]

    segments: List[StateSegment] = []

    # For each boundary interval, record state snapshot
    current_time = boundaries[0]
    for next_time in boundaries[1:]:
        if next_time <= current_time:
            continue
        snapshot = {name: SourceState(**vars(st)) for name, st in state_by_source.items()}
        segments.append(StateSegment(start=float(current_time), end=float(next_time), state_by_source=snapshot))

        # Apply events at next_time for subsequent segments
        if next_time in events_by_time:
            for name, ev in events_by_time[next_time]:
                _apply_event_to_state(state_by_source[name], ev)

        current_time = next_time

    if verbose:
        print(f"[INFO] Built {len(segments)} state segment(s) over production window")

    return segments


def build_chunks(
    state_segments: List[StateSegment],
    include_ranges: List[IncludeRange],
) -> List[Chunk]:
    """Intersect include ranges with state segments."""
    chunks: List[Chunk] = []

    for inc in include_ranges:
        for seg in state_segments:
            if seg.end <= inc.start:
                continue
            if seg.start >= inc.end:
                break
            s = max(seg.start, inc.start)
            e = min(seg.end, inc.end)
            if e <= s:
                continue
            chunks.append(Chunk(start=float(s), end=float(e), state_by_source=seg.state_by_source))

    # Chunks are already in chronological order because inputs are sorted
    return chunks
