"""Shared DSP helpers for the procedural SFX library and music bed.

Everything is plain numpy/scipy. Output contract: 48 kHz, stereo, 16-bit PCM.
Signals are (n,) mono or (n, 2) stereo float64 arrays.
"""
import numpy as np
from scipy import signal
import soundfile as sf

SR = 48000


# ---------------------------------------------------------------- basics
def n_of(sec):
    return int(round(sec * SR))


def tt(dur):
    return np.arange(n_of(dur)) / SR


def rng(seed):
    return np.random.default_rng(seed)


def to_stereo(x):
    x = np.asarray(x, float)
    return x if x.ndim == 2 else np.stack([x, x], axis=1)


def amp(x, env):
    """Multiply x by a per-sample envelope, broadcasting over channels."""
    env = np.asarray(env, float)
    if x.ndim == 2 and env.ndim == 1:
        env = env[:, None]
    return x * env


def lvl(x, db=0.0):
    """Scale x so its RMS (over all samples/channels) is `db` dB re 1.0."""
    r = np.sqrt(np.mean(np.asarray(x, float) ** 2)) + 1e-20
    return x * (10 ** (db / 20) / r)


def mix(*xs):
    xs = [to_stereo(x) for x in xs]
    n = max(len(x) for x in xs)
    out = np.zeros((n, 2))
    for x in xs:
        out[: len(x)] += x
    return out


def delayed(x, sec, total=None):
    d = n_of(sec)
    total = total if total is not None else len(x) + d
    out = np.zeros((total,) + x.shape[1:])
    seg = x[: max(0, total - d)]
    out[d : d + len(seg)] = seg
    return out


def place(buf, x, start, gain=1.0):
    """Add x into buf at sample `start` (clipped to the buffer)."""
    if start >= len(buf):
        return
    s0 = max(0, start)
    x = x[s0 - start :]
    e = min(len(buf), s0 + len(x))
    if buf.ndim == 2 and x.ndim == 1:
        buf[s0:e] += gain * x[: e - s0, None]
    else:
        buf[s0:e] += gain * x[: e - s0]


# ---------------------------------------------------------------- envelopes
def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def bell(t, tp, tend, rise=2.0, fall=2.0):
    """0 at t=0, smooth peak of 1 at tp, back to 0 at tend (zero slope at the peak)."""
    e = np.zeros_like(t)
    a = t < tp
    e[a] = np.sin(0.5 * np.pi * t[a] / tp) ** rise
    d = (t >= tp) & (t < tend)
    e[d] = np.cos(0.5 * np.pi * (t[d] - tp) / (tend - tp)) ** fall
    return e


def decay(t, tau, attack=0.0005, hold=0.0):
    """Raised-cosine attack, optional hold, then exponential decay."""
    if attack > 0:
        att = np.sin(0.5 * np.pi * np.clip(t / attack, 0, 1)) ** 2
    else:
        att = np.ones_like(t)
    return att * np.exp(-np.maximum(t - hold, 0) / tau)


def gate(t, t0, t1, attack, release):
    """Smooth on/off gate: rises from t0 over `attack`, falls from t1 over `release`."""
    a = np.sin(0.5 * np.pi * np.clip((t - t0) / attack, 0, 1)) ** 2
    r = np.cos(0.5 * np.pi * np.clip((t - t1) / release, 0, 1)) ** 2
    return a * r


def keys(t, points, log=False):
    """Piecewise-linear automation through (time, value) points (log-domain if log)."""
    ts = [p[0] for p in points]
    vs = np.array([p[1] for p in points], float)
    if log:
        return np.exp(np.interp(t, ts, np.log(vs)))
    return np.interp(t, ts, vs)


# ---------------------------------------------------------------- noise
def white(n, r):
    return r.standard_normal(n)


def colored(n, r, exponent):
    """Gaussian noise with power spectrum ~ 1/f**exponent, unit variance."""
    X = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    X *= f ** (-exponent / 2)
    x = np.fft.irfft(X, n)
    return x / (np.std(x) + 1e-12)


def pink(n, r):
    return colored(n, r, 1.0)


def brown(n, r):
    return colored(n, r, 2.0)


def stereo_noise(n, r, corr=0.5, kind="white"):
    """Stereo noise whose L/R correlation is `corr` (scalar or per-sample)."""
    gen = {"white": white, "pink": pink, "brown": brown}[kind]
    c, a, b = gen(n, r), gen(n, r), gen(n, r)
    corr = np.clip(np.broadcast_to(np.asarray(corr, float), (n,)), 0, 1)
    k1, k2 = np.sqrt(corr), np.sqrt(1 - corr)
    return np.stack([k1 * c + k2 * a, k1 * c + k2 * b], axis=1)


# ---------------------------------------------------------------- filters
def butter(kind, fc, order=2):
    return signal.butter(order, fc, btype=kind, fs=SR, output="sos")


def filt(x, sos, zp=False):
    if zp:
        return signal.sosfiltfilt(sos, x, axis=0)
    return signal.sosfilt(sos, x, axis=0)


def lp(x, fc, order=2, zp=False):
    return filt(x, butter("lowpass", fc, order), zp)


def hp(x, fc, order=2, zp=False):
    return filt(x, butter("highpass", fc, order), zp)


def bp(x, lo, hi, order=2, zp=False):
    return filt(x, butter("bandpass", [lo, hi], order), zp)


def _rbj(kind, fc, q, gain_db=0.0):
    fc = min(max(fc, 10.0), SR * 0.45)
    w0 = 2 * np.pi * fc / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "bp":  # constant 0 dB peak gain
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        A = 10 ** (gain_db / 40)
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    else:
        raise ValueError(kind)
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return np.concatenate([b, a])


def rbj_sos(kind, fc, q, stages=1, gain_db=0.0):
    if np.ndim(q) == 0:
        q = [q] * stages
    return np.stack([_rbj(kind, fc, qq, gain_db) for qq in q])


def peq(x, fc, q, gain_db):
    return signal.sosfilt(rbj_sos("peak", fc, q, 1, gain_db), x, axis=0)


def tv_filter(x, kind, fc, q, stages=1, block=64):
    """Time-varying RBJ biquad cascade, coefficients updated every `block` samples.

    State is carried across blocks, so slowly moving cutoffs are click-free.
    `fc` and `q` may be scalars or per-sample arrays; `q` may also be a list (one per stage).
    """
    x = np.asarray(x, float)
    mono = x.ndim == 1
    X = x[:, None] if mono else x
    n, nch = X.shape
    fc = np.broadcast_to(np.asarray(fc, float), (n,))
    per_stage = isinstance(q, (list, tuple))
    if not per_stage:
        q = np.broadcast_to(np.asarray(q, float), (n,))
    Y = np.empty_like(X)
    zi = np.zeros((stages, 2, nch))
    for s in range(0, n, block):
        e = min(n, s + block)
        m = (s + e) // 2
        sos = rbj_sos(kind, fc[m], list(q) if per_stage else [q[m]] * stages, stages)
        Y[s:e], zi = signal.sosfilt(sos, X[s:e], axis=0, zi=zi)
    return Y[:, 0] if mono else Y


# ---------------------------------------------------------------- oscillators
def phase_of(freq, n, phase0=0.0):
    """Phase in cycles for a scalar or per-sample frequency (phase[0] == phase0)."""
    f = np.broadcast_to(np.asarray(freq, float), (n,))
    ph = np.empty(n)
    ph[0] = 0.0
    np.cumsum(f[:-1] / SR, out=ph[1:])
    return ph + phase0


def sine(freq, n, phase0=0.0):
    return np.sin(2 * np.pi * phase_of(freq, n, phase0))


def saw(freq, n, phase0=0.0):
    """Band-limited (polyBLEP) sawtooth, range about [-1, 1]."""
    f = np.broadcast_to(np.asarray(freq, float), (n,))
    ph = phase_of(f, n, phase0) % 1.0
    dt = f / SR
    y = 2.0 * ph - 1.0
    m = ph < dt
    u = ph[m] / dt[m]
    y[m] -= u + u - u * u - 1.0
    m = ph > 1.0 - dt
    u = (ph[m] - 1.0) / dt[m]
    y[m] -= u * u + u + u + 1.0
    return y


def pulse(freq, n, phase0=0.0, duty=0.5):
    """Band-limited pulse as the difference of two polyBLEP saws (DC-free)."""
    return 0.5 * (saw(freq, n, phase0) - saw(freq, n, phase0 + duty))


def fm(fc, ratio, index, n):
    pc = phase_of(fc, n)
    pm = phase_of(np.asarray(fc) * ratio, n)
    return np.sin(2 * np.pi * pc + np.asarray(index) * np.sin(2 * np.pi * pm))


def modal(t, modes, attack=0.0001):
    """Sum of damped sines: modes = [(freq, amp, tau), ...] all starting at phase 0."""
    n = len(t)
    y = np.zeros(n)
    for f, a, tau in modes:
        y += a * sine(f, n) * decay(t, tau, attack)
    return y


# ---------------------------------------------------------------- space
def pan(x, p):
    """Equal-power pan of a mono signal; p in [-1, 1] (scalar or per-sample)."""
    p = np.broadcast_to(np.asarray(p, float), x.shape)
    th = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(th), x * np.sin(th)], axis=1)


def balance(y, p):
    """Balance a stereo signal toward p in [-1, 1]; unity gain at p = 0."""
    p = np.broadcast_to(np.asarray(p, float), (len(y),))
    th = (p + 1) * np.pi / 4
    return np.stack([y[:, 0] * np.cos(th) * np.sqrt(2), y[:, 1] * np.sin(th) * np.sqrt(2)], axis=1)


def make_ir(t60, seed=0, predelay=0.01, length=None, lp_hz=9000, hp_hz=100,
            hf_ratio=0.5, lf_ratio=1.0, early=6):
    """Synthetic stereo reverb IR: decorrelated noise with frequency-dependent decay."""
    r = rng(seed)
    n = n_of(length if length else min(1.15 * t60 + 0.05, 5.0))
    t = np.arange(n) / SR
    pd = n_of(predelay)
    ir = np.zeros((pd + n, 2))
    lo_s, mid_s, hi_s = butter("lowpass", 600), butter("bandpass", [600, 4000]), butter("highpass", 4000)

    def env(T):
        return np.exp(-6.9078 * t / max(T, 1e-3))

    for ch in range(2):
        y = (signal.sosfilt(lo_s, r.standard_normal(n)) * env(t60 * lf_ratio)
             + signal.sosfilt(mid_s, r.standard_normal(n)) * env(t60 * 0.85)
             + signal.sosfilt(hi_s, r.standard_normal(n)) * env(t60 * hf_ratio))
        y *= 1 - np.exp(-t / 0.004)
        w = np.hanning(32)
        for _ in range(early):
            d = r.uniform(0.004, 0.045)
            i = int(d * SR)
            if i + 32 < n:
                y[i : i + 32] += r.choice([-1, 1]) * r.uniform(0.6, 1.4) * np.exp(-d / 0.05) * w
        y = signal.sosfilt(butter("lowpass", lp_hz), y)
        y = signal.sosfilt(butter("highpass", hp_hz), y)
        ir[pd:, ch] = y
    ir /= np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True))
    return ir


def convolve(x, ir):
    xs = to_stereo(x)
    return np.stack([signal.oaconvolve(xs[:, c], ir[:, c]) for c in range(2)], axis=1)


def reverb(x, ir, wet_db=-12.0, dry=1.0):
    """Dry + wet, with the wet scaled so its energy is `wet_db` relative to the dry."""
    xs = to_stereo(x)
    wet = convolve(xs, ir)
    g = 10 ** (wet_db / 20) * np.sqrt((np.sum(xs ** 2) + 1e-20) / (np.sum(wet ** 2) + 1e-20))
    out = g * wet
    out[: len(xs)] += dry * xs
    return out


# ---------------------------------------------------------------- loudness
_KB1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
_KA1 = [1.0, -1.69065929318241, 0.73248077421585]
_KB2 = [1.0, -2.0, 1.0]
_KA2 = [1.0, -1.99004745483398, 0.99007225036621]


def k_weight(x):
    y = signal.lfilter(_KB1, _KA1, to_stereo(x), axis=0)
    return signal.lfilter(_KB2, _KA2, y, axis=0)


def _blocks(y, blk_s=0.4, hop_s=0.1):
    blk, hop = int(blk_s * SR), int(hop_s * SR)
    cs = np.concatenate([np.zeros((1, y.shape[1])), np.cumsum(y ** 2, axis=0)])
    starts = np.arange(0, len(y) - blk + 1, hop)
    return starts, ((cs[starts + blk] - cs[starts]) / blk).sum(axis=1)


def lufs_integrated(x):
    """ITU-R BS.1770-4 integrated loudness (48 kHz coefficients, L/R weight 1)."""
    _, zs = _blocks(k_weight(x))
    lj = -0.691 + 10 * np.log10(zs + 1e-30)
    g1 = lj > -70
    if not g1.any():
        return -np.inf
    rel = -0.691 + 10 * np.log10(zs[g1].mean()) - 10
    g2 = g1 & (lj > rel)
    return -0.691 + 10 * np.log10(zs[g2].mean())


def lufs_ungated(x):
    y = k_weight(x)
    return -0.691 + 10 * np.log10(np.mean(y ** 2, axis=0).sum() + 1e-30)


def short_term(x, win=3.0, hop=0.5):
    starts, zs = _blocks(k_weight(x), win, hop)
    return (starts + int(win * SR) / 2) / SR, -0.691 + 10 * np.log10(zs + 1e-30)


def true_peak_db(x, os=4):
    up = signal.resample_poly(to_stereo(x), os, 1, axis=0)
    return 20 * np.log10(np.max(np.abs(up)) + 1e-30)


# ---------------------------------------------------------------- output
def finalize(x, path, dur, fade_in_ms=0.5, fade_out_ms=20.0, trim=True, trim_db=-60.0,
             peak_db=-3.0, dc_hz=12.0):
    """DC-block, trim leading silence, fit to `dur`, raised-cosine fades, peak-normalise, write."""
    y = to_stereo(np.asarray(x, float))
    if not np.all(np.isfinite(y)):
        raise ValueError(f"non-finite samples in {path}")
    y = signal.sosfilt(butter("highpass", dc_hz, 2), y, axis=0)
    if trim:
        a = np.max(np.abs(y), axis=1)
        idx = int(np.argmax(a > a.max() * 10 ** (trim_db / 20)))
        y = y[max(0, idx - 2):]
    n = n_of(dur)
    y = y[:n] if len(y) >= n else np.concatenate([y, np.zeros((n - len(y), 2))])
    fi = max(2, n_of(fade_in_ms / 1000))
    fo = max(2, n_of(fade_out_ms / 1000))
    y[:fi] *= (np.sin(0.5 * np.pi * np.arange(fi) / fi) ** 2)[:, None]
    y[-fo:] *= (np.cos(0.5 * np.pi * (np.arange(fo) + 1) / fo) ** 2)[:, None]
    y *= 10 ** (peak_db / 20) / np.max(np.abs(y))
    write_pcm16(path, y)
    return y


def write_pcm16(path, y):
    """Round-to-nearest int16 conversion done here, so no rounding bias (DC) is introduced."""
    q = np.clip(np.round(np.asarray(y) * 32767), -32768, 32767).astype(np.int16)
    sf.write(path, q, SR, subtype="PCM_16")
