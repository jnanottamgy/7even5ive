"""Builds timeline.json: when every voice line starts, scene cut times, and SFX cues.
Visuals (index.html) and the audio mix (mix.py) both read this file, so they cannot drift."""
import json, bisect

lines = json.load(open('vo/durations.json'))
beats = json.load(open('beats.json'))['beats']
D = {l['id']: l['dur'] for l in lines}
order = [l['id'] for l in lines]
scene_of = {l['id']: l['scene'] for l in lines}

GAP = 0.42                       # default pause between lines inside a scene
CUSTOM = {                       # pause BEFORE this line (overrides GAP)
    'L02': 0.95, 'L03': 0.85, 'L04': 1.35,
    'L06': 0.3, 'L07': 0.3, 'L07a': 0.45, 'L07b': 0.45, 'L07c': 0.5, 'L07d': 0.75, 'L08': 0.75,
    'L10': 0.55, 'L10b': 0.6,
    'L12': 0.45, 'L14': 0.6, 'L15': 0.5, 'L17': 0.6, 'L18': 0.45, 'L18a': 1.0, 'L18a2': 0.45, 'L18b': 0.45, 'L18c': 0.9,
    'L20': 0.5, 'D01': 1.9, 'D02': 0.45, 'D03': 0.35, 'L21': 1.0, 'L22': 0.6, 'L23': 0.55,
    'L25': 0.7, 'L26': 0.7, 'L27': 0.9, 'L28': 0.85, 'L29': 0.55, 'L30': 0.55, 'L31': 0.6,
    'L32': 0.5, 'L33': 0.55,
    'L35': 0.5, 'L36': 0.45, 'L37': 0.45, 'L38': 0.5,
    'L40': 0.45,
    'L43': 0.5, 'L45': 0.45,
}


def next_beat(t):
    i = bisect.bisect_left(beats, t)
    return beats[i] if i < len(beats) else t


T, E, cuts = {}, {}, {}
t = 2.4                          # first word after the string intro settles
scene = None
for lid in order:
    s = scene_of[lid]
    if s != scene:
        if scene is None:
            cuts['hook'] = 0.0
        elif s == 'problem':
            cuts['problem'] = 18.785                     # the drop
            t = cuts['problem'] + 0.75
        elif s == 'reveal':
            cut = next_beat(E[prev] + 0.4)               # collapse starts on a beat
            cuts['reveal'] = cut
            impact = [b for b in json.load(open('beats.json'))['downbeats'] if b >= cut + 1.2][0]
            cuts['reveal_impact'] = impact               # ring fills to 75% on a downbeat
            t = impact + 1.45
        else:
            cut = next_beat(E[prev] + 0.5)
            cuts[s] = cut
            t = cut + (0.7 if s != 'safety' else 0.9)
        scene = s
    else:
        t = E[prev] + CUSTOM.get(lid, GAP)
    T[lid] = round(t, 3)
    E[lid] = round(t + D[lid], 3)
    prev = lid

cuts['endcard'] = round(E['L45'] + 0.6, 3)
total = round(E['L45'] + 3.6, 3)

# ---- SFX cues: (time, file, gain_db) ----
c = []
def cue(t, f, g=0.0, until=None): c.append([round(t, 3), f, g] + ([round(until, 3)] if until else []))
TXT = {l['id']: l['text'] for l in json.load(open('script.json'))}
def wt(lid, idx):                # same estimate as wordTime() in comp/core.js
    lens = [len(w) + 2 for w in TXT[lid].split(' ')]
    return T[lid] + (E[lid] - T[lid]) * 0.92 * sum(lens[:idx]) / sum(lens)

# hook
def extra():
    # the notes hunt
    cue(T['L07a'] - 0.45, 'whoosh_long', -9)
    for k, wi in enumerate((3, 6, 8, 10, 12)):
        cue(wt('L07b', wi), 'swipe_up', -15)
    cue(wt('L07b', 21), 'error_buzz', -11)
    # the track card, then the idea
    cue(cuts['track'] - 0.1, 'whoosh_short', -9); cue(wt('L08b', 3), 'shimmer', -12)
    # the MCP connector
    for wi in (11, 13, 14, 16):
        cue(wt('L10b', wi), 'pop_blip', -12)
    cue(wt('L10b', 22), 'typing_ticks', -14); cue(wt('L10b', 26) + 0.3, 'data_blip', -10)
    # the placement mail nobody read
    cue(T['L07d'] - 0.5, 'whoosh_short', -9); cue(wt('L07d', 13), 'tick_clock', -8); cue(wt('L07d', 13) + 0.25, 'lock_clunk', -8)
    cue(T['L08'] - 0.45, 'whoosh_long', -10)
    # the library
    cue(T['L18a'] - 0.5, 'whoosh_short', -9)
    for wi in (0, 3, 5):
        cue(wt('L18a2', wi), 'swipe_up', -13)
    for wi in (10, 11, 13):
        cue(wt('L18a2', wi), 'pop_blip', -11)
    cue(T['L18b'] + 0.1, 'typing_ticks', -13); cue(wt('L18b', 8), 'success_chime', -12)
    # college mail, filtered
    cue(T['L18c'] - 0.5, 'whoosh_short', -9); cue(wt('L18c', 6), 'scan_sweep', -13)
    for wi in (13, 14, 16):
        cue(wt('L18c', wi), 'pop_blip', -11)
cue(T['L01'] - 0.15, 'heartbeat', -4); cue(T['L01'] + 1.6, 'heartbeat', -6); cue(T['L02'] + 1.4, 'heartbeat', -7)
for k in range(3):                                # the 75 -> 74 -> 73 roll
    cue(T['L03'] + 0.6 + k * 0.55, 'tick_clock', -6)
cue(T['L03'] + 1.75, 'glitch_short', -8)
cue(T['L04'] + 0.0, 'sub_drop', -6)
cue(cuts['problem'] - 4.0, 'riser_4s', -7)
# problem
cue(cuts['problem'], 'impact_boom', -6); cue(cuts['problem'], 'whoosh_long', -8)
cue(T['L05'] + 0.2, 'pop_blip', -10)
cue(T['L06'] - 0.15, 'whoosh_short', -9)
for k in range(9):                                # notification storm across L07
    cue(T['L07'] + 0.25 + k * 0.48, 'notif_ping_1' if k % 2 == 0 else 'notif_ping_2', -13 - (k % 3))
cue(T['L07'] + 3.2, 'phone_buzz', -12)
cue(T['L08'] + 0.0, 'error_buzz', -12); cue(T['L08'] + 0.95, 'error_buzz', -13)
# reveal
cue(cuts['reveal'] - 0.1, 'whoosh_long', -8)
cue(cuts['reveal_impact'] - 2.0, 'soft_riser_2s', -6)
cue(cuts['reveal_impact'], 'impact_boom', -4); cue(cuts['reveal_impact'] + 0.05, 'shimmer', -8)
# flow
cue(cuts['flow'], 'whoosh_short', -8)
cue(T['L11'] + 0.3, 'pop_blip', -10)
cue(T['L12'] + 0.3, 'scan_sweep', -12)
cue(T['L13'] + 0.35, 'swipe_up', -9); cue(wt('L13', 8), 'tap_soft', -6)
cue(T['L14'] + 0.2, 'click_ui', -6)
for k in range(4):
    cue(wt('L14', (11, 13, 16, 21)[k]), 'data_blip', -9)
cue(wt('L14', 18), 'scan_sweep', -12); cue(wt('L15', 6), 'pop_blip', -12)
cue(T['L17'] + 0.35, 'swipe_up', -8); cue(T['L17'] + 0.55, 'phone_buzz', -13)
cue(T['L18'] + 0.75, 'tap_soft', -4); cue(T['L18'] + 1.05, 'success_chime', -9)
# voice
cue(cuts['voice'], 'whoosh_short', -8)
cue(T['L19'] + 0.6, 'pop_blip', -10)
cue(T['L20'] + 0.15, 'phone_buzz', -9); cue(T['L20'] + 0.4, 'ringtone', -10, until=T['D01'] - 0.3)
cue(D['D01'] and T['D01'] - 0.35, 'click_ui', -10)
cue(E['D03'] - 0.2, 'success_chime', -11)
cue(T['L21'] + 0.3, 'whoosh_short', -10)
cue(T['L22'] + 0.4, 'scan_sweep', -12); cue(T['L22'] + 3.6, 'pop_blip', -11)
cue(T['L23'] + 0.3, 'swipe_up', -10)
# safety
cue(cuts['safety'], 'sub_drop', -6)
cue(T['L25'] + 0.1, 'notif_ping_2', -10); cue(wt('L25', 6) + 0.8, 'glitch_short', -10)
cue(T['L26'] + 0.5, 'error_buzz', -9)
cue(T['L27'] + 0.25, 'lock_clunk', -4)
cue(T['L28'] - 0.3, 'whoosh_long', -8)
for k in range(6):
    cue(T['L28'] + 1.2 + k * 1.1, 'data_blip', -10)
cue(T['L29'] + 0.2, 'typing_ticks', -12); cue(T['L29'] + 2.0, 'typing_ticks', -13)
cue(wt('L30', 15) - 0.08, 'glitch_short', -9); cue(wt('L30', 15) + 0.05, 'lock_clunk', -6)
cue(wt('L31', 7), 'tap_soft', -4); cue(wt('L31', 9), 'data_blip', -10); cue(wt('L31', 11) + 0.1, 'scan_sweep', -12); cue(wt('L31', 13), 'success_chime', -11)
cue(wt('L32', 2), 'click_ui', -6); cue(wt('L32', 5), 'glitch_short', -13); cue(wt('L32', 10) - 0.1, 'error_buzz', -8)
for k in range(3):
    cue(wt('L33', k) + 0.08, 'lock_clunk', -8)
cue(wt('L33', 3), 'whoosh_short', -12)
# aws
cue(cuts['aws'] - 0.2, 'whoosh_long', -8); cue(cuts['aws'] + 0.3, 'impact_boom', -10)
for k in range(8):
    cue(T['L35'] + 0.3 + k * 0.8, 'data_blip', -10)
cue(T['L36'] + 0.5, 'lock_clunk', -11)
cue(T['L37'] + 2.0, 'scan_sweep', -13); cue(T['L37'] + 6.5, 'pop_blip', -10)
cue(T['L38'] + 0.4, 'sub_drop', -10)
# forge
cue(cuts['forge'], 'whoosh_short', -8)
cue(T['L40'] + 0.6, 'typing_ticks', -12); cue(T['L40'] + 3.6, 'pop_blip', -10); cue(T['L40'] + 4.1, 'pop_blip', -10)
# close
cue(cuts['close'] - 2.0, 'soft_riser_2s', -8)
cue(cuts['close'], 'impact_boom', -7); cue(cuts['close'] + 0.1, 'shimmer', -9)

extra()
json.dump({'T': T, 'E': E, 'cuts': cuts, 'total': total, 'sfx': sorted(c)}, open('timeline.json', 'w'), indent=1)
print('cuts', {k: round(v, 2) for k, v in cuts.items()})
print('total', total)
for lid in order:
    print(lid, T[lid], E[lid])
