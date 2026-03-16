from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class MasterAudio:
    file: str
    clap_time: float


@dataclass
class SourceState:
    z_index: float
    position_x_pct: float
    position_y_pct: float
    scale_pct: float
    crop_left_pct: float
    crop_right_pct: float
    crop_top_pct: float
    crop_bottom_pct: float


@dataclass(frozen=True)
class TimelineEvent:
    at: float
    z_index: Optional[float] = None
    position: Optional[Tuple[float, float]] = None  # (x_pct, y_pct)
    scale_pct: Optional[float] = None
    crop: Optional[Tuple[float, float, float, float]] = None  # (l,r,t,b)


@dataclass
class VideoSource:
    name: str
    file: str
    clap_time: float
    default_state: SourceState
    timeline: List[TimelineEvent]


@dataclass(frozen=True)
class Production:
    start: float
    end: float
    output_file: str
    width: int
    height: int
    includes: Dict


@dataclass(frozen=True)
class Config:
    master_audio: MasterAudio
    video_sources: List[VideoSource]  # preserves config order
    production: Production


@dataclass(frozen=True)
class IncludeRange:
    start: float
    end: float


@dataclass(frozen=True)
class StateSegment:
    start: float
    end: float
    state_by_source: Dict[str, SourceState]


@dataclass(frozen=True)
class Chunk:
    start: float  # absolute master-audio time
    end: float
    state_by_source: Dict[str, SourceState]

    @property
    def duration(self) -> float:
        return float(self.end - self.start)
