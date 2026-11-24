"""Procedural SFX library: 23 sounds, 48 kHz / stereo / 16-bit, peak -3 dBFS.

Usage:  python make_sfx.py [name ...]      (no names = build everything)
"""
import os
import sys

import numpy as np

from sfxlib import (SR, amp, balance, bell, bp, brown, convolve, decay, delayed, finalize, fm,
                    gate, hp, keys, lp, lvl, make_ir, mix, modal, n_of, pan, peq, phase_of,
                    pink, place, pulse, reverb, rng, saw, sine, smoothstep, stereo_noise,
                    to_stereo, tv_filter, white)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfx")


def T(dur):
    n = n_of(dur)
    return n, np.arange(n) / SR


# ====================================================================== whooshes / swipes
def whoosh_short():
    r = rng(101)
    n, t = T(0.52)
    tp, te = 0.17, 0.44
    env = bell(t, tp, te, rise=1.6, fall=1.9)
    up = smoothstep(t / tp)
    down = smoothstep((t - tp) / (te - tp))
    fc = np.where(t < tp, 380 * (2600 / 380) ** up, 2600 * (620 / 2600) ** down)
    src = 0.6 * stereo_noise(n, r, 0.55, "pink") + 0.5 * stereo_noise(n, r, 0.55, "white")
    body = tv_filter(src, "bp", fc, [0.9, 1.4], stages=2, block=32)
    air = hp(stereo_noise(n, r, 0.4, "white"), 5200, 2)
    low = lp(stereo_noise(n, r, 0.85, "pink"), 280, 2)
    y = (lvl(amp(body, env), 0) + lvl(amp(air, env ** 1.6), -15) + lvl(amp(low, env), -11))
    y = balance(y, 0.22 * np.tanh((t - tp) / 0.08))
    return reverb(y, make_ir(0.45, seed=11, predelay=0.006, lp_hz=8000), wet_db=-13)


def whoosh_long():
    r = rng(202)
    n, t = T(1.25)
    tp, te = 0.52, 1.08
    env = bell(t, tp, te, rise=2.3, fall=1.5)
    # Doppler: pitch ratio high on approach, low after the pass (+-3.2 semitones)
    ratio = 2 ** ((3.8 * -np.tanh((t - tp) / 0.13)) / 12)
    pos = np.concatenate([[0.0], np.cumsum(ratio)[:-1]])
    m = int(pos[-1]) + 8
    grid = np.arange(m)

    def doppler(src):
        return np.stack([np.interp(pos, grid, src[:, c]) for c in range(2)], axis=1)

    src = stereo_noise(m, r, 0.7, "pink")
    src = peq(peq(src, 230, 2.5, 9.0), 640, 3.0, 6.0)
    src = lp(src, 2600, 2)
    d = doppler(src)
    up = smoothstep(t / tp)
    down = smoothstep((t - tp) / (te - tp))
    fc = np.where(t < tp, 260 * (1150 / 260) ** up, 1150 * (210 / 1150) ** down)
    body = tv_filter(d, "bp", fc, 0.75, stages=1, block=64)
    whistle = (tv_filter(d, "bp", 520 * ratio, 9.0, stages=1, block=64)
               + 0.45 * tv_filter(d, "bp", 1090 * ratio, 9.0, stages=1, block=64))
    rumble = lp(doppler(stereo_noise(m, r, 0.85, "brown")), 170, 2)
    air = hp(stereo_noise(n, r, 0.4, "white"), 3600, 2)
    y = (lvl(amp(body, env), 0) + lvl(amp(whistle, env), -6) + lvl(amp(rumble, env), -5)
         + lvl(amp(air, env ** 2.2), -16))
    y = balance(y, 0.65 * np.tanh((t - tp) / 0.2))
    return reverb(y, make_ir(0.9, seed=22, predelay=0.012, lp_hz=6000), wet_db=-11)


def swipe_up():
    r = rng(303)
    n, t = T(0.40)
    tp, te = 0.11, 0.335
    env = bell(t, tp, te, rise=1.4, fall=2.2)
    u = np.clip(t / 0.31, 0, 1)
    fc = 700 * (6800 / 700) ** (u ** 0.85)
    src = 0.7 * stereo_noise(n, r, 0.6, "white") + 0.5 * stereo_noise(n, r, 0.6, "pink")
    body = tv_filter(src, "bp", fc, [1.0, 1.6], stages=2, block=32)
    zip_ = sine(520 * (1500 / 520) ** u, n)
    air = hp(stereo_noise(n, r, 0.5, "white"), 6500, 2)
    y = lvl(amp(body, env), 0) + lvl(amp(to_stereo(zip_), env ** 2), -23) + lvl(amp(air, env), -15)
    y = balance(y, 0.12 * np.tanh((t - tp) / 0.06))
    return reverb(y, make_ir(0.35, seed=33, predelay=0.005), wet_db=-15)


# ====================================================================== risers / impacts
def riser_4s():
    r = rng(404)
    n, t = T(4.0)
    u = t / 4.0
    # filtered noise, centre rising and narrowing, image widening
    src = stereo_noise(n, r, 0.85 - 0.6 * u, "white")
    noise = tv_filter(src, "bp", 250 * (7500 / 250) ** (u ** 1.35), 0.7 + 1.1 * u ** 2,
                      stages=2, block=64)
    # rising power-chord saw stack + sines, A2 -> A4 accelerating
    f0 = 110 * 4 ** (u ** 1.7)
    stack = np.zeros((n, 2))
    for ch, cents in ((0, -8.0), (1, 8.0)):
        for k, ratio in enumerate((1.0, 1.5, 2.0)):
            stack[:, ch] += saw(f0 * ratio * 2 ** (cents / 1200), n, r.random()) * (0.8 if k else 1.0)
            stack[:, ch] += 0.5 * saw(f0 * ratio * 2 ** (-cents / 2400), n, r.random())
    stack = tv_filter(stack, "lp", 300 * (6500 / 300) ** (u ** 1.2), [0.54, 1.1], stages=2, block=64)
    sines = sine(f0, n) + 0.5 * sine(2 * f0, n)
    # accelerating pulses: 2 Hz -> 18 Hz, smooth periodic gate (no clicks)
    rate = 2 * 9 ** (u ** 1.5)
    ph = phase_of(rate, n)
    g = (0.5 + 0.5 * np.cos(2 * np.pi * ((ph % 1.0) - 0.08))) ** 3
    trem = 1 - (0.55 * smoothstep(u * 1.4)) * (1 - g)
    # percussive ticks on each pulse
    ticks = np.zeros((n, 2))
    starts = np.nonzero(np.diff(np.floor(ph)) > 0)[0] + 1
    tk_t = np.arange(n_of(0.05)) / SR
    for i, s in enumerate(starts):
        burst = bp(white(len(tk_t), r) * decay(tk_t, 0.006, 0.0006), 900, 5000)
        burst += 0.6 * sine(70, len(tk_t)) * decay(tk_t, 0.03, 0.002)
        place(ticks, pan(burst, 0.25 * (-1) ** i), s, gain=u[s] ** 1.5)
    sub = sine(40 * (58 / 40) ** u, n)
    y = (lvl(amp(noise, (u ** 2.3) * trem), 0)
         + lvl(amp(stack, (u ** 2.0) * trem), -3)
         + lvl(amp(to_stereo(sines), (u ** 2.0) * trem), -10)
         + lvl(ticks, -13)
         + lvl(amp(to_stereo(sub), u ** 1.6), -10))
    y = reverb(y, make_ir(1.6, seed=44, predelay=0.015, lp_hz=7000), wet_db=-9)
    return y[:n]


def soft_riser_2s():
    r = rng(2323)
    n, t = T(2.0)
    u = t / 2.0
    src = 0.6 * stereo_noise(n, r, 0.6 - 0.4 * u, "white") + 0.5 * stereo_noise(n, r, 0.5, "pink")
    body = tv_filter(src, "bp", 400 * (6000 / 400) ** (u ** 1.25), 0.9, stages=2, block=64)
    f = 329.63 * 2 ** u
    tone = np.stack([sine(f * 2 ** (-5 / 1200), n) + 0.4 * sine(2 * f, n, 0.3),
                     sine(f * 2 ** (5 / 1200), n, 0.2) + 0.4 * sine(2 * f, n, 0.6)], axis=1)
    air = hp(stereo_noise(n, r, 0.3, "white"), 7000, 2)
    y = (lvl(amp(body, u ** 1.8), 0) + lvl(amp(tone, u ** 2.4), -16)
         + lvl(amp(air, u ** 2.5), -14))
    y = reverb(y, make_ir(1.1, seed=55, predelay=0.012, lp_hz=8000), wet_db=-8)
    return y[:n]


def impact_boom():
    r = rng(505)
    n, t = T(2.7)
    sub = sine(35 + 25 * np.exp(-t / 0.35), n) * decay(t, 0.85, attack=0.003)
    body = sine(55 + 95 * np.exp(-t / 0.028), n) * decay(t, 0.10, attack=0.0015)
    core = lvl(sub, 0) + lvl(body, -2)
    core = np.tanh(1.5 * core / np.max(np.abs(core))) / np.tanh(1.5)
    trans = bp(stereo_noise(n, r, 0.7, "white"), 150, 6000) * decay(t, 0.022, 0.0004)[:, None]
    debris = lp(stereo_noise(n, r, 0.5, "pink"), 1300, 2) * decay(t, 0.28, 0.002)[:, None]
    rumble = lp(stereo_noise(n, r, 0.8, "brown"), 120, 2) * decay(t, 0.7, 0.01)[:, None]
    dry = (lvl(to_stereo(core), 0) + lvl(trans, -9) + lvl(debris, -17) + lvl(rumble, -16))
    send = lvl(trans, 0) + lvl(debris, -4) + lvl(to_stereo(body), -6)
    ir = make_ir(2.2, seed=66, predelay=0.014, lp_hz=3500, hp_hz=60, hf_ratio=0.35)
    wet = convolve(send, ir)
    wet = lvl(wet, 0) * (np.sqrt(np.mean(dry ** 2)) * 10 ** (-12.5 / 20))
    return mix(dry, wet)


def sub_drop():
    n, t = T(1.3)
    y = sine(30 + 50 * np.exp(-t / 0.28), n) * decay(t, 0.45, attack=0.006)
    return to_stereo(y)


# ====================================================================== UI one-shots
def click_ui():
    r = rng(707)
    n, t = T(0.09)
    trans = bp(white(n, r) * decay(t, 0.0006, 0.00008), 2500, 9000)
    tone = sine(2900 + 350 * np.exp(-t / 0.004), n) * decay(t, 0.006, 0.00015)
    body = (sine(1150, n) * decay(t, 0.0045, 0.0002)
            + 0.45 * sine(1830, n) * decay(t, 0.003, 0.0002))
    y = lvl(trans, 0) + lvl(tone, -6) + lvl(body, -5)
    return reverb(y, make_ir(0.10, seed=77, predelay=0.002, early=3), wet_db=-20)


def tap_soft():
    r = rng(808)
    n, t = T(0.16)
    body = sine(185 + 140 * np.exp(-t / 0.010), n) * decay(t, 0.028, 0.0015)
    mid = sine(640, n) * decay(t, 0.010, 0.001)
    skin = lp(pink(n, r) * decay(t, 0.007, 0.0008), 1400, 2)
    y = lp(lvl(body, 0) + lvl(mid, -10) + lvl(skin, -7), 3200, 2)
    return reverb(y, make_ir(0.15, seed=88, predelay=0.003, early=3), wet_db=-20)


def pop_blip():
    r = rng(909)
    n, t = T(0.19)
    ph = phase_of(520 + 1100 * np.exp(-t / 0.016), n)
    y1 = np.sin(2 * np.pi * ph) * decay(t, 0.045, 0.0008)
    y2 = np.sin(4 * np.pi * ph) * decay(t, 0.018, 0.0008)
    click = bp(white(n, r) * decay(t, 0.0008, 0.0001), 2000, 6000)
    y = lvl(y1, 0) + lvl(y2, -11) + lvl(click, -15)
    y = np.tanh(1.3 * y / np.max(np.abs(y)))
    return reverb(y, make_ir(0.18, seed=99, predelay=0.003, early=3), wet_db=-18)


def notif_ping_1():
    """A6 FM bell, single strike: bright attack mellowing to a near-pure tone."""
    r = rng(1001)
    n, t = T(0.7)
    fc = 1760.0
    bell_ = fm(fc, 2.0, 2.2 * np.exp(-t / 0.045) + 0.25, n) * decay(t, 0.17, 0.0012)
    sparkle = sine(fc * 2.76, n) * decay(t, 0.05, 0.001)
    mallet = hp(white(n, r) * decay(t, 0.0015, 0.0002), 3000, 2)
    y = hp(lvl(bell_, 0) + lvl(sparkle, -15) + lvl(mallet, -24), 500, 2)
    return reverb(y, make_ir(0.7, seed=111, predelay=0.010, hf_ratio=0.6), wet_db=-11)


def _glass(f0, n, t, tau):
    chirp = f0 * (1 + 0.012 * np.exp(-t / 0.006))
    parts = ((1.0, 1.0, tau), (2.0, 0.22, tau * 0.45), (3.0, 0.08, tau * 0.3), (4.16, 0.06, tau * 0.18))
    return sum(a * sine(chirp * k, n) * decay(t, tk, 0.0015) for k, a, tk in parts)


def notif_ping_2():
    """Two-tone glass 'ba-ding': E6 then B6, softer and glassier than ping 1."""
    n, t = T(0.7)
    a = hp(_glass(1318.51, n, t, 0.20), 600, 2)
    b = hp(delayed(_glass(1975.53, n, t, 0.22), 0.07, n), 600, 2)
    y = pan(0.55 * a, -0.12) + pan(b, 0.12)
    return reverb(y, make_ir(0.6, seed=222, predelay=0.010, hf_ratio=0.6), wet_db=-11)


def data_blip():
    n, t = T(0.10)
    ph = phase_of(2637.0 * (1 + 0.06 * (1 - np.exp(-t / 0.004))), n)
    y = np.sin(2 * np.pi * ph) + 0.18 * np.sin(6 * np.pi * ph) + 0.06 * np.sin(10 * np.pi * ph)
    y *= decay(t, 0.009, attack=0.0006, hold=0.014)
    return reverb(y, make_ir(0.08, seed=333, predelay=0.002, early=2), wet_db=-22)


def tick_clock():
    r = rng(1818)
    n, t = T(0.15)
    modes = ((2150, 1.0, 0.006), (3720, 0.65, 0.0042), (5310, 0.45, 0.003),
             (7900, 0.25, 0.002), (1180, 0.35, 0.008))
    res = modal(t, modes)
    trans = bp(white(n, r) * decay(t, 0.0005, 0.00005), 3000, 11000)
    body = sine(820, n) * decay(t, 0.005, 0.0002)
    y = lvl(res, 0) + lvl(trans, -7) + lvl(body, -11)
    return reverb(y, make_ir(0.12, seed=444, predelay=0.002, early=3), wet_db=-20)


def lock_clunk():
    r = rng(2121)
    n, t = T(0.6)
    click = modal(t, ((2350, 1.0, 0.010), (3020, 0.6, 0.006), (4180, 0.5, 0.007), (6230, 0.3, 0.004)))
    click += 0.5 * bp(white(n, r) * decay(t, 0.0008, 0.0001), 2000, 9000)
    td = np.maximum(t - 0.008, 0)
    thump = sine(55 + 85 * np.exp(-td / 0.025), n) * decay(td, 0.075, 0.0018) * (t >= 0.008)
    tb = np.maximum(t - 0.006, 0)
    body = bp(white(n, r), 200, 800) * decay(tb, 0.025, 0.001) * (t >= 0.006)
    body += 0.6 * sine(420, n) * decay(tb, 0.030, 0.001) * (t >= 0.006)
    ts = np.maximum(t - 0.058, 0)
    settle = modal(ts, ((1900, 1.0, 0.005), (3400, 0.4, 0.003))) * (t >= 0.058)
    y = lvl(click, -4) + lvl(thump, 0) + lvl(body, -2) + lvl(settle, -22)
    y = np.tanh(1.3 * y / np.max(np.abs(y)))
    return reverb(y, make_ir(0.35, seed=555, predelay=0.006), wet_db=-14)


# ====================================================================== tonal cues
def _marimba(f0, n, t):
    parts = ((1.0, 1.0, 0.42), (3.98, 0.32, 0.11), (9.9, 0.10, 0.035))
    y = sum(a * sine(f0 * k, n) * decay(t, tau, 0.0012) for k, a, tau in parts)
    return y


def ringtone():
    r = rng(1212)
    n, t = T(3.4)
    tn = np.arange(n_of(1.8)) / SR
    m = len(tn)
    mallet = lp(white(m, r) * decay(tn, 0.002, 0.0002), 2500, 2)

    def note(f, vel):
        return vel * (_marimba(f, m, tn) + 0.22 * _glass(2 * f, m, tn, 0.6) + 0.12 * mallet)

    y = np.zeros(n)
    for start in (0.0, 1.6):
        place(y, note(659.26, 0.85), n_of(start))
        place(y, note(987.77, 1.0), n_of(start + 0.20))
    dry = pan(y, 0.0) * np.sqrt(2)
    # soft ping-pong echo (lowpassed) for space without clutter
    echo = np.zeros((n, 2))
    src = lp(y, 3000, 2)
    for k, (ch, g) in enumerate(((0, 0.26), (1, 0.15), (0, 0.08))):
        echo[:, ch] += delayed(src, 0.30 * (k + 1), n) * g
    out = dry + echo
    return reverb(out, make_ir(1.2, seed=1213, predelay=0.015, hf_ratio=0.5), wet_db=-12)


def success_chime():
    r = rng(1414)
    n, t = T(1.1)

    def note(f0, tau):
        parts = ((1.0, 1.0, tau), (2.0, 0.30, tau * 0.5), (3.0, 0.10, tau * 0.3),
                 (4.2, 0.06, tau * 0.2), (5.4, 0.03, tau * 0.12))
        y = sum(a * sine(f0 * k, n) * decay(t, tk, 0.001) for k, a, tk in parts)
        return y + 0.05 * hp(white(n, r) * decay(t, 0.0012, 0.0002), 3000, 2)

    st = np.zeros((n, 2))
    st += pan(0.8 * note(880.00, 0.30), -0.15)
    st += pan(delayed(0.9 * note(1108.73, 0.32), 0.085, n), 0.0)
    st += pan(delayed(note(1318.51, 0.55), 0.170, n), 0.15)
    st = hp(st, 400, 2)
    return reverb(st, make_ir(0.9, seed=1415, predelay=0.012, hf_ratio=0.6), wet_db=-10)


def error_buzz():
    n, t = T(0.56)

    def buzz(f):
        y = np.zeros(n)
        k = 1
        while k * f < 4000:
            y += (1.0 / k) * np.exp(-k * f / 2600) * sine(k * f, n)
            k += 2
        return np.tanh(1.4 * y / np.max(np.abs(y)))

    y = np.zeros(n)
    for t0, t1, vel, st in ((0.0, 0.15, 1.0, 0), (0.21, 0.36, 0.88, -1)):
        s = 2 ** (st / 12)
        tone = buzz(130.81 * s) + 0.8 * buzz(185.0 * s) + 0.5 * buzz(130.81 * s * 1.006)
        y += vel * tone * gate(t, t0, t1 - 0.03, 0.004, 0.03)
    y = hp(lp(y, 2400, 2), 110, 2)
    return reverb(y, make_ir(0.25, seed=1516, predelay=0.005), wet_db=-16)


def heartbeat():
    r = rng(1717)
    n, t = T(1.45)

    def thump(t0, f_hi, f_lo, tau_f, tau_a, att, vel):
        tl = np.maximum(t - t0, 0)
        on = t >= t0
        tone = sine(f_lo + (f_hi - f_lo) * np.exp(-tl / tau_f), n) * decay(tl, tau_a, att) * on
        thud = lp(pink(n, r), 140, 2) * decay(tl, 0.04, 0.005) * on
        return vel * (lvl(tone, 0) + lvl(thud, -12))

    y = thump(0.0, 85, 47, 0.03, 0.085, 0.007, 1.0) + thump(0.29, 95, 55, 0.025, 0.07, 0.006, 0.72)
    y = np.tanh(1.5 * y / np.max(np.abs(y)))
    y = lp(y, 380, 2)
    return reverb(y, make_ir(0.35, seed=1718, predelay=0.006, lp_hz=2000), wet_db=-22)


def phone_buzz():
    r = rng(1111)
    n, t = T(1.65)
    f = np.full(n, 120.0)
    a = np.zeros(n)
    for s, e in ((0.0, 0.55), (0.80, 1.35)):
        on = (t >= s) & (t < e + 0.09)
        tl = t - s
        fb = 118 + 50 * (1 - np.exp(-np.maximum(tl, 0) / 0.035))
        fb -= 40 * np.clip((t - e) / 0.06, 0, 1)
        f[on] = fb[on]
        a += gate(t, s, e, 0.03, 0.06) * on
    f += 1.2 * np.sin(2 * np.pi * 6.5 * t)
    ph = phase_of(f, n)
    motor = np.sin(2 * np.pi * ph)
    tone = (np.tanh(2.8 * motor + 0.35) - np.tanh(0.35)) * a
    tone *= 1 + 0.22 * np.sin(2 * np.pi * 26 * t)
    tone = hp(lp(tone, 2200, 2), 90, 2)
    tone = peq(peq(peq(tone, 240, 4.0, 6.0), 620, 5.0, 4.0), 1300, 6.0, 3.0)
    # rattle: tiny clicks locked to the motor cycle, random strength, decorrelated L/R
    rat = np.zeros((n, 2))
    starts = np.nonzero(np.diff(np.floor(ph)) > 0)[0] + 1
    ct = np.arange(n_of(0.006)) / SR
    for s in starts:
        if a[s] < 0.05:
            continue
        for ch in range(2):
            click = white(len(ct), r) * decay(ct, 0.0007, 0.0001)
            place(rat[:, ch], click, s + int(r.integers(0, 24)), gain=a[s] * r.uniform(0.3, 1.0))
    rat = bp(rat, 1500, 5000)
    y = lvl(to_stereo(tone), 0) + lvl(rat, -17)
    return reverb(y, make_ir(0.3, seed=1112, predelay=0.004, lp_hz=5000), wet_db=-18)


def glitch_short():
    r = rng(1313)
    n, t = T(0.42)
    chord = (pulse(220, n) + 0.7 * pulse(277.18 * 1.01, n, 0.3) + 0.5 * pulse(523.25, n, 0.6)
             + 0.6 * saw(110 * 2 ** (6 * t), n))
    src = 0.6 * chord / np.max(np.abs(chord)) + 0.45 * white(n, r) * 0.5
    out = np.zeros((n, 2))
    pos, first = 0, True
    kinds = ["crush", "srr", "stutter", "noise", "tone", "gap"]
    probs = [0.22, 0.22, 0.24, 0.14, 0.12, 0.06]
    while pos < n:
        L = int(r.integers(n_of(0.010), n_of(0.045)))
        L = min(L, n - pos)
        seg = src[pos : pos + L].copy()
        kind = "crush" if first else r.choice(kinds, p=probs)
        if kind == "crush":
            q = 2 ** (int(r.integers(3, 6)) - 1)
            seg = np.round(seg * q) / q
        elif kind == "srr":
            k = int(r.integers(6, 28))
            seg = np.repeat(seg[::k], k)[:L]
        elif kind == "stutter":
            g = int(r.integers(n_of(0.003), n_of(0.012)))
            s0 = int(r.integers(0, n - g))
            grain = src[s0 : s0 + g] * np.hanning(g) ** 0.25
            seg = np.tile(grain, L // g + 1)[:L]
        elif kind == "noise":
            fc = r.uniform(1200, 7000)
            tl = np.arange(L) / SR
            seg = bp(white(L, r), fc / 1.5, min(fc * 1.5, 20000)) * decay(tl, 0.012, 0.0003) * 2.5
        elif kind == "tone":
            seg = 0.6 * pulse(r.uniform(300, 2500), L, 0.0, 0.5 if r.random() < 0.5 else 0.25)
        else:
            seg = np.zeros(L)
        f = min(n_of(0.0004), L // 2)
        if f > 1:
            ramp = np.sin(0.5 * np.pi * np.arange(f) / f) ** 2
            seg[:f] *= ramp
            seg[-f:] *= ramp[::-1]
        g_env = 1.0 if first else r.uniform(0.35, 1.0) * (1 - 0.45 * pos / n)
        out[pos : pos + L] += pan(seg * g_env, 0.0 if first else r.uniform(-0.7, 0.7))
        pos += L
        first = False
    out = hp(lp(out, 10000, 2), 90, 2)
    out = np.tanh(1.2 * out / np.max(np.abs(out)))
    return reverb(out, make_ir(0.25, seed=1314, predelay=0.004), wet_db=-17)


def typing_ticks():
    r = rng(1616)
    n, t = T(2.0)
    out = np.zeros((n, 2))
    m = n_of(0.05)
    tk = np.arange(m) / SR
    ev, count = 0.0, 0
    while ev < 1.93:
        count += 1
        space = count % 9 == 0
        if space:
            y = (bp(white(m, r) * decay(tk, 0.003, 0.0002), 350, 1200)
                 + 0.5 * sine(r.uniform(150, 200), m) * decay(tk, 0.008, 0.0006))
            g = r.uniform(0.6, 0.85)
        else:
            fc = r.uniform(2600, 5200)
            trans = bp(white(m, r) * decay(tk, r.uniform(0.0006, 0.0013), 0.0001), fc / 1.6, fc * 1.6)
            body = sine(r.uniform(1400, 2600), m) * decay(tk, 0.003, 0.0002)
            low = sine(r.uniform(160, 240), m) * decay(tk, 0.006, 0.0005)
            y = lvl(trans, 0) + lvl(body, -10) + lvl(low, -17)
            g = r.uniform(0.5, 1.0)
        place(out, pan(y / np.max(np.abs(y)), r.uniform(-0.25, 0.25)), n_of(ev), gain=g)
        x = r.random()
        if x < 0.07:
            ev += r.uniform(0.18, 0.28)
        elif x < 0.25:
            ev += r.uniform(0.032, 0.048)
        else:
            ev += r.uniform(0.055, 0.125)
    return reverb(out, make_ir(0.15, seed=1617, predelay=0.003, early=3), wet_db=-18)


def shimmer():
    r = rng(1919)
    n, t = T(1.7)
    sweep_fc = 3000 * (10000 / 3000) ** smoothstep(t / 0.2)
    sweep = tv_filter(stereo_noise(n, r, 0.4, "white"), "bp", sweep_fc, 2.0, stages=2, block=32)
    sweep = amp(sweep, bell(t, 0.05, 0.4, 1.5, 2.0))
    freqs = np.array([1760.0, 2637.02, 2959.96, 3520.0, 3951.07, 4434.92, 5274.04, 7040.0])
    grains = np.zeros((n, 2))
    for _ in range(80):
        onset = min(r.exponential(0.28), 1.1)
        f = r.choice(freqs) * (1 + r.uniform(-0.003, 0.003))
        tau = r.uniform(0.03, 0.14)
        m = n_of(min(6 * tau, 0.6))
        tg = np.arange(m) / SR
        gr = sine(f, m) * decay(tg, tau, r.uniform(0.002, 0.006))
        gain = r.uniform(0.25, 1.0) * np.exp(-onset / 0.5)
        place(grains, pan(gr, r.uniform(-0.8, 0.8)), n_of(onset), gain=gain)
    sus = np.zeros((n, 2))
    for i, f in enumerate((3520.0, 5274.04, 7040.0)):
        fl = lp(white(n, r), 18, 2)
        fl = 0.5 + 0.5 * np.tanh(2.5 * fl / np.std(fl))
        sus += pan(sine(f, n, r.random()) * fl * decay(t, 0.5, 0.01), (-0.5, 0.5, 0.0)[i])
    y = lvl(grains, 0) + lvl(sweep, -7) + lvl(sus, -8)
    y = hp(y, 1500, 2)
    return reverb(y, make_ir(1.6, seed=1920, predelay=0.012, hf_ratio=0.7, lp_hz=12000), wet_db=-5)


def scan_sweep():
    r = rng(2222)
    n, t = T(1.25)
    u = np.clip(t / 1.15, 0, 1)
    f = 600 * (2400 / 600) ** u * (1 + 0.006 * np.sin(2 * np.pi * 9 * t))
    tone = sine(f, n) + 0.15 * sine(2 * f, n)
    band = tv_filter(stereo_noise(n, r, 0.5, "white"), "bp", 2 * f, 2.5, stages=2, block=32)
    flutter = 1 - 0.35 * (0.5 + 0.5 * np.sin(2 * np.pi * 30 * t))
    env = gate(t, 0.0, 0.95, 0.06, 0.25)
    y = lvl(amp(to_stereo(tone), env), -5) + lvl(amp(band, env * flutter), 0)
    y = balance(y, -0.6 + 1.2 * smoothstep(t / 1.2))
    y = hp(lp(y, 9000, 2), 300, 2)
    return reverb(y, make_ir(0.6, seed=2223, predelay=0.008), wet_db=-12)


# ====================================================================== registry
# name: (generator, duration, kwargs for finalize)
SFX = {
    "whoosh_short": (whoosh_short, 0.45, dict(fade_in_ms=2, fade_out_ms=40)),
    "whoosh_long": (whoosh_long, 1.10, dict(fade_in_ms=3, fade_out_ms=80)),
    "swipe_up": (swipe_up, 0.35, dict(fade_in_ms=2, fade_out_ms=30)),
    "riser_4s": (riser_4s, 4.00, dict(trim=False, fade_in_ms=20, fade_out_ms=4)),
    "impact_boom": (impact_boom, 2.50, dict(fade_in_ms=0.3, fade_out_ms=350)),
    "sub_drop": (sub_drop, 1.20, dict(fade_in_ms=0.5, fade_out_ms=300)),
    "click_ui": (click_ui, 0.06, dict(fade_in_ms=0.1, fade_out_ms=15)),
    "tap_soft": (tap_soft, 0.12, dict(fade_in_ms=0.3, fade_out_ms=30)),
    "pop_blip": (pop_blip, 0.15, dict(fade_in_ms=0.3, fade_out_ms=35)),
    "notif_ping_1": (notif_ping_1, 0.60, dict(fade_in_ms=0.3, fade_out_ms=150)),
    "notif_ping_2": (notif_ping_2, 0.60, dict(fade_in_ms=0.3, fade_out_ms=140)),
    "phone_buzz": (phone_buzz, 1.60, dict(fade_in_ms=1, fade_out_ms=60)),
    "ringtone": (ringtone, 3.20, dict(fade_in_ms=0.3, fade_out_ms=400)),
    "glitch_short": (glitch_short, 0.40, dict(fade_in_ms=0.2, fade_out_ms=25)),
    "error_buzz": (error_buzz, 0.50, dict(fade_in_ms=0.3, fade_out_ms=60)),
    "success_chime": (success_chime, 1.00, dict(fade_in_ms=0.3, fade_out_ms=200)),
    "typing_ticks": (typing_ticks, 2.00, dict(fade_in_ms=0.1, fade_out_ms=25)),
    "heartbeat": (heartbeat, 1.40, dict(fade_in_ms=0.5, fade_out_ms=200)),
    "tick_clock": (tick_clock, 0.12, dict(fade_in_ms=0.1, fade_out_ms=25)),
    "shimmer": (shimmer, 1.50, dict(fade_in_ms=0.5, fade_out_ms=350)),
    "data_blip": (data_blip, 0.08, dict(fade_in_ms=0.2, fade_out_ms=20)),
    "lock_clunk": (lock_clunk, 0.50, dict(fade_in_ms=0.2, fade_out_ms=90)),
    "scan_sweep": (scan_sweep, 1.20, dict(fade_in_ms=1, fade_out_ms=120)),
    "soft_riser_2s": (soft_riser_2s, 2.00, dict(trim=False, fade_in_ms=20, fade_out_ms=25)),
}


def build(names=None):
    os.makedirs(OUT, exist_ok=True)
    for name in names or SFX:
        gen, dur, kw = SFX[name]
        y = finalize(gen(), os.path.join(OUT, f"{name}.wav"), dur, **kw)
        print(f"{name:16s} {len(y) / SR:6.3f}s")


if __name__ == "__main__":
    build(sys.argv[1:] or None)
