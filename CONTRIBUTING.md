# Contributing to beat-synced-montage

Thanks for looking at this — it's a small, single-purpose Claude skill for
cutting clips to the beat of a song, and it's meant to stay that way:  + Python standard
library only, no build step, no dependencies to install.

## Before you start
- Open an issue first for anything beyond a small fix, so we're aligned on
  approach before you put time into it.
- Look for issues tagged **good first issue** if you're not sure where to start.

## Local setup
No install step. You need:
- `ffmpeg` + `ffprobe` on `PATH`
- Python 3 (3.12+ where noted in the README)

Run the script directly against the sample files in `demo/`:
```bash
python3 scripts/beat_montage.py --help
```

## Making a change
1. Fork the repo, branch off `main`.
2. Keep the no-dependency constraint — if a change needs a pip install, open
   an issue to discuss it first rather than adding it in a PR.
3. Test by actually rendering something (ideally against the files in
   `demo/`) and check the output, not just that the script exits 0.
4. Keep flags and defaults documented in both `README.md` and `SKILL.md` —
   they intentionally overlap (README = human quick-start, SKILL.md = what
   Claude reads to use the skill correctly).

## Submitting
Open a PR against `main` with:
- What changed and why (one or two sentences is fine).
- Before/after output if the change affects rendered video/image quality —
  a screenshot or short clip is more useful than a description.

## Code style
Match what's already there: plain, readable Python, no external frameworks,
comments only where the *why* isn't obvious from the code itself.
