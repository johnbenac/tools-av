# av-editor — AI Authoring Context

## What this tool does

`av-editor` takes a JSON config and uses ffmpeg to composite multiple video sources into a single output. It syncs all sources to a master audio track using clapboard timestamps.

## Running a render

```bash
/opt/tools-av/av-editor/av-editor render /path/to/config.json -v --force
```

## Time model — the most important concept

All times in the config (`production.start`, `production.end`, timeline `at` values) are in **master audio absolute time**: seconds from the start of the master audio file.

The clap times synchronize sources to master audio:
```
sync_offset = master_clap_time - source_clap_time
source is seeked to: master_time - sync_offset
```

To convert "N seconds after the clapboard" → config time:
```
config_time = master_clap_time + N
```

## Config fields

### master_audio
- `file`: path to audio file
- `clap_time`: timestamp of clapboard in that file

### video_sources (named dict)
Each source requires:
- `file`: path to video
- `clap_time`: timestamp of clapboard in that video
- `z_index`: draw order (higher = in front)

Optional (all default to full-canvas, no crop):
- `position`: `[x_pct, y_pct]` — top-left of the scaled video on canvas. Can be negative.
- `scale`: percentage of output canvas size. Default `100`.
- `crop`: `[left, right, top, bottom]` — percentage of the *scaled* video to remove from each edge.
- `timeline`: list of `{at, z_index?, position?, scale?, crop?}` events. State persists — only named keys change.

### production
- `start`, `end`: master audio absolute time
- `output_file`, `width`, `height`
- `includes`: `{}` for full window, or `{"label": [start, end], ...}` for a cut list

## Key mechanics

### Position + crop interaction
Crop is applied after scale. The overlay position accounts for the crop offset:
```
overlay_x = (position_x_pct / 100) * output_width + crop_left_px
```
To place a cropped video flush at the canvas left edge, use `position_x = -crop_left_pct`. Example — central third of a full-res source, placed on the left:
```json
"position": [-33.333, 0], "scale": 100, "crop": [33.333, 33.333, 0, 0]
```

### Hiding a source with z_index
Sources cannot be removed mid-render. To hide one, keep its `z_index` below a full-canvas source (e.g. default `z_index: -1` while background is `z_index: 1`). Use timeline events to raise/lower z_index at the desired times.

### Clean cutover pattern
To swap to a different full-frame camera for a window, set the alt camera's default `z_index` below the background (e.g. `-1`), raise it above (e.g. `2`) at the start of the window, and lower it back at the end. No compositing — the background is simply covered by a full-canvas source at higher z.

### Timeline event timing
`at` is master audio absolute time. Always compute: `at = master_clap_time + seconds_after_clap`.

## Media files location

mozvision 1_intro takes: `/media/Parure/TOOO_video/mozvision/1_intro/`

File naming pattern: `take_N_<source>.mkv/.MOV/.mka`

Sources in each take:
- `take_N_MVI_XXXX.MOV` — Canon camera
- `take_N_ugreen_1.mkv`, `take_N_ugreen_2.mkv` — UGreen cameras
- `take_N_cam_0_3_1.mkv` — webcam
- `take_N_audio_mic_card5_dev0.mka` — preferred master audio (mic card 5)
- `take_N_combined_*.mkv` — pre-merged video+audio versions
