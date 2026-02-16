#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-/tmp/av-editor-color-demo}"

DURATION="10"
WIDTH="960"
HEIGHT="540"
FPS="30"
CLAP_TIME="1.5"
CLAP_MS="1500"

mkdir -p "$OUT_DIR"

MASTER_AUDIO="$OUT_DIR/master_audio.m4a"
RED_VIDEO="$OUT_DIR/red.mp4"
GREEN_VIDEO="$OUT_DIR/green.mp4"
BLUE_VIDEO="$OUT_DIR/blue.mp4"

CONFIG_01="$OUT_DIR/demo_01_full_timeline.json"
CONFIG_02="$OUT_DIR/demo_02_includes_cutlist.json"
CONFIG_03="$OUT_DIR/demo_03_state_persistence.json"

OUT_01="$OUT_DIR/demo_01_full_timeline.mp4"
OUT_02="$OUT_DIR/demo_02_includes_cutlist.mp4"
OUT_03="$OUT_DIR/demo_03_state_persistence.mp4"

echo "[1/5] Generating demo audio (low hum + clap pop at ${CLAP_TIME}s)..."
ffmpeg -v error -y \
  -f lavfi -i "sine=frequency=110:sample_rate=48000:duration=${DURATION}" \
  -f lavfi -i "sine=frequency=1800:sample_rate=48000:duration=0.03" \
  -filter_complex "[0:a]volume=0.07[hum];[1:a]volume=0.9,adelay=${CLAP_MS}|${CLAP_MS}[pop];[hum][pop]amix=inputs=2:normalize=0[a]" \
  -map "[a]" \
  -c:a aac -b:a 192k -movflags +faststart \
  "$MASTER_AUDIO"

echo "[2/5] Generating color video sources..."
ffmpeg -v error -y -f lavfi -i "color=c=red:s=${WIDTH}x${HEIGHT}:r=${FPS}:d=${DURATION}" \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart "$RED_VIDEO"
ffmpeg -v error -y -f lavfi -i "color=c=green:s=${WIDTH}x${HEIGHT}:r=${FPS}:d=${DURATION}" \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart "$GREEN_VIDEO"
ffmpeg -v error -y -f lavfi -i "color=c=blue:s=${WIDTH}x${HEIGHT}:r=${FPS}:d=${DURATION}" \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart "$BLUE_VIDEO"

echo "[3/5] Writing demo JSON configs..."
cat > "$CONFIG_01" <<EOF
{
  "master_audio": {
    "file": "$MASTER_AUDIO",
    "clap_time": $CLAP_TIME
  },
  "video_sources": {
    "red": {
      "file": "$RED_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 0,
      "position": [0, 0],
      "scale": 100
    },
    "green": {
      "file": "$GREEN_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 2,
      "position": [0, 0],
      "scale": 35,
      "timeline": [
        {"at": 2.0, "position": [55, 5]},
        {"at": 3.0, "scale": 50},
        {"at": 4.0, "z_index": -1},
        {"at": 5.0, "z_index": 3, "position": [0, 55], "scale": 45},
        {"at": 7.0, "position": [25, 25], "scale": 30}
      ]
    },
    "blue": {
      "file": "$BLUE_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 1,
      "position": [65, 65],
      "scale": 35,
      "timeline": [
        {"at": 1.0, "z_index": 4},
        {"at": 2.5, "position": [65, 0], "scale": 25},
        {"at": 4.5, "z_index": 0},
        {"at": 6.0, "z_index": 5, "position": [65, 65], "scale": 30},
        {"at": 8.0, "z_index": -2}
      ]
    }
  },
  "production": {
    "start": 0.0,
    "end": 10.0,
    "output_file": "$OUT_01",
    "width": $WIDTH,
    "height": $HEIGHT,
    "includes": {}
  }
}
EOF

cat > "$CONFIG_02" <<EOF
{
  "master_audio": {
    "file": "$MASTER_AUDIO",
    "clap_time": $CLAP_TIME
  },
  "video_sources": {
    "red": {
      "file": "$RED_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 0,
      "position": [0, 0],
      "scale": 100
    },
    "green": {
      "file": "$GREEN_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 2,
      "position": [0, 0],
      "scale": 35,
      "timeline": [
        {"at": 2.0, "position": [55, 5]},
        {"at": 3.0, "scale": 50},
        {"at": 4.0, "z_index": -1},
        {"at": 5.0, "z_index": 3, "position": [0, 55], "scale": 45},
        {"at": 7.0, "position": [25, 25], "scale": 30}
      ]
    },
    "blue": {
      "file": "$BLUE_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 1,
      "position": [65, 65],
      "scale": 35,
      "timeline": [
        {"at": 1.0, "z_index": 4},
        {"at": 2.5, "position": [65, 0], "scale": 25},
        {"at": 4.5, "z_index": 0},
        {"at": 6.0, "z_index": 5, "position": [65, 65], "scale": 30},
        {"at": 8.0, "z_index": -2}
      ]
    }
  },
  "production": {
    "start": 0.0,
    "end": 10.0,
    "output_file": "$OUT_02",
    "width": $WIDTH,
    "height": $HEIGHT,
    "includes": {
      "intro": [0.0, 2.2],
      "middle": [[3.8, 6.2]],
      "finale": [8.0, 10.0]
    }
  }
}
EOF

cat > "$CONFIG_03" <<EOF
{
  "master_audio": {
    "file": "$MASTER_AUDIO",
    "clap_time": $CLAP_TIME
  },
  "video_sources": {
    "red": {
      "file": "$RED_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 0,
      "position": [0, 0],
      "scale": 100
    },
    "green": {
      "file": "$GREEN_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 3,
      "position": [5, 5],
      "scale": 25,
      "timeline": [
        {"at": 2.0, "position": [70, 5]},
        {"at": 4.0, "scale": 45},
        {"at": 6.0, "z_index": -1},
        {"at": 8.0, "z_index": 3, "position": [35, 35], "scale": 30}
      ]
    },
    "blue": {
      "file": "$BLUE_VIDEO",
      "clap_time": $CLAP_TIME,
      "z_index": 1,
      "position": [65, 65],
      "scale": 30
    }
  },
  "production": {
    "start": 0.0,
    "end": 10.0,
    "output_file": "$OUT_03",
    "width": $WIDTH,
    "height": $HEIGHT,
    "includes": {}
  }
}
EOF

echo "[4/5] Demo configs:"
echo "  - $CONFIG_01"
echo "  - $CONFIG_02"
echo "  - $CONFIG_03"

cat <<EOF
[5/5] Next steps:
  /opt/tools-av/av-editor/av-editor render "$CONFIG_01" --force -v
  /opt/tools-av/av-editor/av-editor render "$CONFIG_02" --force -v
  /opt/tools-av/av-editor/av-editor render "$CONFIG_03" --force -v
EOF

