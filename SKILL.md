---
name: beat-synced-montage
description: >-
  Cut a folder of video clips into a montage that lands every cut on the beat
  of a song. Detects the tempo itself (or takes --bpm), builds a beat grid,
  and hard-cuts shots to it. Use when the user wants a montage, sizzle reel,
  hype edit, recap, or "cut my clips to this song / to the music / on the
  beat". ffmpeg + Python stdlib only — no npm, no pip installs.
---

# Beat-Synced Montage

Drop in video clips and a song; get back a montage where every cut lands on
the beat. The tempo is detected from the audio itself.

## When to use
The user has **video clips and a song** and wants them cut together **to the
music**: a montage, recap, sizzle reel, travel edit, sports mix, product hype
cut, etc.

## Requirements
- `ffmpeg` and `ffprobe` on PATH.
- Python 3.12+ (standard library only — no pip installs).

## How to run
```bash
python3 scripts/beat_montage.py --clips ./clips --music song.mp3 --out montage.mp4
```

Check what tempo it hears first (fast, renders nothing):
```bash
python3 scripts/beat_montage.py --clips ./clips --music song.mp3 --analyze
```

No song handy? Synthesize a royalty-free one:
```bash
python3 scripts/synth_track.py --bpm 128 --secs 30 --out track.wav
```

## Options
| Flag | Default | What it does |
|------|---------|--------------|
| `--clips` | (required) | Folder of video clips (mp4/mov/mkv/webm...). |
| `--music` | (required) | The song. Tempo is detected from it. |
| `--out` | `montage.mp4` | Output file. |
| `--duration` | `30` | Montage length in seconds. `0` = the whole song. |
| `--pattern` | `2` | Beats per shot, cycled. `2,2,1,1` = two long, two quick. |
| `--bpm` | auto | Force the tempo if detection misses (odd/soft percussion). |
| `--res` | `auto` | `WxH`. Auto picks 1080x1920 if most clips are vertical, else 1920x1080. |
| `--fps` | `30` | Output frame rate. |
| `--order` | `shuffle` | `shuffle` (seeded, repeatable), `name` (filename order), or `duration` (sorted by clip length). |
| `--order-dir` | `asc` | Direction for `--order duration`: `asc` = shortest clips first, `desc` = longest first. Ignored for other `--order` modes. |
| `--seed` | `7` | Change to get a different shuffle. |
| `--snap` | `0.03` | Snap each grid beat to the nearest onset peak within this many seconds. |
| `--analyze` | off | Print BPM + first beats and exit. |
| `--cutlist` | (none) | Write the cut list as JSON (for checking or re-editing). |

## What makes the output good (the design, so you can tune it)
- **The kick drives the grid.** Onset detection weights the low band (< 150 Hz)
  so the beat grid locks to the kick drum, not to hi-hats or vocals.
- **Sub-frame tempo fit.** The beat period is refined to sub-frame precision
  over the whole track, so cuts don't drift late in the montage.
- **Cumulative frame rounding.** Shot lengths are quantized against the
  running total, so audio/video never drift more than half a frame apart.
- **Pattern, not metronome.** `--pattern 2,2,1,1` alternates longer shots
  with quick double-hits — rhythm, not a metronome. That's the taste knob.
- **Clip reuse with a moving cursor.** If clips run out they cycle, but each
  reuse starts later into the clip, so repeats show a different moment.

## Tips
- Punchy electronic/pop/hip-hop tracks detect cleanly. For songs with soft or
  complex percussion, pass `--bpm` (find it once with `--analyze` or by ear).
- Energetic edit: `--pattern 1` at 120+ BPM (a cut every ~0.5s). Calmer:
  `--pattern 4`.
- The montage starts at the first detected beat — intros before the first
  beat are skipped automatically.
- Assumes a constant tempo (true of most modern recordings). Live/rubato
  recordings won't hold the grid; the `--snap` tolerance absorbs small drift.
- `--order duration` is handy for a deliberate build: `--order-dir asc` ramps
  from quick cutaways into longer shots, `desc` front-loads your best long
  takes then tightens up toward the end.

## Troubleshooting
- *Cuts feel off the beat* → run `--analyze`; if the BPM printed is half or
  double what you tap, pass the right one with `--bpm`.
- *"need at least 2 usable clips"* → the folder has fewer than 2 readable
  videos; check extensions and that ffprobe can open them.
- *Some clips never appear* → montage may be shorter than the pool; raise
  `--duration` or lower `--pattern`.
