#!/usr/bin/env python3
"""
synth_track.py — generate a royalty-free electronic beat track from nothing.

No samples, no downloads, no license worries: the track is synthesized with
pure math (Python standard library only), so it's yours. Handy when you want
to test or demo the beat-synced montage and don't have a track ready.

  python3 synth_track.py --bpm 128 --secs 30 --out track.wav
"""

import argparse
import math
import random
import struct
import wave

SR = 44100


def synth(bpm, secs, seed=3):
    rng = random.Random(seed)
    n = int(SR * secs)
    buf = [0.0] * n
    beat = 60.0 / bpm
    spb = int(SR * beat)

    # minor-ish bass line, one note per beat, two-bar loop
    roots = [110.0, 110.0, 130.81, 98.0]  # A, A, C, G
    n_beats = int(secs / beat) + 1

    for b in range(n_beats):
        t0 = b * spb
        # --- kick: 4-on-the-floor, pitch 150->45 Hz, exp decay
        ph = 0.0
        for i in range(int(0.28 * SR)):
            if t0 + i >= n:
                break
            frac = i / SR
            f = 45 + 105 * math.exp(-frac * 28)
            ph += 2 * math.pi * f / SR
            env = math.exp(-frac * 16)
            buf[t0 + i] += 0.9 * env * math.sin(ph)
        # --- clap on 2 and 4: noise burst, crude high-pass
        if b % 2 == 1:
            prev = 0.0
            for i in range(int(0.16 * SR)):
                if t0 + i >= n:
                    break
                x = rng.uniform(-1, 1)
                hp = x - prev
                prev = x
                env = math.exp(-(i / SR) * 22)
                buf[t0 + i] += 0.35 * env * hp
        # --- offbeat hat
        h0 = t0 + spb // 2
        prev = 0.0
        for i in range(int(0.05 * SR)):
            if h0 + i >= n:
                break
            x = rng.uniform(-1, 1)
            hp = x - prev
            prev = x
            env = math.exp(-(i / SR) * 60)
            buf[h0 + i] += 0.22 * env * hp
        # --- bass: gated eighth notes on the beat's root
        root = roots[(b // 4) % len(roots)] / 2
        for eighth in range(2):
            g0 = t0 + eighth * (spb // 2)
            ph = 0.0
            lp = 0.0
            for i in range(int(spb * 0.4)):
                if g0 + i >= n:
                    break
                ph += 2 * math.pi * root / SR
                sq = 1.0 if math.sin(ph) >= 0 else -1.0
                lp += 0.05 * (sq - lp)  # cheap low-pass
                env = min(1.0, i / (0.005 * SR)) * math.exp(-(i / SR) * 6)
                buf[g0 + i] += 0.30 * env * lp

    # normalize to -1 dBFS
    peak = max(abs(v) for v in buf) or 1.0
    gain = 0.89 / peak
    return [v * gain for v in buf]


def main():
    ap = argparse.ArgumentParser(description="Synthesize a beat track.")
    ap.add_argument("--bpm", type=float, default=128.0)
    ap.add_argument("--secs", type=float, default=30.0)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--out", default="track.wav")
    args = ap.parse_args()

    buf = synth(args.bpm, args.secs, args.seed)
    with wave.open(args.out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack(f"<{len(buf)}h",
                                  *(int(v * 32767) for v in buf)))
    print(f"wrote {args.out}  ({args.secs:.0f}s at {args.bpm:g} BPM)")


if __name__ == "__main__":
    main()
