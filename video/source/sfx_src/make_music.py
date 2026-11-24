"""Royalty-free fallback music bed: exactly 245 s, 90 BPM, A minor (Am-F-C-G), 48 kHz stereo 16-bit.

Grid: one beat = 32000 samples. Bar n starts at 2.000 + n * 2.6667 s, so the drop (bar 12) lands
exactly on 34.000 s. Sections (bars): intro -1..3, build 4..11, groove 12..43, breakdown 44..49,
groove 50..85, outro 86.. with a 4 s fade from 241 s.
"""
import os

import numpy as np
from scipy import signal

from sfxlib import (SR, amp, bp, convolve, decay, hp, keys, lp, lufs_integrated, lufs_ungated,
                    make_ir, n_of, pan, peq, phase_of, place, rng, saw, short_term, sine,
                    stereo_noise, true_peak_db, tv_filter, white, write_pcm16)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfx", "music_fallback.wav")
TOTAL = 245 * SR
BEAT = 32000
BAR = 4 * BEAT
OFF = 96000

BUILD, DROP, BREAK, BACK, OUTRO, LAST = 4, 12, 44, 50, 86, 90
PROG = ("Am", "F", "C", "G")
VOICING = {"Am": (57, 60, 64), "F": (57, 60, 65), "C": (55, 60, 64), "G": (55, 59, 62)}
ROOT = {"Am": 33, "F": 29, "C": 36, "G": 31}
GROOVE = list(range(DROP, BREAK)) + list(range(BACK, OUTRO))
SWING = 0.57


def at(bar, beat=0.0):
    return OFF + int(round((bar * 4 + beat) * BEAT))


def sec(bar, beat=0.0):
    return at(bar, beat) / SR


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def chord(bar):
    if bar < 0:
        return "Am"
    if bar < BREAK:
        return PROG[bar % 4]
    if bar < BACK:
        return ("Am", "F", "C", "G", "F", "G")[bar - BREAK]
    if bar >= LAST:
        return "Am"
    return PROG[(bar - BACK) % 4]


def bars():
    for b in range(-1, 92):
        s, e = max(0, at(b)), min(TOTAL, at(b + 1))
        if s < e:
            yield b, s, e


# ---------------------------------------------------------------- instruments
def render_pads(r):
    events = []
    for b, s, e in bars():
        c = chord(b)
        if events and events[-1][2] == c and events[-1][1] == s:
            events[-1][1] = e
        else:
            events.append([s, e, c])
    pad = np.zeros((TOTAL, 2))
    xf = n_of(1.0)
    for i, (s, e, c) in enumerate(events):
        att = n_of(3.5) if i == 0 else xf
        L = min(e - s + xf, TOTAL - s)
        k = np.arange(L)
        env = (np.sin(0.5 * np.pi * np.clip(k / att, 0, 1))
               * np.cos(0.5 * np.pi * np.clip((k - (e - s)) / xf, 0, 1)))
        wow = 1 + 0.0015 * np.sin(2 * np.pi * 0.31 * k / SR + r.uniform(0, 2 * np.pi))
        seg = np.zeros((L, 2))
        for m in VOICING[c]:
            f = midi(m) * wow
            for ch, ca, cb in ((0, -7.0, 3.0), (1, 7.0, -3.0)):
                seg[:, ch] += (saw(f * 2 ** (ca / 1200), L, r.random())
                               + 0.7 * saw(f * 2 ** (cb / 1200), L, r.random()))
            seg += 0.9 * sine(f, L, r.random())[:, None]
        pad[s : s + L] += seg * env[:, None]
    t = np.arange(TOTAL) / SR
    fc = keys(t, [(0.0, 170), (6.0, 330), (sec(BUILD), 750), (sec(8), 1050), (sec(10), 1300),
                  (sec(DROP) - 0.05, 1700), (sec(DROP), 2100), (sec(BREAK), 2100),
                  (sec(BREAK) + 1.2, 900), (sec(48), 1200), (sec(BACK) - 0.05, 1900),
                  (sec(BACK), 2300), (sec(OUTRO), 2300), (sec(OUTRO) + 6, 1300), (245.0, 520)],
              log=True)
    fc *= 1 + 0.06 * np.sin(2 * np.pi * t / 23 + 0.7)
    return tv_filter(pad, "lp", fc, [0.54, 1.31], stages=2, block=256)


def render_bass():
    f = np.empty(TOTAL)
    for b, s, e in bars():
        f[s:e] = midi(ROOT[chord(b)])
    a = np.exp(-1 / (0.012 * SR))
    lf = np.log2(f)
    lf, _ = signal.lfilter([1 - a], [1, -a], lf, zi=signal.lfilter_zi([1 - a], [1, -a]) * lf[0])
    ph = 2 * np.pi * phase_of(2 ** lf, TOTAL)
    y = np.sin(ph) + 0.22 * np.sin(2 * ph)
    y = lp(np.tanh(1.2 * y) / np.tanh(1.2), 240, 2)
    t = np.arange(TOTAL) / SR
    g = keys(t, [(0, 0), (sec(5), 0), (sec(7), 0.55), (sec(DROP) - 0.02, 0.55), (sec(DROP), 1.0),
                 (sec(BREAK), 1.0), (sec(BREAK) + 0.35, 0), (sec(BACK) - 0.03, 0), (sec(BACK), 1.0),
                 (sec(OUTRO), 1.0), (sec(OUTRO + 2), 0), (245, 0)])
    return y * g


def kick_sample(r):
    n = n_of(0.6)
    t = np.arange(n) / SR
    body = sine(46 + 64 * np.exp(-t / 0.035), n) * decay(t, 0.20, 0.0015)
    body *= np.cos(0.5 * np.pi * np.clip((t - 0.45) / 0.15, 0, 1)) ** 2
    click = lp(white(n, r) * decay(t, 0.0025, 0.0002), 2500, 2)
    y = body + 0.12 * click / np.max(np.abs(click))
    return lp(np.tanh(1.4 * y) / np.tanh(1.4), 5000, 2)


def clap_sample(r):
    n = n_of(0.45)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for d, a, tau in ((0.0, 0.55, 0.0028), (0.0095, 0.75, 0.0028), (0.019, 0.65, 0.0028),
                      (0.027, 1.0, 0.075)):
        td = np.maximum(t - d, 0)
        y += a * white(n, r) * decay(td, tau, 0.0003) * (t >= d)
    y = bp(y, 900, 3200, 2)
    return y / np.max(np.abs(y))


def rim_sample(r):
    n = n_of(0.12)
    t = np.arange(n) / SR
    y = sine(1650, n) * decay(t, 0.010, 0.0002) + 0.6 * sine(470, n) * decay(t, 0.018, 0.0003)
    y += 0.4 * bp(white(n, r) * decay(t, 0.001, 0.0001), 2000, 7000)
    return y / np.max(np.abs(y))


def hat_sample(r, open_=False):
    n = n_of(0.5 if open_ else 0.15)
    t = np.arange(n) / SR
    metal = sum(np.sign(np.sin(2 * np.pi * f * 1.6 * t + r.uniform(0, 2 * np.pi)))
                for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    metal = bp(metal, 7000, 12000, 2)
    nz = hp(white(n, r), 7500, 2)
    y = (0.6 * metal / np.std(metal) + 0.5 * nz / np.std(nz)) * decay(t, 0.11 if open_ else 0.016,
                                                                         0.0004)
    y = lp(y, 13000, 2)
    return y / np.max(np.abs(y))


def riser(length, seed, f0=300.0, f1=5000.0):
    r = rng(seed)
    n = n_of(length)
    u = np.arange(n) / n
    y = tv_filter(stereo_noise(n, r, 0.3, "white"), "bp", f0 * (f1 / f0) ** (u ** 1.3), 0.8,
                  stages=2, block=128)
    y = amp(y, u ** 2.2)
    fo = n_of(0.03)
    y[-fo:] *= (np.cos(0.5 * np.pi * (np.arange(fo) + 1) / fo) ** 2)[:, None]
    return y


def downlifter(length, seed):
    r = rng(seed)
    n = n_of(length)
    t = np.arange(n) / SR
    u = t / length
    y = tv_filter(stereo_noise(n, r, 0.3, "white"), "bp", 5000 * (300 / 5000) ** (u ** 0.7), 0.8,
                  stages=2, block=128)
    return amp(y, decay(t, 0.6, 0.004) * (1 - u) ** 1.5)


def pump(kicks, depth, tau):
    d = np.zeros(TOTAL)
    m = n_of(0.9)
    ts = np.arange(m) / SR
    shape = (1 - np.exp(-ts / 0.008)) * np.exp(-ts / tau)
    shape /= shape.max()
    shape *= np.cos(0.5 * np.pi * np.clip((ts - 0.7) / 0.2, 0, 1)) ** 2
    for k, _ in kicks:
        seg = d[k : k + m]
        np.maximum(seg, shape[: len(seg)], out=seg)
    return 1 - depth * d


# ---------------------------------------------------------------- arrangement
def build():
    r = rng(90)
    kicks, claps, rims, hats = [], [], [], []
    for b in GROOVE:
        kicks += [(at(b, 0), 1.0), (at(b, 2), 0.85)]
        claps += [(at(b, 1), 1.0), (at(b, 3), 0.95)]
        rims += [(at(b, 1), 0.35), (at(b, 3), 0.35)]
    kicks.append((at(OUTRO, 0), 0.8))  # one last soft downbeat as the drums drop out
    for b in range(8, DROP):
        for beat in (1, 3):
            if not (b == DROP - 1 and beat == 3):
                rims.append((at(b, beat), 0.8))
    for b in list(range(5, DROP)) + GROOVE:
        for beat in range(4):
            if b == DROP - 1 and beat == 3:
                continue  # a one-beat breath before the drop
            for half, base in ((0.0, 0.62), (SWING, 0.85)):
                v = base * r.uniform(0.85, 1.0)
                if b < DROP:
                    v *= 0.25 + 0.55 * (b - 5) / 6
                is_open = b in GROOVE and b % 4 == 3 and beat == 3 and half > 0
                jitter = int(r.normal(0, 0.002) * SR)
                hats.append((at(b, beat + half) + jitter, v, is_open))

    print("rendering pads ...", flush=True)
    pads = render_pads(r)
    pads *= pump(kicks, 0.30, 0.17)[:, None]
    bass = render_bass() * pump(kicks, 0.55, 0.12)

    kick_s = [kick_sample(r) for _ in range(2)]
    clap_s = [clap_sample(r) for _ in range(3)]
    rim_s = [rim_sample(r) for _ in range(2)]
    hat_c = [hat_sample(r) for _ in range(6)]
    hat_o = [hat_sample(r, True) for _ in range(2)]

    st = {k: np.zeros((TOTAL, 2)) for k in ("kick", "clap", "hats", "fx")}
    for i, (s, v) in enumerate(kicks):
        place(st["kick"], kick_s[i % 2], s, v)
    for i, (s, v) in enumerate(claps):
        place(st["clap"], pan(clap_s[i % 3], 0.0) * np.sqrt(2), s, v)
    for i, (s, v) in enumerate(rims):
        place(st["clap"], pan(rim_s[i % 2], -0.1) * np.sqrt(2), s, 0.45 * v)
    for i, (s, v, o) in enumerate(hats):
        smp = hat_o[i % 2] if o else hat_c[i % 6]
        place(st["hats"], pan(smp, 0.15) * np.sqrt(2), s, v * (0.8 if o else 1.0))
    for length, end_bar, g, seed in ((sec(BUILD + 1) - sec(BUILD), BUILD + 1, 0.4, 1),
                                     (sec(DROP) - sec(10), DROP, 1.0, 2),
                                     (sec(BACK) - sec(48), BACK, 0.8, 3)):
        y = riser(length, seed)
        place(st["fx"], y, at(end_bar) - len(y), g)
    for b, seed in ((DROP, 4), (BACK, 5)):
        place(st["fx"], downlifter(2.5, seed), at(b), 0.35)
    st["pads"] = pads
    st["bass"] = np.stack([bass, bass], axis=1)

    # balance stems by K-weighted (ungated) loudness inside the first groove
    w0, w1 = n_of(sec(14)), n_of(sec(42))
    target = {"pads": -20.0, "bass": -26.0, "kick": -25.0, "clap": -30.0, "hats": -31.5}
    for k, tgt in target.items():
        st[k] *= 10 ** ((tgt - lufs_ungated(st[k][w0:w1])) / 20)
    f0, f1 = n_of(sec(DROP) - 2.0), n_of(sec(DROP))
    st["fx"] *= 10 ** ((-23.0 - lufs_ungated(st["fx"][f0:f1])) / 20)

    print("reverb ...", flush=True)
    send = 0.35 * st["pads"] + 0.6 * st["clap"] + 0.15 * st["hats"] + 0.4 * st["fx"]
    ir = make_ir(2.6, seed=91, predelay=0.025, lp_hz=6000, hp_hz=150, hf_ratio=0.5)
    rev = convolve(send, ir)[:TOTAL]
    rev *= 10 ** ((-27.5 - lufs_ungated(rev[w0:w1])) / 20)

    for k in ("pads", "bass", "kick", "clap", "hats"):
        print(f"  stem {k:5s} groove loudness {lufs_ungated(st[k][w0:w1]):6.1f} LUFS(ungated)")
    print(f"  reverb return    {lufs_ungated(rev[w0:w1]):6.1f}")

    mixd = sum(st.values()) + rev
    mixd = hp(mixd, 20, 2)
    mixd = peq(mixd, 1600, 0.8, -2.0)  # gentle pocket for the voiceover's presence range
    t = np.arange(TOTAL) / SR
    fade = np.cos(0.5 * np.pi * np.clip((t - 241.0) / 4.0, 0, 1)) ** 2
    fade *= np.sin(0.5 * np.pi * np.clip(t / 0.03, 0, 1)) ** 2
    mixd *= fade[:, None]
    mixd[-1] = 0.0

    lin = lufs_integrated(mixd)
    mixd *= 10 ** ((-18.0 - lin) / 20)
    tp = true_peak_db(mixd)
    print(f"integrated {lufs_integrated(mixd):.2f} LUFS, true peak {tp:.2f} dBTP")
    if tp > -1.2:
        raise SystemExit("true peak too hot; rebalance before limiting")

    lsb = 1 / 32767
    mask = (np.abs(mixd).max(axis=1) > 1e-6)[:, None]
    dither = (r.random((TOTAL, 2)) - r.random((TOTAL, 2))) * lsb
    write_pcm16(OUT, mixd + dither * mask)
    return mixd


if __name__ == "__main__":
    y = build()
    t, st_l = short_term(y, 3.0, 1.0)
    marks = [(0, "intro"), (sec(BUILD), "build"), (sec(DROP), "drop"), (sec(BREAK), "breakdown"),
             (sec(BACK), "groove back"), (sec(OUTRO), "outro"), (241.0, "fade")]
    for (a, name), (b, _) in zip(marks, marks[1:] + [(245.0, "end")]):
        sel = (t >= a + 1.5) & (t <= b - 1.5)
        if sel.any():
            print(f"{name:12s} {a:7.2f}-{b:7.2f}s  short-term LUFS median {np.median(st_l[sel]):6.1f}")
