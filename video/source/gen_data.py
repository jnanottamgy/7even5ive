"""Writes comp/data.js (timeline, captions, per-frame voice loudness) and comp/grain.png."""
import json, re, numpy as np, soundfile as sf
from PIL import Image

FPS = 30
tl = json.load(open('timeline.json'))
lines = json.load(open('vo/durations.json'))
beats = json.load(open('beats.json'))

DISPLAY = [
    (r'\bD B M S\b', 'DBMS'), (r'\bA I\b', 'AI'), (r'\bM C P\b', 'MCP'), (r'\bA W S\b', 'AWS'),
    (r'\bS Q S\b', 'SQS'), (r'Open A P I', 'OpenAPI'), (r'\bA P I\b', 'API'), (r'Eleven Labs', 'ElevenLabs'),
    (r'Agent Core', 'AgentCore'), (r'Event Bridge', 'EventBridge'), (r'Supa base', 'Supabase'),
    (r'Seven Five', '7even5ive'), (r'\bP M\b', 'PM'), (r'\bP D F\b', 'PDF'), (r'\bP Y Qs\b', 'PYQs'), (r'assignment three', 'Assignment 3'),
    (r'eleven fifty-nine', '11:59'), (r'seventy-three percent', '73%'), (r'Seventy-five percent', '75%'),
]

captions = []
for l in lines:
    if l['voice'] != 'narr':
        continue
    txt = l['text']
    for a, b in DISPLAY:
        txt = re.sub(a, b, txt)
    captions.append({'id': l['id'], 't': tl['T'][l['id']], 'e': tl['E'][l['id']], 'text': txt})

# per-frame loudness of each voice track, so visuals can react to speech
n = int(np.ceil(tl['total'] * FPS)) + 2
env = {'narr': np.zeros(n), 'agent': np.zeros(n), 'student': np.zeros(n)}
for l in lines:
    s, sr = sf.read(f"vo/{l['id']}.wav")
    if s.ndim > 1:
        s = s.mean(1)
    t0 = tl['T'][l['id']]
    hop = sr // FPS
    for k in range(len(s) // hop):
        f = int(round(t0 * FPS)) + k
        if 0 <= f < n:
            seg = s[k * hop:(k + 1) * hop]
            env[l['voice']][f] = max(env[l['voice']][f], float(np.sqrt((seg ** 2).mean())))
for k in env:
    m = env[k].max() or 1
    v = env[k] / m
    sm = np.copy(v)                       # light smoothing: fast attack, slower release
    for i in range(1, len(v)):
        sm[i] = v[i] if v[i] > sm[i - 1] else sm[i - 1] * 0.72 + v[i] * 0.28
    env[k] = [round(float(x), 3) for x in sm]

data = {**tl, 'captions': captions, 'env': env, 'beats': beats['beats'], 'downbeats': beats['downbeats'],
        'fps': FPS}
open('comp/data.js', 'w').write('window.TLD = ' + json.dumps(data) + ';')

rng = np.random.default_rng(7)
g = rng.normal(128, 46, (256, 256)).clip(0, 255).astype(np.uint8)
a = np.full((256, 256), 255, np.uint8)
Image.fromarray(np.dstack([g, g, g, a]), 'RGBA').save('comp/grain.png')
print('frames', n, 'captions', len(captions))
