# Beat-Synced Montage — a Claude skill

Drop in a **folder of video clips** and a **song**, get back a **montage cut on
the beat** — every hard cut lands on the music. The tempo is detected from the
song itself; no tapping, no timeline, no editing app.

No npm. No pip installs. Just `ffmpeg` + Python 3.

## Quick start
```bash
python3 scripts/beat_montage.py --clips ./clips --music song.mp3 --out montage.mp4
```
Hear what tempo it detects first (renders nothing):
```bash
python3 scripts/beat_montage.py --clips ./clips --music song.mp3 --analyze
```
No royalty-free track handy? Make one from pure math:
```bash
python3 scripts/synth_track.py --bpm 128 --secs 30 --out track.wav
```

## Why the cuts actually land
- **The kick drives the grid** — beat detection weights the low end, so the
  grid locks to the drum, not the vocals.
- **Sub-frame tempo fit** — the beat period is refined across the whole track,
  so cuts don't drift by the end.
- **Half-a-frame A/V lock** — shot lengths are quantized cumulatively; measured
  on the demo: every cut within one frame of the grid (mean error 8 ms).
- **`--pattern` is the taste knob** — `2,2,1,1` cuts two longer shots then two
  quick hits, so it feels edited, not metronomic.
- **`--order` controls clip sequence** — `shuffle` (default), `name`, or
  `duration` (shortest/longest first, via `--order-dir`).

## Options
See [`SKILL.md`](SKILL.md) for the full flag reference and troubleshooting.

## Install as a Claude skill
Copy this folder into your Claude skills directory (e.g.
`~/.claude/skills/beat-synced-montage/`), then ask Claude to
"cut these clips to this song."

## Requirements
- `ffmpeg` + `ffprobe` on PATH
- Python 3.12+ (standard library only)

---
Part of the **Dunham Motion Skills** series — free craft skills for people new to Claude.
