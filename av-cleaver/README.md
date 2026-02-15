# av-cleaver

Split audio from video, or merge them back together.

## Philosophy

**Keep it simple.** This tool handles the split → (you process) → merge workflow cleanly. All "processing" (effects, normalization, editing) happens externally. av-cleaver just splits and combines, predictably and safely.

**Fail fast on mismatches.** Duration validation is mandatory and non-negotiable. If your audio and video don't match, that's a problem upstream that needs fixing - not something to paper over.

## Installation

```bash
chmod +x /opt/tools-av/av-cleaver
```

Optionally symlink to your PATH:
```bash
ln -s /opt/tools-av/av-cleaver /usr/local/bin/av-cleaver
```

## Quick Start

**Extract audio from a video:**
```bash
av-cleaver split video.mp4
# Creates: video_audio.m4a (or .mp3, .flac, etc. based on source codec)
```

**Merge audio and video:**
```bash
av-cleaver merge video.mp4 audio.mp3
# Creates: video_merged.mp4
# Validates durations match (within 0.1s tolerance)
```

## Common Workflows

### Extract and convert audio format
```bash
# Extract as-is (fastest, no re-encode)
av-cleaver split video.mp4

# Convert to MP3
av-cleaver split video.mp4 -f mp3

# Convert to FLAC with custom output name
av-cleaver split video.mkv -f flac -o soundtrack.flac

# High-quality MP3
av-cleaver split video.mp4 -f mp3 -b 320k
```

### Replace audio in a video
```bash
# 1. Extract original audio
av-cleaver split original.mp4

# 2. Process audio externally (Audacity, ffmpeg filters, whatever)
# ... your processing here ...

# 3. Merge processed audio back
av-cleaver merge original.mp4 processed_audio.mp3 -o final.mp4
```

### Preview before running
```bash
# Dry-run shows what would happen
av-cleaver split video.mp4 --dry-run -v
av-cleaver merge video.mp4 audio.mp3 --dry-run -v
```

## Key Features

### Smart Codec Handling

**Split mode:**
- Default: Copies audio without re-encoding (fast!)
- Auto-selects container based on codec (AAC → .m4a, MP3 → .mp3, etc.)
- Only re-encodes when you specify a different format with `-f`

**Merge mode:**
- Default: Copies both streams when possible (fast!)
- Auto-transcodes audio if incompatible with output container
  - MP4 output + FLAC input → transcodes to AAC
  - MKV output + anything → copies (MKV accepts everything)
- Video always copies by default (no re-encode)

### Duration Validation

Before merging, av-cleaver checks that audio and video durations match:
- Default tolerance: **0.1 seconds**
- Adjustable with `-t` flag: `av-cleaver merge video.mp4 audio.mp3 -t 0.5`
- **No bypass option** - if durations don't match, fix the source files

Why? Duration mismatches usually mean something went wrong upstream (wrong audio file, incomplete render, encoding issue). Merging mismatched streams produces bad output. Better to fail and fix the problem.

### Container Compatibility

av-cleaver knows which codecs work in which containers and handles transcoding automatically:

| Container | Compatible Audio Codecs | Auto-transcodes to |
|-----------|-------------------------|-------------------|
| MP4/MOV   | AAC, MP3, AC3          | AAC               |
| MKV       | Almost everything      | (copies)          |
| WebM      | Opus, Vorbis           | Opus              |
| AVI       | MP3, AC3               | MP3               |

You don't need to think about this - just specify your output filename and av-cleaver handles it.

## Options Reference

### Split Mode
```
av-cleaver split <video_file> [options]

  -o, --output FILE      Output filename
  -f, --format FORMAT    Audio format: mp3, aac, flac, wav, ogg, opus
  -b, --bitrate RATE     Bitrate for re-encoding (e.g., 192k, 320k)
  -c, --copy             Copy audio codec without re-encoding (default)
  -r, --re-encode        Force re-encoding even when format matches
  -v, --verbose          Show decisions and ffmpeg commands
  --dry-run              Preview without executing
  --force                Overwrite existing output file
  -h, --help             Show help
```

### Merge Mode
```
av-cleaver merge <video_file> <audio_file> [options]

  -o, --output FILE       Output filename
  -t, --tolerance SECS    Duration tolerance in seconds (default: 0.1)
  -c, --video-codec CODEC Video codec: copy, h264, h265, vp9 (default: copy)
  -v, --verbose           Show decisions and ffmpeg commands
  --dry-run               Preview without executing
  --force                 Overwrite existing output file
  -h, --help              Show help
```

## Exit Codes

- **0**: Success
- **1**: General error (missing file, bad arguments, ffmpeg failure)
- **2**: Duration mismatch (merge only)

Useful for scripts:
```bash
if av-cleaver merge video.mp4 audio.mp3; then
    echo "Success!"
else
    echo "Failed with exit code $?"
fi
```

## Examples

**Basic extraction:**
```bash
av-cleaver split recording.mp4
# Output: recording_audio.m4a (or .mp3, .flac depending on source)
```

**Convert to specific format:**
```bash
av-cleaver split video.mkv -f mp3 -o output.mp3
```

**High-quality extraction:**
```bash
av-cleaver split source.mp4 -f flac -o lossless.flac
```

**Basic merge:**
```bash
av-cleaver merge video.mp4 narration.mp3
# Output: video_merged.mp4
```

**Merge with custom tolerance:**
```bash
av-cleaver merge video.mp4 audio.flac -t 0.5
# Allows up to 0.5s duration difference
```

**Merge with custom output:**
```bash
av-cleaver merge video.mp4 audio.mp3 -o final_cut.mp4
```

**Force overwrite existing output:**
```bash
av-cleaver merge video.mp4 audio.mp3 -o output.mp4 --force
```

**Verbose mode (see what's happening):**
```bash
av-cleaver split video.mp4 -v
# Shows:
# [INFO] Copying audio as-is (aac)
# [CMD] ffmpeg -i video.mp4 -vn -acodec copy -map 0:a:0 -y /path/.av-cleaver-tmp-xyz123.m4a
# ✓ Audio extracted to: video_audio.m4a
```

## Troubleshooting

**"Duration mismatch" error when merging:**
- Check actual durations: `ffprobe -show_entries format=duration file.mp4`
- Your audio and video don't match - fix the source, don't force it
- If close but slightly off, adjust tolerance: `-t 0.5`

**"No audio stream found":**
- Input file has no audio track
- Use `ffprobe -show_streams file.mp4` to verify

**"Output file exists":**
- Use `--force` to overwrite
- Or choose a different output name with `-o`

**Audio sounds wrong after merge:**
- Likely a duration mismatch you forced through with high tolerance
- Re-extract and verify your source files match

## Technical Details

- **Language:** Python 3.7+ (stdlib only, no external dependencies)
- **Backend:** ffmpeg and ffprobe (required)
- **Duration detection:** Prefers stream duration, falls back to format duration
- **Atomic operations:** Writes to temp file, then renames on success
- **Safety:** Never modifies input files

## See Also

- **SPEC.md** - Full technical specification
- **USAGE.txt** - Detailed help text (also shown with `--help`)
- `av-cleaver --help` - Quick reference

## License

This tool is part of the /opt/tools-av collection.
