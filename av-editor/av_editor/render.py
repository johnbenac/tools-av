from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import load_config
from .errors import AVEditorError, ConfigError, FFmpegError
from .ffmpeg import ffmpeg_has_encoder, has_cuda_runtime, probe_duration, probe_resolution, run_command
from .models import Chunk, Config, SourceState, VideoSource
from .timeline import build_chunks, build_state_segments, parse_includes
from .util import safe_label


@dataclass(frozen=True)
class SourceMedia:
    name: str
    file: str
    clap_time: float
    offset: float
    order: int
    duration: float
    width: int
    height: int


@dataclass(frozen=True)
class EncoderPlan:
    use_cuda: bool
    video_codec_args: List[str]
    audio_codec_args: List[str]


def _compute_source_media(cfg: Config, *, verbose: bool) -> Dict[str, SourceMedia]:
    master_clap = cfg.master_audio.clap_time

    sources: Dict[str, SourceMedia] = {}
    for order, src in enumerate(cfg.video_sources):
        # offset definition matches original:
        # master_time = video_time + offset  =>  video_time = master_time - offset
        offset = master_clap - float(src.clap_time)
        duration = probe_duration(src.file, stream_type='v', verbose=verbose)
        w, h = probe_resolution(src.file)
        sources[src.name] = SourceMedia(
            name=src.name,
            file=src.file,
            clap_time=float(src.clap_time),
            offset=float(offset),
            order=order,
            duration=duration,
            width=w,
            height=h,
        )

    return sources


def _choose_encoder_plan(*, verbose: bool) -> EncoderPlan:
    """Select GPU vs CPU encoding.

    On machines with an NVIDIA driver (libcuda present) and ffmpeg NVENC support,
    we use NVENC + (optional) CUDA decode.

    In environments without CUDA (CI/containers), we fall back to libx264 so the
    tool remains runnable (and testable). This does not change the CLI interface.
    """
    cuda_ok = has_cuda_runtime()
    nvenc_ok = ffmpeg_has_encoder('h264_nvenc')

    use_cuda = bool(cuda_ok and nvenc_ok)

    if use_cuda:
        if verbose:
            print("\n🚀 GPU Acceleration enabled:")
            print("  • Hardware decode: CUDA")
            print("  • Hardware encode: NVENC (h264_nvenc)")
        video_codec_args = [
            '-c:v', 'h264_nvenc',
            '-preset', 'p4',
            '-cq', '19',
            '-b:v', '0',
            '-pix_fmt', 'yuv420p',
        ]
    else:
        if verbose:
            print("\n🐢 GPU Acceleration unavailable; using CPU (libx264).")
            if not cuda_ok:
                print("  • CUDA runtime not detected (libcuda.so.1 missing)")
            if not nvenc_ok:
                print("  • ffmpeg encoder h264_nvenc not detected")
        video_codec_args = [
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '19',
            '-pix_fmt', 'yuv420p',
        ]

    audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']

    return EncoderPlan(use_cuda=use_cuda, video_codec_args=video_codec_args, audio_codec_args=audio_codec_args)


def _build_filtergraph_for_batch(
    batch_chunks: List[Chunk],
    cfg: Config,
    sources_media: Dict[str, SourceMedia],
    *,
    output_width: int,
    output_height: int,
    input_index_map: Dict[Tuple[int, str], int],
    audio_index_map: Dict[int, int],
    delay_map: Dict[Tuple[int, str], float],
) -> Tuple[str, str, str]:
    """Return (filter_complex, final_v_label, final_a_label)."""
    filter_parts: List[str] = []
    seg_video_labels: List[str] = []
    seg_audio_labels: List[str] = []

    # Stable tie-breaker for equal z_index
    source_order = {name: sm.order for name, sm in sources_media.items()}

    for seg_idx, chunk in enumerate(batch_chunks):
        dur = chunk.duration
        bg_label = f"seg{seg_idx}_bg"
        filter_parts.append(f"color=c=black:s={output_width}x{output_height}:d={dur:.6f}[{bg_label}]")

        # Determine draw order by current state
        state = chunk.state_by_source
        draw_order = sorted(state.keys(), key=lambda n: (state[n].z_index, source_order.get(n, 0)))

        prev = bg_label
        for layer_idx, name in enumerate(draw_order):
            st: SourceState = state[name]
            safe = safe_label(name)
            clip_label = f"seg{seg_idx}_{safe}_clip"
            out_label = f"seg{seg_idx}_layer{layer_idx}"

            in_idx = input_index_map[(seg_idx, name)]
            delay = delay_map.get((seg_idx, name), 0.0)

            target_w = max(1, int(round(output_width * (st.scale_pct / 100.0))))
            target_h = max(1, int(round(output_height * (st.scale_pct / 100.0))))

            crop_left_px = int(target_w * (st.crop_left_pct / 100.0))
            crop_right_px = int(target_w * (st.crop_right_pct / 100.0))
            crop_top_px = int(target_h * (st.crop_top_pct / 100.0))
            crop_bottom_px = int(target_h * (st.crop_bottom_pct / 100.0))
            crop_w = max(1, target_w - crop_left_px - crop_right_px)
            crop_h = max(1, target_h - crop_top_px - crop_bottom_px)

            # Build chain. Trim first (after optional start pad), then scale/crop.
            chain = f"[{in_idx}:v]"
            if delay > 0.0005:
                chain += f"tpad=start_duration={delay:.6f}:start_mode=add:color=black,"
            chain += f"trim=start=0:end={dur:.6f},"
            chain += f"scale={target_w}:{target_h},setsar=1,"
            chain += f"crop=w={crop_w}:h={crop_h}:x={crop_left_px}:y={crop_top_px},"
            chain += f"setpts=PTS-STARTPTS[{clip_label}]"
            filter_parts.append(chain)

            overlay_x = int(round(output_width * (st.position_x_pct / 100.0))) + crop_left_px
            overlay_y = int(round(output_height * (st.position_y_pct / 100.0))) + crop_top_px

            filter_parts.append(f"[{prev}][{clip_label}]overlay={overlay_x}:{overlay_y}[{out_label}]")
            prev = out_label

        v_label = f"v{seg_idx}"
        filter_parts.append(f"[{prev}]format=yuv420p,setpts=PTS-STARTPTS[{v_label}]")
        seg_video_labels.append(v_label)

        a_idx = audio_index_map[seg_idx]
        a_label = f"a{seg_idx}"
        filter_parts.append(
            f"[{a_idx}:a]atrim=start=0:end={dur:.6f},asetpts=PTS-STARTPTS[{a_label}]"
        )
        seg_audio_labels.append(a_label)

    if len(batch_chunks) > 1:
        concat_in = ''.join(f"[{v}][{a}]" for v, a in zip(seg_video_labels, seg_audio_labels))
        filter_parts.append(f"{concat_in}concat=n={len(batch_chunks)}:v=1:a=1[vout][aout]")
        return ';'.join(filter_parts), 'vout', 'aout'

    return ';'.join(filter_parts), seg_video_labels[0], seg_audio_labels[0]


def _render_batch_to_file(
    batch_chunks: List[Chunk],
    cfg: Config,
    sources_media: Dict[str, SourceMedia],
    *,
    encoder: EncoderPlan,
    verbose: bool,
    dry_run: bool,
    output_path: Path,
) -> None:
    """Render a batch (one or more chunks) to a single output file."""

    master_file = cfg.master_audio.file
    out_w = cfg.production.width
    out_h = cfg.production.height

    cmd: List[str] = ['ffmpeg']
    if encoder.use_cuda:
        cmd.extend(['-hwaccel', 'cuda'])

    input_index_map: Dict[Tuple[int, str], int] = {}
    audio_index_map: Dict[int, int] = {}
    delay_map: Dict[Tuple[int, str], float] = {}

    input_idx = 0

    for seg_idx, chunk in enumerate(batch_chunks):
        seg_start = float(chunk.start)
        seg_dur = float(chunk.duration)

        for name, sm in sources_media.items():
            seek = seg_start - sm.offset
            delay = 0.0
            if seek > 0:
                cmd.extend(['-ss', f'{seek:.6f}'])
            else:
                delay = -seek
                # No -ss when negative; start from file beginning.
            cmd.extend(['-t', f'{seg_dur:.6f}', '-i', str(sm.file)])
            input_index_map[(seg_idx, name)] = input_idx
            delay_map[(seg_idx, name)] = delay
            input_idx += 1

        if seg_start > 0:
            cmd.extend(['-ss', f'{seg_start:.6f}'])
        cmd.extend(['-t', f'{seg_dur:.6f}', '-i', str(master_file)])
        audio_index_map[seg_idx] = input_idx
        input_idx += 1

    filter_complex, final_v, final_a = _build_filtergraph_for_batch(
        batch_chunks,
        cfg,
        sources_media,
        output_width=out_w,
        output_height=out_h,
        input_index_map=input_index_map,
        audio_index_map=audio_index_map,
        delay_map=delay_map,
    )

    cmd.extend(['-filter_complex', filter_complex])
    cmd.extend(['-map', f'[{final_v}]', '-map', f'[{final_a}]'])
    cmd.extend(encoder.video_codec_args)
    cmd.extend(encoder.audio_codec_args)
    cmd.extend(['-movflags', '+faststart'])

    cmd.extend(['-y', str(output_path)])

    run_command(cmd, verbose=verbose, dry_run=dry_run)


def _concat_mp4_files(inputs: List[Path], *, verbose: bool, dry_run: bool, output_path: Path) -> None:
    """Concatenate already-encoded MP4 files using the concat demuxer (stream copy)."""
    if len(inputs) == 1:
        # Nothing to do
        if not dry_run:
            inputs[0].rename(output_path)
        else:
            print(f"[DRY-RUN] Would move {inputs[0]} -> {output_path}")
        return

    # concat demuxer file
    list_file = output_path.parent / ('.av-editor-concat-' + next(tempfile._get_candidate_names()) + '.txt')
    content = ''.join(f"file '{p.as_posix()}'\n" for p in inputs)

    if verbose or dry_run:
        print(f"[INFO] Concat list file: {list_file}")

    if not dry_run:
        list_file.write_text(content, encoding='utf-8')

    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', str(list_file),
        '-c', 'copy',
        '-movflags', '+faststart',
        '-y',
        str(output_path),
    ]

    try:
        run_command(cmd, verbose=verbose, dry_run=dry_run)
    finally:
        if not dry_run and list_file.exists():
            list_file.unlink()


def render(config_path: str, *, verbose: bool = False, dry_run: bool = False, force: bool = False) -> None:
    cfg = load_config(config_path)

    # Probe master audio
    master_duration = probe_duration(cfg.master_audio.file, stream_type='a', verbose=verbose)

    print(f"Master audio: {cfg.master_audio.file}")
    print(f"  Duration: {master_duration:.3f}s")
    print(f"  Clap at: {cfg.master_audio.clap_time:.3f}s")

    sources_media = _compute_source_media(cfg, verbose=verbose)

    print("\nVideo sources:")
    for src in cfg.video_sources:
        sm = sources_media[src.name]
        print(f"  [{src.name}] {Path(sm.file).name}")
        print(f"    Resolution: {sm.width}x{sm.height}")
        print(f"    Duration: {sm.duration:.3f}s")
        print(f"    Clap at: {sm.clap_time:.3f}s")
        print(f"    Sync offset: {sm.offset:+.3f}s")
        st = src.default_state
        print(
            f"    Default z_index: {st.z_index:g}\n"
            f"    Placement: x={st.position_x_pct:.1f}%, y={st.position_y_pct:.1f}%, scale={st.scale_pct:.1f}%\n"
            f"    Crop: l={st.crop_left_pct:.1f}%, r={st.crop_right_pct:.1f}%, t={st.crop_top_pct:.1f}%, b={st.crop_bottom_pct:.1f}%"
        )
        if src.timeline:
            print(f"    Timeline events: {len(src.timeline)}")

    prod = cfg.production
    production_start = float(prod.start)
    production_end = float(prod.end)
    production_duration = production_end - production_start

    if production_duration <= 0:
        raise ConfigError(
            f"Invalid production range: start={production_start}, end={production_end} "
            f"(duration would be {production_duration:.3f}s)"
        )

    include_ranges = parse_includes(prod.includes, production_start=production_start, production_end=production_end, verbose=verbose)
    total_duration = sum(r.end - r.start for r in include_ranges)

    print("\nProduction:")
    print(f"  Window start in master audio: {production_start:.3f}s")
    print(f"  Window end in master audio:   {production_end:.3f}s")
    print(f"  Window duration:             {production_duration:.3f}s")
    print(f"  Resolution: {prod.width}x{prod.height}")
    print(f"  Output file: {prod.output_file}")

    if len(include_ranges) == 1 and include_ranges[0].start == production_start and include_ranges[0].end == production_end:
        print("  Includes: full window (production.includes is empty)")
    else:
        print(f"  Includes: {len(include_ranges)} segment(s), total output duration {total_duration:.3f}s")
        for i, r in enumerate(include_ranges, 1):
            print(f"    {i:2d}. {r.start:.3f}s - {r.end:.3f}s  ({(r.end - r.start):.3f}s)")

    output_path = Path(prod.output_file)
    if output_path.exists() and not force:
        raise AVEditorError(f"Output file exists: {output_path}\nUse --force to overwrite")

    # Compute state segments and final chunks
    state_segments = build_state_segments(cfg.video_sources, production_start=production_start, production_end=production_end, verbose=verbose)
    chunks = build_chunks(state_segments, include_ranges)

    if not chunks:
        raise AVEditorError("No output chunks produced (includes may be empty after clipping)")

    if verbose:
        print(f"\n[INFO] Output will be rendered in {len(chunks)} chunk(s):")
        for i, c in enumerate(chunks, 1):
            print(f"  {i:3d}. {c.start:.3f}s - {c.end:.3f}s  ({c.duration:.3f}s)")

    encoder = _choose_encoder_plan(verbose=verbose)

    # Work directory for intermediate files
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix='.av-editor-work-', dir=str(output_path.parent)))

    # Final output is written atomically via temp file in output dir
    final_tmp = output_path.parent / ('.av-editor-tmp-' + next(tempfile._get_candidate_names()) + output_path.suffix)

    # Batching strategy: limit command/input size while keeping overhead low.
    # Each chunk needs (num_sources + 1) inputs.
    num_sources = len(cfg.video_sources)
    max_inputs = 50  # conservative
    max_chunks_per_batch = max(1, max_inputs // (num_sources + 1))

    batch_files: List[Path] = []

    try:
        for batch_start in range(0, len(chunks), max_chunks_per_batch):
            batch = chunks[batch_start: batch_start + max_chunks_per_batch]
            batch_idx = batch_start // max_chunks_per_batch
            batch_out = work_dir / f"batch_{batch_idx:04d}.mp4"

            if verbose:
                print(f"\n[INFO] Rendering batch {batch_idx} with {len(batch)} chunk(s) -> {batch_out.name}")

            _render_batch_to_file(
                batch,
                cfg,
                sources_media,
                encoder=encoder,
                verbose=verbose,
                dry_run=dry_run,
                output_path=batch_out,
            )

            batch_files.append(batch_out)

        # Concat batches (or move single batch) into final temp output
        if verbose:
            print("\n[INFO] Finalizing output...")

        _concat_mp4_files(batch_files, verbose=verbose, dry_run=dry_run, output_path=final_tmp)

        if not dry_run:
            # Atomic rename
            if output_path.exists() and force:
                output_path.unlink()
            final_tmp.rename(output_path)
            print(f"\n✓ Rendered: {output_path}")
        else:
            print(f"\n[DRY-RUN] Would write final output to: {output_path}")

    finally:
        # Cleanup work dir
        if dry_run:
            # Don't delete in dry-run so user can inspect planned paths.
            return
        try:
            for p in work_dir.glob('*'):
                try:
                    p.unlink()
                except Exception:
                    pass
            work_dir.rmdir()
        except Exception:
            pass
