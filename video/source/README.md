# 7even5ive film: source

The 4-minute Round 1 video is an HTML/GSAP composition rendered frame by frame. Everything is
timed from one file, `timeline.json`, so picture and sound cannot drift apart.

| Step | Command | What it does |
|---|---|---|
| 1 | (already done) `vo/*.wav` | Voiceover lines from `script.json`, made with the open-source Kokoro-82M TTS |
| 2 | `python schedule.py` | Places every line, scene cut and sound effect on the music's beat grid → `timeline.json` |
| 3 | `python gen_data.py` | Captions, beats and voice envelopes for the page → `comp/data.js` |
| 4 | `cd comp && npm install` | GSAP and the fonts (Inter Tight, Instrument Serif, JetBrains Mono, Noto Kannada/Devanagari) |
| 5 | `cd sfx_src && python make_sfx.py && python make_music.py` | Rebuilds the synthesised SFX library and the royalty-free music bed into `../sfx/` |
| 6 | `node render.js <k> 4` for k = 0..3 | Renders 1920×1080 @ 30 fps segments into `render/` (needs Playwright + Chromium + ffmpeg) |
| 7 | `python mix.py <music> <offset_s> -23 render/mix.wav` | Voice, word-synced SFX and ducked music, mastered to −14 LUFS / −1 dBTP |
| 8 | ffmpeg concat + mux | `ffmpeg -f concat -i list.txt -c copy video.mp4`, then mux the mix as AAC 320k |

Preview any moment with `node probe.js $PWD/comp 34.7 140 236` (writes JPEGs to `probe/`).
The licensed music track is not in this repository.
