"""Audio mix for the 7even5ive film: VO on the timeline, word-synced SFX, music ducked under the voice.
usage: python mix.py <music_file> <music_offset_s> <music_gain_db> <out.wav>
Reads timeline.json, so the mix cannot drift from the visuals."""
import json, subprocess, sys
import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import maximum_filter1d, minimum_filter1d

sys.path.insert(0, 'sfx_src')
from sfxlib import SR, hp, lp, peq, lufs_integrated, short_term, true_peak_db  # noqa: E402

music_file, m_off, m_gain, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
tl = json.load(open('timeline.json'))
T, total = tl['T'], tl['total']
N = int(round(total * SR))
lines = json.load(open('vo/durations.json'))
db = lambda g: 10 ** (g / 20)


def place(bus, x, t):
    i = int(round(t * SR))
    if i >= N: return
    x = x[: N - i]
    bus[i:i + len(x)] += x


# ---- voice ----
vo = np.zeros((N, 2))
for l in lines:
    x, sr = sf.read(f"vo/{l['id']}.wav", dtype='float64')
    x = signal.resample_poly(x, SR // sr, 1) if sr != SR else x
    x = hp(x, 75, 2)
    if l['voice'] == 'agent':      # the agent is on a phone call: band-limit it, keep it clear
        x = hp(x, 260, 2); x = lp(x, 5200, 2); x = peq(x, 1800, 0.9, 3.0)
    else:                           # narrator and student: a little presence and air
        x = peq(x, 3500, 0.8, 1.5); x = peq(x, 180, 0.9, -1.0)
    x = x * db(-20.0 - lufs_integrated(np.c_[x, x]))   # every line at the same loudness
    place(vo, np.c_[x, x], T[l['id']])

# ---- sfx ----
fx = np.zeros((N, 2))
for cue in tl['sfx']:
    t, f, g = cue[:3]
    x, sr = sf.read(f'sfx/{f}.wav', dtype='float64')
    assert sr == SR
    if x.ndim == 1: x = np.c_[x, x]
    if len(cue) > 3:                 # cut short (e.g. the ringtone stops when the call is accepted)
        n = int((cue[3] - t) * SR); x = x[:n].copy(); k = min(n, int(0.06 * SR))
        x[n - k:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k)))[:, None]
    place(fx, x * db(g - 3.0), t)   # library peaks at -3 dBFS; cue gains are relative to that

# ---- music ----
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', music_file, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'],
                     capture_output=True, check=True).stdout
m = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)
mus = np.zeros((N, 2))
if m_off >= 0: place(mus, m, m_off)
else: mus[:] = m[int(-m_off * SR):int(-m_off * SR) + N]
mus *= db(m_gain - lufs_integrated(mus[:int(min(total, 200) * SR)]))   # music bed at m_gain LUFS when open

# duck: voice presence with 120 ms lookahead, fast attack, slow release
hop = SR // 100
env = np.sqrt(np.convolve((vo[:, 0] ** 2), np.ones(hop) / hop, 'same'))[::hop]
act = (20 * np.log10(env + 1e-9) > -48).astype(float)
act = maximum_filter1d(act, 12, origin=-5)                 # look ahead / bridge tiny gaps
act = minimum_filter1d(maximum_filter1d(act, 35), 35)       # don't swell in sub-0.35 s pauses
g = np.empty_like(act); a = 0.0
for i, v in enumerate(act):                                  # 1-pole smoothing: 60 ms down, 450 ms up
    k = 1 - np.exp(-1 / (6 if v > a else 45)); a += k * (v - a); g[i] = a
duck = db(-10.0 * g)                                        # -10 dB under the voice
duck = np.interp(np.arange(N), np.arange(len(duck)) * hop, duck)
fade = np.clip((total - np.arange(N) / SR) / 3.2, 0, 1) ** 1.6   # tail fade into black
mus *= (duck * fade)[:, None]

mix = vo + fx + mus

# ---- master: -14 LUFS integrated, true peak <= -1 dBTP ----
mix *= db(-14.0 - lufs_integrated(mix))
for _ in range(3):
    up = signal.resample_poly(mix, 4, 1, axis=0)
    pk = maximum_filter1d(np.max(np.abs(up), axis=1), 4 * 48)[::4][:N]   # 1 ms window, 4x oversampled
    need = np.minimum(1.0, db(-1.2) / np.maximum(pk, 1e-9))
    gl = minimum_filter1d(need, int(0.006 * SR), origin=0)                 # 6 ms lookahead hold
    sm = np.empty_like(gl); a = 1.0
    rel = 1 - np.exp(-1 / (0.12 * SR))
    for i in range(N):                                                     # instant attack, 120 ms release
        v = gl[i]; a = v if v < a else a + rel * (v - a); sm[i] = a
    mix *= sm[:, None]
    if true_peak_db(mix) <= -1.0: break
q = np.clip(np.round(mix * 32767), -32768, 32767).astype(np.int16)
sf.write(out, q, SR, subtype='PCM_16')
st_t, st_l = short_term(mix)
print(f'{out}: {total:.2f}s  integrated {lufs_integrated(mix):.2f} LUFS  true peak {true_peak_db(mix):.2f} dBTP  '
      f'short-term max {np.max(st_l):.1f}  vo {lufs_integrated(vo):.1f}  fx {lufs_integrated(fx):.1f}  music {lufs_integrated(mus):.1f}')
