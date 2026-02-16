# av-editor Color Demo

This demo creates synthetic media and three configs that exercise:
- initial source state (`z_index`, `position`, `scale`)
- unified timeline updates (`z_index` and/or `position` and/or `scale`)
- `production.includes` segment selection and concatenation

## Generate Demo Assets

```bash
chmod +x /opt/tools-av/av-editor/examples/color_demo/generate_demo_assets.sh
/opt/tools-av/av-editor/examples/color_demo/generate_demo_assets.sh /tmp/av-editor-color-demo
```

Generated files include:
- `/tmp/av-editor-color-demo/red.mp4`
- `/tmp/av-editor-color-demo/green.mp4`
- `/tmp/av-editor-color-demo/blue.mp4`
- `/tmp/av-editor-color-demo/master_audio.m4a`
- `/tmp/av-editor-color-demo/demo_01_full_timeline.json`
- `/tmp/av-editor-color-demo/demo_02_includes_cutlist.json`
- `/tmp/av-editor-color-demo/demo_03_state_persistence.json`

## Render Commands

```bash
/opt/tools-av/av-editor/av-editor render /tmp/av-editor-color-demo/demo_01_full_timeline.json --force -v
/opt/tools-av/av-editor/av-editor render /tmp/av-editor-color-demo/demo_02_includes_cutlist.json --force -v
/opt/tools-av/av-editor/av-editor render /tmp/av-editor-color-demo/demo_03_state_persistence.json --force -v
```

## What Each Example Shows

### 1) Full Timeline (`demo_01_full_timeline.json`)

`red` starts as a full background.

`green` initial state:
- `z_index: 2`
- `position: [0, 0]`
- `scale: 35`

`green.timeline` changes:
- `{"at": 2.0, "position": [55, 5]}` changes position only
- `{"at": 3.0, "scale": 50}` changes scale only
- `{"at": 4.0, "z_index": -1}` moves behind
- `{"at": 5.0, "z_index": 3, "position": [0, 55], "scale": 45}` changes all fields
- `{"at": 7.0, "position": [25, 25], "scale": 30}` changes position+scale, keeps z

`blue.timeline` demonstrates similar mixed updates, including z changes that move in front/behind.

### 2) Includes Cutlist (`demo_02_includes_cutlist.json`)

Same timeline behavior as Example 1, but output keeps only:
- `intro: [0.0, 2.2]`
- `middle: [3.8, 6.2]`
- `finale: [8.0, 10.0]`

This demonstrates that:
- timeline times are absolute in master-audio time
- includes select/concatenate subsets of that timeline

### 3) State Persistence (`demo_03_state_persistence.json`)

Demonstrates that timeline entries only override specified keys:
- `{"at": 2.0, "position": [70, 5]}` keeps prior `z_index` and `scale`
- `{"at": 4.0, "scale": 45}` keeps prior `z_index` and `position`
- `{"at": 6.0, "z_index": -1}` keeps prior `position` and `scale`

Run with `-v` to see per-segment state prints and confirm how timeline updates modify the initial values over time.

