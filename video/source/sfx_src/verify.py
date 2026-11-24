"""Numeric + visual sanity checks for every WAV in ../sfx.

Prints a table (ffprobe format facts, peak/RMS, DC, clipping, boundary samples, leading
silence, spectral balance, L/R correlation) and writes spectrogram contact sheets.
Usage: python verify.py [--sheets DIR]
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
SFX = os.path.normpath(os.path.join(HERE, "..", "sfx"))


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,sample_rate,channels,bits_per_sample:format=duration",
         "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    return dict(dur=float(j["format"]["duration"]), sr=int(s["sample_rate"]),
                ch=int(s["channels"]), codec=s["codec_name"], bits=int(s.get("bits_per_sample", 0)))


def band_fractions(x, sr):
    m = x.mean(axis=1)
    P = np.abs(np.fft.rfft(m)) ** 2  # no window: transients sit at t=0
    f = np.fft.rfftfreq(len(m), 1 / sr)
    tot = P.sum() + 1e-30
    frac = lambda lo, hi: P[(f >= lo) & (f < hi)].sum() / tot
    centroid = (f * P).sum() / tot
    return dict(lt100=frac(0, 100), lt200=frac(0, 200), gt1k=frac(1000, 1e9),
                gt5k=frac(5000, 1e9), centroid=centroid)


def analyse(path):
    info = ffprobe(path)
    raw, sr = sf.read(path, dtype="int16", always_2d=True)
    x = raw.astype(float) / 32768.0
    a = np.abs(x).max(axis=1)
    pk = a.max()
    lead = int(np.argmax(a > pk * 10 ** (-60 / 20))) / sr * 1000
    bf = band_fractions(x, sr)
    corr = np.corrcoef(x[:, 0], x[:, 1])[0, 1] if np.std(x[:, 0]) > 0 and np.std(x[:, 1]) > 0 else 1.0
    return dict(
        name=os.path.basename(path), **info, n=len(x),
        nan=bool(np.isnan(x).any()),
        clip=int((np.abs(raw.astype(int)) >= 32767).sum()),
        peak_db=20 * np.log10(pk + 1e-30),
        rms_db=20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-30),
        dc=float(np.abs(x.mean(axis=0)).max()),
        first=int(np.abs(raw[0]).max()), last=int(np.abs(raw[-1]).max()),
        lead_ms=lead, t_peak=float(np.argmax(a)) / sr, corr=corr, **bf)


def sheet(paths, out_png, cols=4):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal

    rows = int(np.ceil(len(paths) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.6, rows * 2.6), squeeze=False)
    for ax, p in zip(axes.flat, paths):
        x, sr = sf.read(p, always_2d=True)
        m = x.mean(axis=1)
        nper = 1024 if len(m) > 20000 else 256
        f, tt, S = signal.spectrogram(m, sr, nperseg=nper, noverlap=nper * 3 // 4, window="hann")
        S = 10 * np.log10(S + 1e-14)
        ax.pcolormesh(tt, np.maximum(f, 1), S, vmin=S.max() - 80, vmax=S.max(), shading="auto",
                      cmap="magma")
        ax.set_yscale("log")
        ax.set_ylim(20, 22000)
        env = np.abs(m)
        k = max(1, len(m) // 400)
        envd = env[: len(env) // k * k].reshape(-1, k).max(axis=1)
        te = np.arange(len(envd)) * k / sr
        ax2 = ax.twinx()
        ax2.plot(te, 20 * np.log10(envd + 1e-9), color="cyan", lw=0.8)
        ax2.set_ylim(-80, 0)
        ax2.set_yticks([])
        ax.set_title(os.path.basename(p), fontsize=9)
        ax.tick_params(labelsize=7)
    for ax in list(axes.flat)[len(paths):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_png, dpi=72)
    plt.close(fig)


def main():
    paths = sorted(glob.glob(os.path.join(SFX, "*.wav")))
    rows = [analyse(p) for p in paths]
    hdr = ("file", "dur", "sr", "ch", "fmt", "peak", "rms", "dc", "clip", "b0", "bN", "lead",
           "tpk", "<100", "<200", ">1k", ">5k", "cent", "corr")
    print("{:22s} {:>6s} {:>5s} {:>2s} {:>9s} {:>6s} {:>6s} {:>7s} {:>4s} {:>3s} {:>3s} {:>5s} "
          "{:>5s} {:>5s} {:>5s} {:>5s} {:>5s} {:>6s} {:>5s}".format(*hdr))
    for r in rows:
        print("{name:22s} {dur:6.3f} {sr:5d} {ch:2d} {codec:>9s} {peak_db:6.2f} {rms_db:6.1f} "
              "{dc:7.5f} {clip:4d} {first:3d} {last:3d} {lead_ms:5.1f} {t_peak:5.2f} {lt100:5.2f} "
              "{lt200:5.2f} {gt1k:5.2f} {gt5k:5.2f} {centroid:6.0f} {corr:5.2f}".format(**r))
    bad = [r["name"] for r in rows if r["sr"] != 48000 or r["ch"] != 2 or r["codec"] != "pcm_s16le"
           or r["nan"] or r["clip"] or r["first"] > 2 or r["last"] > 2]
    print("FORMAT/BOUNDARY PROBLEMS:", bad or "none")
    if "--sheets" in sys.argv:
        d = sys.argv[sys.argv.index("--sheets") + 1]
        os.makedirs(d, exist_ok=True)
        sfx_only = [p for p in paths if "music" not in os.path.basename(p)]
        half = (len(sfx_only) + 1) // 2
        sheet(sfx_only[:half], os.path.join(d, "sheet1.png"))
        sheet(sfx_only[half:], os.path.join(d, "sheet2.png"))
        print("sheets written to", d)


if __name__ == "__main__":
    main()
