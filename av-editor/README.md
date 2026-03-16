# av-editor (drop-in replacement)

This directory is a **drop-in replacement** for `/opt/tools-av/av-editor`.

## What changed (internals only)

The original implementation built one giant ffmpeg filtergraph and used `split` + `concat` to
stitch segments together.

That pattern can **explode memory usage** on long timelines, because ffmpeg has to buffer
frames from later branches until earlier branches finish.

This replacement renders in **timeline chunks**:

- A **chunk** is a span of time where *every source* has a constant state
  (`z_index`, `position`, `scale`, `crop`).
- Each chunk is rendered by seeking inputs with `-ss/-t`, compositing once, and writing output.
- Chunks are grouped into small **batches**, and batches are concatenated with the concat demuxer.

Result: memory stays roughly flat with timeline length.

## CLI (unchanged)

```bash
av-editor render <config.json> [-v] [--dry-run] [--force]
av-editor <config.json> [-v] [--dry-run] [--force]   # legacy shorthand
av-editor --version
```

## Running tests

```bash
python3 -m unittest -v
```

---

## Authoring Guide

### Config structure

```json
{
  "master_audio": { ... },
  "video_sources": { "SourceName": { ... }, ... },
  "production": { ... }
}
```

---

### master_audio

```json
"master_audio": {
  "file": "/path/to/audio.mka",
  "clap_time": 15.611
}
```

`clap_time` is the timestamp (seconds) inside the audio file where the clapboard hits. All other times in the config are in **master audio absolute time** — meaning seconds measured from the start of the master audio file.

---

### video_sources

Each source is a named entry:

```json
"video_sources": {
  "MVI": {
    "file": "/path/to/video.MOV",
    "clap_time": 12.379,
    "z_index": 1,
    "position": [0, 0],
    "scale": 100,
    "crop": [0, 0, 0, 0],
    "timeline": []
  }
}
```

#### Clap sync

The renderer computes a sync offset per source:

```
sync_offset = master_clap_time - source_clap_time
```

When rendering a moment at master time `T`, the source is seeked to `T - sync_offset`. This aligns all sources so the clapboard hit is the same frame across every track.

#### Fields

| Field | Required | Default | Description |
|---|---|---|---|
| `file` | yes | — | Path to video file |
| `clap_time` | yes | — | Timestamp of clapboard hit in the source file (seconds) |
| `z_index` | yes | — | Draw order. Higher = in front. Sources with equal z_index are ordered by config order. |
| `position` | no | `[0, 0]` | `[x_pct, y_pct]` — top-left corner of the (scaled, pre-crop) video on the output canvas, as a percentage of output dimensions. Can be negative or >100 for off-canvas placement. |
| `scale` | no | `100` | Size of the source as a percentage of output dimensions. `100` = fill the canvas. |
| `crop` | no | `[0, 0, 0, 0]` | `[left, right, top, bottom]` — percentage of the *scaled* video to remove from each edge. Values 0–100; left+right < 100; top+bottom < 100. |
| `timeline` | no | `[]` | List of state-change events (see below). |

#### Position and crop interaction

Crop is applied **after** scale, but the overlay position accounts for crop offset:

```
overlay_x = (position_x_pct / 100) * output_width + crop_left_px
```

This means: if you crop the left side of a video, the visible content is shifted right on the canvas by the amount cropped. To counteract this and place the cropped content at the canvas left edge, use a negative `position_x` equal to `-crop_left_pct`.

**Example — show the central third of a 1920x1080 source on the left side of the canvas:**

```json
"position": [-33.333, 0],
"scale": 100,
"crop": [33.333, 33.333, 0, 0]
```

- Crop removes 33.3% from left and right → central 640px strip remains
- `position_x = -33.333%` → overlay_x = −640 + 640 = 0 (flush left)

#### z_index and hiding sources

A source at `z_index` lower than a full-canvas source above it is effectively hidden. This is the preferred way to show/hide a source over time:

- Set the source's default `z_index` to something low (e.g. `-1`) while the background source is at `1`.
- Use a timeline event to raise `z_index` to `2` (or any value above the background) when you want it visible.
- Use another timeline event to lower it back when you want it hidden.

**No source is ever fully removed from the render** — every source is composited in every chunk. Hiding works by stacking order only.

---

### Timeline events

Timeline events change one or more source properties at a point in master audio absolute time. **State persists** — only named keys are updated; everything else keeps its current value.

```json
"timeline": [
  {"at": 85.611, "z_index": 2},
  {"at": 85.611, "position": [0, 0]},
  {"at": 120.611, "z_index": -1, "position": [-33.333, 0]}
]
```

`at` is in **master audio absolute time** (not relative to the clap). To convert from "N seconds after the clapboard":

```
at = master_clap_time + N
```

Available keys per event (at least one required): `z_index`, `position`, `scale`, `crop`.

---

### production

```json
"production": {
  "start": 15.611,
  "end": 149.611,
  "output_file": "/tmp/output.mp4",
  "width": 1920,
  "height": 1080,
  "includes": {}
}
```

`start` and `end` are in **master audio absolute time**. Typically `start = master_clap_time` and `end = master_clap_time + desired_duration`.

#### includes

Use `{}` to include the full production window. To select subranges (e.g. for a cut list), use named segments:

```json
"includes": {
  "intro":  [15.611, 17.811],
  "middle": [53.411, 96.211],
  "finale": [128.811, 149.611]
}
```

Times are in master audio absolute time. Segments are concatenated in the order listed.

---

### Common patterns

#### Single camera + master audio, full take

```json
{
  "master_audio": {"file": "audio.mka", "clap_time": 15.6},
  "video_sources": {
    "CAM": {"file": "camera.MOV", "clap_time": 12.4, "z_index": 1}
  },
  "production": {
    "start": 15.6, "end": 149.6,
    "output_file": "out.mp4", "width": 1920, "height": 1080,
    "includes": {}
  }
}
```

#### Clean cutover to a different camera for a window

Set the alternate camera's default `z_index` below the background, then raise it above during the desired window. The background source is completely replaced — no compositing, just a full-frame swap:

```json
"cam": {
  "file": "cam.mkv",
  "clap_time": 15.6,
  "z_index": -1,
  "position": [0, 0],
  "scale": 100,
  "timeline": [
    {"at": 59.011, "z_index": 2},
    {"at": 76.011, "z_index": -1}
  ]
}
```

The background source (z_index: 1) is fully covered during the window because `cam` is full-canvas at z_index: 2.

#### Picture-in-picture that appears for a window

Set the PIP source's default `z_index` below the background, then use timeline events to raise/lower it:

```json
"pip_cam": {
  "file": "pip.mkv",
  "clap_time": 16.0,
  "z_index": -1,
  "position": [-33.333, 0],
  "scale": 100,
  "crop": [33.333, 33.333, 0, 0],
  "timeline": [
    {"at": 85.611, "z_index": 2},
    {"at": 120.611, "z_index": -1}
  ]
}
```
