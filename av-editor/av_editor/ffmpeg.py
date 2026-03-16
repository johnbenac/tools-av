from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .errors import FFmpegError


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: Optional[int] = None
    height: Optional[int] = None


def run_command(cmd: List[str], *, verbose: bool = False, dry_run: bool = False) -> str:
    """Run a command and return stdout.

    Raises FFmpegError on failure.
    """
    if verbose or dry_run:
        cmd_str = ' '.join(cmd)
        if len(cmd_str) > 140:
            print(f"[CMD] {cmd_str[:140]}...")
        else:
            print(f"[CMD] {cmd_str}")

    if dry_run:
        return ""

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return (result.stdout or "").strip()
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise FFmpegError(f"Command failed: {' '.join(cmd)}\n{stderr}") from e


def ffmpeg_has_encoder(encoder_name: str) -> bool:
    try:
        out = run_command(['ffmpeg', '-hide_banner', '-encoders'], verbose=False, dry_run=False)
    except FFmpegError:
        return False
    return f" {encoder_name} " in out


def probe_duration(file_path: str, *, stream_type: Optional[str] = None, verbose: bool = False) -> float:
    """Get duration of a file.

    Prefer stream duration when stream_type provided ('a' or 'v'), fallback to format duration.
    """
    p = str(file_path)

    if stream_type:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', f'{stream_type}:0',
            '-show_entries', 'stream=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            p,
        ]
        try:
            out = run_command(cmd)
            if out and out != 'N/A':
                dur = float(out)
                if dur > 0:
                    if verbose:
                        print(f"[INFO] {Path(p).name}: {stream_type} stream duration = {dur:.3f}s")
                    return dur
        except Exception:
            pass

    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        p,
    ]
    out = run_command(cmd)
    if out and out != 'N/A':
        dur = float(out)
        if verbose:
            print(f"[INFO] {Path(p).name}: format duration = {dur:.3f}s")
        return dur

    raise FFmpegError(f"Could not determine duration for {file_path}")


def probe_resolution(file_path: str) -> Tuple[int, int]:
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        str(file_path),
    ]
    out = run_command(cmd)
    data = json.loads(out)
    streams = data.get('streams') or []
    if not streams:
        raise FFmpegError(f"Could not determine resolution for {file_path}")
    s0 = streams[0]
    w = s0.get('width')
    h = s0.get('height')
    if not (w and h):
        raise FFmpegError(f"Could not determine resolution for {file_path}")
    return int(w), int(h)


def has_cuda_runtime() -> bool:
    """Heuristic: can we load libcuda.so.1?

    This is more reliable than checking encoder lists alone, especially in headless
    environments (CI, containers) where ffmpeg might list NVENC but it cannot
    actually initialize.
    """
    try:
        import ctypes

        ctypes.CDLL('libcuda.so.1')
        return True
    except Exception:
        return False
