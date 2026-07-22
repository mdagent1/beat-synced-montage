#!/usr/bin/env python3
"""
Beat-Synced Montage — clips + a song in, a montage cut on the beat out.

Pure Python standard library + ffmpeg/ffprobe. No pip installs.

  python3 beat_montage.py --clips ./clips --music song.mp3 --out montage.mp4

How it works:
  1. Decode the song to raw PCM twice (full band + low-passed) via ffmpeg.
  2. Onset envelope = half-wave-rectified log-energy flux (low band weighted
     up, so the kick drives the grid).
  3. Tempo by autocorrelation of the envelope, refined to sub-frame precision
     by a period+phase grid fit over the whole track.
  4. Beat grid -> cut list (a new shot every --every beats), each grid point
     snapped to the nearest local onset peak within --snap seconds.
  5. One ffmpeg pass: per-shot trims -> scale/crop -> concat, with the song
     as the audio track, faded out at the end.
"""

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
from array import array

SR = 22050          # analysis sample rate
WIN = 512           # energy window (samples)
HOP = 256           # hop (samples) -> ~11.6 ms resolution
HOP_S = HOP / SR

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".mxf"}


def die(msg):
    sys.exit(f"error: {msg}")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def ffprobe_stream(path):
    try:
        out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height,duration",
                   "-show_entries", "format=duration",
                   "-of", "json", path]).stdout
        info = json.loads(out)
        st = info["streams"][0]
        dur = float(st.get("duration") or info["format"]["duration"])
        return int(st["width"]), int(st["height"]), dur
    except Exception:
        return None


def audio_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", path]).stdout
    return float(out.strip())


# ---------------------------------------------------------------- analysis

def decode_pcm(path, lowpass=None):
    """Decode audio to mono s16le PCM at SR. Returns array('h')."""
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    if lowpass:
        cmd += ["-af", f"lowpass=f={lowpass}"]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    raw = run(cmd).stdout
    pcm = array("h")
    pcm.frombytes(raw[: len(raw) - (len(raw) % 2)])
    return pcm


def log_energy(pcm):
    """Windowed log energy. math.sumprod keeps this at C speed."""
    n = max(0, (len(pcm) - WIN) // HOP)
    out = []
    for i in range(n):
        w = pcm[i * HOP: i * HOP + WIN]
        e = math.sumprod(w, w) / WIN
        out.append(math.log10(e + 1.0))
    return out


def onset_envelope(song):
    full = log_energy(decode_pcm(song))
    low = log_energy(decode_pcm(song, lowpass=150))
    n = min(len(full), len(low))
    env = [0.0] * n
    for i in range(1, n):
        flux = 0.5 * max(0.0, full[i] - full[i - 1]) + \
               1.0 * max(0.0, low[i] - low[i - 1])
        env[i] = flux
    # light smoothing (3-tap)
    sm = env[:]
    for i in range(1, n - 1):
        sm[i] = (env[i - 1] + env[i] + env[i + 1]) / 3.0
    return sm


def env_at(env, x):
    """Linear interpolation of the envelope at fractional frame x."""
    if x < 0 or x >= len(env) - 1:
        return 0.0
    i = int(x)
    f = x - i
    return env[i] * (1 - f) + env[i + 1] * f


def grid_score(env, period, phase):
    s, k = 0.0, 0
    x = phase
    while x < len(env) - 1:
        s += env_at(env, x)
        k += 1
        x += period
    return s / max(k, 1)


def detect_beats(env, bpm_hint=0.0):
    """Return (bpm, phase_frames, period_frames)."""
    n = len(env)
    if bpm_hint > 0:
        p0 = 60.0 / bpm_hint / HOP_S
        lo, hi = p0 * 0.97, p0 * 1.03
    else:
        # autocorrelation over 60..200 BPM
        lag_min = int(60.0 / 200.0 / HOP_S)
        lag_max = min(int(60.0 / 60.0 / HOP_S), n // 2)
        best_lag, best_r = lag_min, -1.0
        for lag in range(lag_min, lag_max + 1):
            r = math.sumprod(env[: n - lag], env[lag:])
            bpm = 60.0 / (lag * HOP_S)
            # gentle preference for the 90-180 montage range; fixes half/double
            if 90 <= bpm <= 180:
                r *= 1.15
            if r > best_r:
                best_r, best_lag = r, lag
        lo, hi = best_lag - 2.0, best_lag + 2.0

    # sub-frame refinement: search period x phase for the best grid fit
    best = (-1.0, lo, 0.0)
    p = lo
    while p <= hi:
        step = max(p / 24.0, 1.0)
        ph = 0.0
        while ph < p:
            s = grid_score(env, p, ph)
            if s > best[0]:
                best = (s, p, ph)
            ph += step
        p += 0.05 if (hi - lo) < 6 else 0.25
    _, period, phase = best
    # one more fine pass around the winner
    for dp in [x * 0.01 for x in range(-8, 9)]:
        for dph in [x * 0.25 for x in range(-8, 9)]:
            s = grid_score(env, period + dp, phase + dph)
            if s > best[0]:
                best = (s, period + dp, phase + dph)
    _, period, phase = best
    bpm = 60.0 / (period * HOP_S)
    return bpm, phase, period


def beat_times(env, phase, period, snap_s):
    """Beat grid in seconds, each point snapped to a local onset peak."""
    snap_f = snap_s / HOP_S
    beats, x = [], phase
    prev = -1.0
    while x < len(env):
        if snap_f > 0:
            a, b = int(max(0, x - snap_f)), int(min(len(env) - 1, x + snap_f))
            j = max(range(a, b + 1), key=lambda i: env[i], default=int(x))
            t = j * HOP_S
        else:
            t = x * HOP_S
        t = max(t, prev + 0.1)  # keep monotonic
        beats.append(t)
        prev = t
        x += period
    return beats


# ---------------------------------------------------------------- assembly

def collect_clips(folder):
    clips = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
            continue
        meta = ffprobe_stream(p)
        if not meta:
            print(f"  ! skipping unreadable: {name}")
            continue
        w, h, dur = meta
        if dur < 0.5:
            print(f"  ! skipping too-short: {name}")
            continue
        clips.append({"path": p, "name": name, "w": w, "h": h, "dur": dur})
    return clips


def build_cutlist(clips, beats, duration, pattern, order, seed, order_dir="asc"):
    """Shots: [(clip, in_point, start_t, end_t)] following the beat grid."""
    rng = random.Random(seed)
    pool = clips[:]
    if order == "shuffle":
        rng.shuffle(pool)
    elif order == "duration":
        pool.sort(key=lambda c: c["dur"], reverse=(order_dir == "desc"))
    cursors = {c["path"]: min(0.15 * c["dur"], 1.0) for c in clips}

    shots, bi, pi, ci = [], 0, 0, 0
    t0 = beats[0]
    while bi < len(beats) - 1:
        every = pattern[pi % len(pattern)]
        pi += 1
        j = min(bi + every, len(beats) - 1)
        start, end = beats[bi], beats[j]
        if start - t0 >= duration - 0.05:
            break
        end = min(end, t0 + duration)
        shot_len = end - start
        if shot_len < 0.1:
            break
        clip = pool[ci % len(pool)]
        ci += 1
        cur = cursors[clip["path"]]
        if cur + shot_len > clip["dur"] - 0.05:
            cur = 0.0
        shots.append({"clip": clip, "in": round(cur, 3),
                      "start": start, "end": end})
        cursors[clip["path"]] = cur + shot_len
        bi = j
    return shots


def assemble(shots, music, music_start, out, res, fps, crf):
    w, h = res
    t0 = shots[0]["start"]
    total = shots[-1]["end"] - t0

    # cumulative frame rounding so A/V drift never exceeds half a frame
    frames = []
    for s in shots:
        n0 = round((s["start"] - t0) * fps)
        n1 = round((s["end"] - t0) * fps)
        frames.append(max(1, n1 - n0))

    cmd = ["ffmpeg", "-y", "-v", "error"]
    filt, labels = [], []
    for i, (s, nf) in enumerate(zip(shots, frames)):
        need = nf / fps + 0.5
        cmd += ["-ss", f"{s['in']:.3f}", "-t", f"{need:.3f}",
                "-i", s["clip"]["path"]]
        filt.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={fps},trim=end_frame={nf},"
            f"setpts=PTS-STARTPTS,format=yuv420p,setsar=1[v{i}]")
        labels.append(f"[v{i}]")
    ai = len(shots)
    cmd += ["-ss", f"{music_start:.3f}", "-t", f"{total + 0.1:.3f}",
            "-i", music]
    fade = min(0.75, total / 4)
    filt.append("".join(labels) +
                f"concat=n={len(shots)}:v=1:a=0[vout]")
    filt.append(f"[{ai}:a]atrim=duration={total:.3f},"
                f"afade=t=in:d=0.02,"
                f"afade=t=out:st={total - fade:.3f}:d={fade:.3f}[aout]")
    cmd += ["-filter_complex", ";".join(filt),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    run(cmd)
    return total


def main():
    ap = argparse.ArgumentParser(description="Cut a montage on the beat.")
    ap.add_argument("--clips", required=True, help="folder of video clips")
    ap.add_argument("--music", required=True, help="the song")
    ap.add_argument("--out", default="montage.mp4")
    ap.add_argument("--duration", type=float, default=30.0,
                    help="montage length in seconds (0 = whole song)")
    ap.add_argument("--pattern", default="2",
                    help="beats per shot, cycled — e.g. '2' or '2,2,1,1'")
    ap.add_argument("--bpm", type=float, default=0.0,
                    help="force the tempo instead of detecting it")
    ap.add_argument("--res", default="auto",
                    help="WxH, or 'auto' (1080x1920 if clips are vertical)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--order", choices=["shuffle", "name", "duration"],
                    default="shuffle",
                    help="clip ordering: shuffle, name (as scanned), or "
                         "duration (sorted by clip length, see --order-dir)")
    ap.add_argument("--order-dir", choices=["asc", "desc"], default="asc",
                    help="direction for --order duration: asc = shortest "
                         "clips first, desc = longest first (ignored "
                         "otherwise)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--snap", type=float, default=0.03,
                    help="snap beats to onset peaks within this many seconds")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--analyze", action="store_true",
                    help="print BPM + first beats and exit")
    ap.add_argument("--cutlist", default="", help="write the cut list as JSON")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            die(f"{tool} not found on PATH")
    if not os.path.isdir(args.clips):
        die(f"not a folder: {args.clips}")
    if not os.path.isfile(args.music):
        die(f"not a file: {args.music}")

    pattern = []
    for tok in args.pattern.split(","):
        tok = tok.strip()
        if not tok.isdigit() or int(tok) < 1:
            die(f"--pattern must be comma-separated positive ints, got {tok!r}")
        pattern.append(int(tok))

    print("analyzing the song ...")
    env = onset_envelope(args.music)
    if len(env) < 200:
        die("song too short to analyze (need a few seconds of audio)")
    bpm, phase, period = detect_beats(env, args.bpm)
    beats = beat_times(env, phase, period, args.snap)
    print(f"  tempo: {bpm:.1f} BPM  ({len(beats)} beats, "
          f"first at {beats[0]:.2f}s)")

    if args.analyze:
        print("  first beats:", " ".join(f"{b:.2f}" for b in beats[:16]))
        return

    song_len = audio_duration(args.music)
    duration = args.duration if args.duration > 0 else song_len
    duration = min(duration, song_len - beats[0] - 0.25)
    if duration <= 1:
        die("song is too short for the requested duration")

    print("scanning clips ...")
    clips = collect_clips(args.clips)
    if len(clips) < 2:
        die("need at least 2 usable clips")
    vertical = sum(1 for c in clips if c["h"] > c["w"]) > len(clips) / 2
    if args.res == "auto":
        res = (1080, 1920) if vertical else (1920, 1080)
    else:
        try:
            res = tuple(int(x) for x in args.res.lower().split("x"))
            assert len(res) == 2 and res[0] > 0 and res[1] > 0
        except Exception:
            die(f"bad --res: {args.res}")
    print(f"  {len(clips)} clips -> {res[0]}x{res[1]} @ {args.fps} fps")

    shots = build_cutlist(clips, beats, duration, pattern,
                          args.order, args.seed, args.order_dir)
    if len(shots) < 2:
        die("could not build at least 2 shots (song/duration too short?)")

    if args.cutlist:
        data = [{"clip": s["clip"]["name"], "in": s["in"],
                 "start": round(s["start"] - shots[0]["start"], 3),
                 "end": round(s["end"] - shots[0]["start"], 3)}
                for s in shots]
        with open(args.cutlist, "w") as f:
            json.dump({"bpm": round(bpm, 2), "shots": data}, f, indent=1)

    print(f"cutting {len(shots)} shots ...")
    total = assemble(shots, args.music, shots[0]["start"], args.out,
                     res, args.fps, args.crf)
    print(f"done: {args.out}  ({total:.1f}s, {len(shots)} cuts on the beat)")


if __name__ == "__main__":
    main()
