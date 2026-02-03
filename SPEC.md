# AV Cleaver Tool - Specification

## Overview
A command-line tool for splitting audio from video files and merging separate audio and video streams, with built-in duration validation to ensure sync compatibility.

**Design philosophy**: Keep splitting and combining simple and predictable. All "processing" happens externally. This tool handles the split → (you process) → merge workflow cleanly.

## Tool Name
`av-cleaver`

## Location
`/opt/tools-av/av-cleaver`

---

## Requirements

### Functional Requirements

#### FR1: Audio Extraction (Split Mode)
- Extract audio stream from video file to a separate audio file
- Support common video formats: MP4, MKV, AVI, MOV, WEBM
- Default: first audio stream, first video stream
- Fail clearly if no audio stream exists

**Codec/Format Handling:**
- **Default behavior (no `--format` specified)**: Copy audio codec without re-encoding
  - Auto-select output container based on codec (e.g., AAC → `.m4a` or `.aac`, MP3 → `.mp3`, etc.)
  - Output naming: `{basename}_audio.{ext}` where ext matches the codec
- **When `--format` is specified**:
  - If specified format matches source codec → copy (fast)
  - If specified format differs from source codec → automatically re-encode with clear notice
  - User can force re-encode with `--re-encode` even when format matches

**Metadata:**
- Preserve container-level metadata when the output container supports it
- If output is a raw elementary stream (like `.aac`), metadata may be lost (tool warns in verbose mode)
- Don't promise what can't be delivered

**Codec → Container Defaults (when copying):**
```
AAC     → .m4a (preferred) or .aac
MP3     → .mp3
FLAC    → .flac
Opus    → .opus or .ogg
Vorbis  → .ogg
AC3     → .ac3
```

#### FR2: Audio/Video Merge
- Combine separate audio and video files into single output file
- Support common video formats as input/output
- Support common audio formats as input
- Validate that audio and video durations match (within tolerance)
- Default stream selection: first video stream from video file, first audio stream from audio file

**Audio Codec Handling:**
- **Default**: Copy audio when compatible with output container, otherwise transcode to container-friendly codec
- **Container-friendly defaults:**
  ```
  MP4/MOV  → AAC (if source isn't already AAC/MP3/AC3)
  MKV      → Copy (MKV accepts almost anything)
  WebM     → Opus (if source isn't already Opus/Vorbis)
  AVI      → MP3 or AC3
  ```

- Tool prints what it's doing: "Copying audio" vs "Transcoding audio to AAC for MP4 compatibility"

**Video Codec Handling:**
- Default: Copy video stream (no re-encoding)
- Optional: `--video-codec` to specify (copy|h264|h265|vp9)

**Audio Track Handling:**
- **Default**: Replace all existing audio tracks with the new audio
- No multi-track complexity in


#### FR3: Duration Validation
- Compare audio and video stream durations before merging
- Configurable tolerance threshold (default: 0.1 seconds)
- Clear error messages when durations don't match, showing exact durations

**Duration Measurement (critical spec detail):**
- Prefer stream duration when available (from ffprobe `stream=duration`)
- Fall back to format duration if stream duration is missing/invalid
- Verbose mode prints which method was used: "Using stream duration: 125.47s" vs "Using format duration: 125.5s"
- Handle VFR video and encoder delay gracefully (hence the tolerance)

**Duration Mismatch Handling:**
- fail fast and loud. This is unacceptable, and we dont want to pass bad work forward. If the duration doesnt match, it's game over and the user has to figure something else out.

#### FR4: Output Control
- Specify output filename/path with `-o` / `--output`
- Auto-generate sensible output names if not specified:
  - Split: `{basename}_audio.{ext}` (ext based on codec/format)
  - Merge: `{video_basename}_merged.{video_ext}`
- **Overwrite protection**:
  - Default: Refuse to overwrite existing files (exit non-zero with clear error)
  - `--force`: Overwrite without prompting
  - **No interactive prompts** (keeps tool script-safe)
- Output container defaults to video file's extension unless `--output` specifies otherwise

#### FR5: Standard CLI Requirements
- `--help`: Show usage information
- `--version`: Print tool version
- `--verbose`: Detailed output (codec decisions, duration method, ffmpeg commands)
- `--dry-run`: Show what would be done without executing
- Exit codes:
  - `0`: Success
  - `1`: General error (bad args, missing files, etc.)
  - `2`: Duration validation failed
  - `3`: Codec/format incompatibility

**Mutually Exclusive Flag Enforcement:**
- `--copy` and `--re-encode` are mutually exclusive (error if both specified)

---

### Non-Functional Requirements

#### NFR1: Usability
- Simple, intuitive command syntax
- Helpful error messages with actionable suggestions
- Verbose mode for debugging (shows ffmpeg commands, decisions made)
- Dry-run mode to preview operations without executing

#### NFR2: Performance
- Use stream copying when possible (no re-encoding) for speed
- Only re-encode when necessary (format change, padding/trimming, container incompatibility)

#### NFR3: Safety
- Validate input files exist and are readable before starting
- Never modify original files (always create new output)
- Atomic operations: write to temp file, then rename on success

#### NFR4: Dependencies
- Requires `ffmpeg` and `ffprobe` (already confirmed installed)
- **Recommendation**: Python 3.7+ with argparse (stdlib only, no external packages)
- Fallback: Pure Bash if Python isn't desired (harder to parse durations cleanly)

---

## Command Line Interface

### Split Mode
```bash
av-cleaver split <video_file> [options]

Options:
  -o, --output <file>      Output audio filename
  -f, --format <format>    Audio format (mp3|aac|flac|wav|ogg|opus)
                           (auto re-encodes if different from source)
  -c, --copy               Copy audio codec without re-encoding (default)
  -r, --re-encode          Force re-encoding even if format matches
  -b, --bitrate <rate>     Audio bitrate for re-encoding (e.g., 192k)
  -v, --verbose            Verbose output (shows decisions and commands)
  --dry-run                Show what would be done without executing
  --version                Print version and exit
  -h, --help               Show this help message

Notes:
  - Default output name: {basename}_audio.{ext}
  - Default behavior: copy codec (no re-encode)
  - Specifying --format different from source triggers re-encode
```

**Examples:**
```bash
# Copy audio as-is (AAC video → audio.m4a)
av-cleaver split video.mp4

# Extract and convert to MP3
av-cleaver split video.mp4 -f mp3 -o audio.mp3

# Extract to FLAC with custom output name
av-cleaver split video.mkv -f flac -o audio.flac

# Dry-run to see what would happen
av-cleaver split video.mp4 --dry-run -v
```

### Merge Mode
```bash
av-cleaver merge <video_file> <audio_file> [options]

Options:
  -o, --output <file>         Output video filename
  -t, --tolerance <seconds>   Duration mismatch tolerance (default: 0.1)
  -c, --video-codec <codec>   Video codec (copy|h264|h265|vp9, default: copy)
  -v, --verbose               Verbose output
  --dry-run                   Show what would be done without executing
  --force                     Overwrite output file if it exists
  --version                   Print version and exit
  -h, --help                  Show this help message

Notes:
  - Default: replace all existing audio with new audio
  - Audio auto-transcodes if incompatible with output container
  - Video copies by default (no re-encode)
  - Refuses to overwrite unless --force is specified
```

**Examples:**
```bash
# Merge with duration validation (default tolerance 0.1s)
av-cleaver merge video.mp4 audio.mp3

# Merge with custom output name
av-cleaver merge video.mp4 audio.mp3 -o final.mp4

# Merge with 0.5s tolerance
av-cleaver merge video.mp4 audio.flac -t 0.5

# Overwrite existing output
av-cleaver merge video.mp4 audio.mp3 -o final.mp4 --force

# Dry-run with verbose to see decisions
av-cleaver merge video.mp4 audio.mp3 --dry-run -v
```

---

## Implementation Notes

### Technology Choice
**Recommendation: Python 3.7+**
- Better error handling and exit codes
- Clean duration parsing (float arithmetic vs Bash)
- argparse provides robust CLI with mutual exclusion
- subprocess for ffmpeg/ffprobe calls
- No external dependencies (stdlib only)

**Alternative: Bash**
- Simpler deployment (single script)
- Harder to parse durations reliably
- More fragile error handling
- Works, but less maintainable

### Duration Validation Logic (Pseudocode)
```python
def get_duration(file):
    # Try stream duration first
    stream_dur = probe_stream_duration(file)
    if stream_dur is not None and stream_dur > 0:
        if verbose:
            print(f"Using stream duration: {stream_dur}s")
        return stream_dur

    # Fall back to format duration
    format_dur = probe_format_duration(file)
    if verbose:
        print(f"Using format duration: {format_dur}s")
    return format_dur

def validate_duration(video_file, audio_file, tolerance):
    video_dur = get_duration(video_file)
    audio_dur = get_duration(audio_file)
    diff = abs(video_dur - audio_dur)

    if diff > tolerance:
        print(f"Duration mismatch: video={video_dur:.2f}s, audio={audio_dur:.2f}s (diff={diff:.2f}s)")
        print(f"Exceeds tolerance of {tolerance}s")
        print("Fix the source files - duration mismatch indicates a problem upstream.")
        sys.exit(2)  # Exit code 2 for duration failure

    if verbose and diff > 0:
        print(f"Duration check passed: diff={diff:.2f}s within tolerance {tolerance}s")
```

### Codec/Container Compatibility Logic
```python
def choose_audio_codec(audio_file, output_container):
    source_codec = probe_audio_codec(audio_file)

    # MKV accepts everything
    if output_container in ['mkv', 'webm']:
        if output_container == 'webm' and source_codec not in ['opus', 'vorbis']:
            return 'libopus'  # Transcode for WebM
        return 'copy'

    # MP4/MOV prefer AAC, MP3, AC3
    if output_container in ['mp4', 'mov', 'm4v']:
        if source_codec in ['aac', 'mp3', 'ac3']:
            return 'copy'
        else:
            print(f"Transcoding {source_codec} to AAC for MP4 compatibility")
            return 'aac'

    # Default: try to copy
    return 'copy'
```

### FFmpeg Command Templates

**Split (copy):**
```bash
ffmpeg -i input.mp4 -vn -acodec copy -map 0:a:0 output.m4a
```

**Split (re-encode to MP3):**
```bash
ffmpeg -i input.mp4 -vn -acodec libmp3lame -b:a 192k -map 0:a:0 output.mp3
```

**Merge (copy both):**
```bash
ffmpeg -i video.mp4 -i audio.m4a -c:v copy -c:a copy -map 0:v:0 -map 1:a:0 output.mp4
```

**Merge (copy video, transcode audio):**
```bash
ffmpeg -i video.mp4 -i audio.flac -c:v copy -c:a aac -b:a 192k -map 0:v:0 -map 1:a:0 output.mp4
```

**Get stream duration:**
```bash
ffprobe -v error -select_streams a:0 -show_entries stream=duration \
  -of default=noprint_wrappers=1:nokey=1 input.mp4
```

**Get format duration (fallback):**
```bash
ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 input.mp4
```

**Probe audio codec:**
```bash
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name \
  -of default=noprint_wrappers=1:nokey=1 input.mp4
```

---


## Testing Plan

### Test Cases

**1. Split Operations**
- Extract audio from MP4 (AAC), MKV (Opus), MOV (AAC)
- Extract with format conversion: MP4 AAC → MP3, MKV Opus → FLAC
- Extract with `--copy` when format matches
- Test with video containing no audio stream (should fail clearly)
- Test codec → container mapping (AAC should output .m4a by default)
- Verify metadata preservation where possible

**2. Merge Operations**
- Merge matching duration files (within 0.1s)
- Merge with 0.2s mismatch (should fail with clear message)
- Merge with custom tolerance `-t 0.5`
- Test container compatibility:
  - MP4 + FLAC → should transcode FLAC to AAC
  - MKV + anything → should copy
  - MP4 + AAC → should copy
- Test video that already has audio (should replace)
- Verify verbose mode shows decisions (copying vs transcoding)

**3. CLI Behavior**
- `--help` works
- `--version` works
- Mutex flags error correctly (`--copy` + `--re-encode`)
- Dry-run shows commands without executing
- Overwrite protection (default refuses, `--force` allows)
- Exit codes: 0 on success, 1 on bad args, 2 on duration fail

**4. Error Handling**
- Missing input files (clear error)
- Invalid file paths
- Corrupted files (ffmpeg will error, tool should report clearly)
- Unsupported formats
- Permission issues (unreadable input, unwritable output dir)

**5. Edge Cases**
- Very large files (multi-GB) - should work without memory issues
- Very short files (<1 second)
- Unicode/special characters in filenames
- Filenames with spaces
- VFR video (variable frame rate)
- Files with encoder delay (duration discrepancies)

---

## Success Criteria

1. ✅ Tool extracts audio from common video formats reliably
2. ✅ Tool merges audio and video with accurate duration validation
3. ✅ Copy-when-possible behavior works correctly (no unnecessary re-encodes)
4. ✅ Auto-transcoding for container compatibility works without user intervention
5. ✅ Duration validation correctly handles stream vs format duration
6. ✅ Clear, actionable error messages guide users when issues occur
7. ✅ Operations never modify original files
8. ✅ Tool is script-safe (no prompts, predictable exit codes)
9. ✅ Performance is good (stream copy is fast, re-encodes only when needed)
10. ✅ Tool feels solid and predictable, not flaky

---

## File Structure

```
/opt/tools-av/
├── av-cleaver               # Main executable (Python or Bash)
├── SPEC.md                  # This specification document
└── README.md                # User-facing documentation (optional)
```

---

## Installation

Place in `/opt/tools-av/` as a standalone tool. Make executable:
```bash
chmod +x /opt/tools-av/av-cleaver
```

Optionally add to PATH or symlink to `/usr/local/bin/`.

---

