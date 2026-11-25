#!/usr/bin/env python3
"""The recap's theme song: composed for the week and played by a sampled orchestra (the MuseScore General soundfont, through FluidSynth), then cut
into the pieces the player mixes: three looping stems (0 strings, choir and basses; 1 adds cellos, timpani and snare cadence; 2 adds horns, trumpet,
violins and cymbals) and three one-shots (a big hit and a small hit for the card changes, and the ending).

    python3 tools/build_theme.py --check     # needed=true/false: is there no theme for the current recap week yet?
    python3 tools/build_theme.py             # compose, render, write data/theme/*
    python3 tools/build_theme.py --keep      # also keep the .mid files next to the audio (to look at)

Needs: fluidsynth, the soundfont (apt: fluidsynth musescore-general-soundfont), ffmpeg and `pip install mido`.
Every week is a different piece: key, mode, chord progression, melody and tempo come from the week number, and the tempo is chosen so a whole number of
16-bar loops fills the recap.
"""
import argparse, json, os, random, shutil, subprocess, sys, tempfile

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HUB, 'data', 'theme')
SF = next((p for p in ('/usr/share/sounds/sf3/MuseScore_General.sf3', '/usr/share/sounds/sf3/MuseScore_General_Full.sf3', '/usr/share/sounds/sf2/FluidR3_GM.sf2') if os.path.exists(p)), None)
TPB = 480

# General MIDI programs (0-based)
STRINGS, CHOIR, BASS, CELLO, VIOLA, VIOLIN, HORN, TRUMPET, BRASS, TIMP = 49, 52, 43, 42, 41, 40, 60, 56, 61, 47
CH = {'strings': 0, 'choir': 1, 'bass': 2, 'cello': 3, 'viola': 4, 'timp': 5, 'horn': 6, 'trumpet': 7, 'brass': 8, 'violin': 10, 'drums': 9, 'low': 11}
STEMS = {0: ['strings', 'choir', 'bass'], 1: ['cello', 'viola', 'timp', 'drums'], 2: ['horn', 'trumpet', 'brass', 'violin', 'drums2']}
PROG = {'strings': STRINGS, 'choir': CHOIR, 'bass': BASS, 'cello': CELLO, 'viola': VIOLA, 'timp': TIMP, 'horn': HORN, 'trumpet': TRUMPET, 'brass': BRASS, 'violin': VIOLIN, 'low': BASS}
VOL = {'strings': 78, 'choir': 56, 'bass': 100, 'cello': 100, 'viola': 84, 'timp': 112, 'horn': 96, 'trumpet': 100, 'brass': 100, 'violin': 88, 'drums': 100, 'low': 100}

MINOR = [(0, 'm'), (2, 'd'), (3, 'M'), (5, 'm'), (7, 'm'), (8, 'M'), (10, 'M')]
MAJOR = [(0, 'M'), (2, 'm'), (4, 'm'), (5, 'M'), (7, 'M'), (9, 'm'), (11, 'd')]
PROGS = {   # (semitones above the tonic, quality)
    'minor': [[(0, 'm'), (8, 'M'), (3, 'M'), (10, 'M')], [(0, 'm'), (10, 'M'), (8, 'M'), (10, 'M')], [(0, 'm'), (5, 'm'), (8, 'M'), (7, 'M')], [(0, 'm'), (3, 'M'), (10, 'M'), (8, 'M')]],
    'major': [[(0, 'M'), (7, 'M'), (9, 'm'), (5, 'M')], [(0, 'M'), (9, 'm'), (5, 'M'), (7, 'M')], [(9, 'm'), (5, 'M'), (0, 'M'), (7, 'M')]]
}
SCALES = {'minor': [0, 2, 3, 5, 7, 8, 10], 'major': [0, 2, 4, 5, 7, 9, 11]}
CELLS = [   # a bar of melody: (start beat, length in beats)
    [(0, 1.5), (1.5, .5), (2, 2)], [(0, 1), (1, 1), (2, 2)], [(0, 3), (3, 1)], [(0, 2), (2, 1), (3, 1)],
    [(0, 1.5), (1.5, .5), (2, 1), (3, 1)], [(0, 4)]
]


def triad(root, q):
    third = 3 if q in ('m', 'd') else 4
    fifth = 6 if q == 'd' else 7
    return [root, root + third, root + fifth]


class Song:
    def __init__(self, bpm):
        self.bpm = bpm
        self.ev = {}   # channel name -> [(tick, order, message tuple)]

    def add(self, ch, beat, msg, order=1):
        self.ev.setdefault(ch, []).append((int(round(beat * TPB)), order, msg))

    def note(self, ch, beat, dur, pitch, vel):
        self.add(ch, beat, ('on', int(pitch), int(max(1, min(127, vel)))), 2)
        self.add(ch, beat + dur, ('off', int(pitch)), 0)

    def cc(self, ch, beat, num, val):
        self.add(ch, beat, ('cc', num, int(max(0, min(127, val)))), 1)

    def ramp(self, ch, beat, dur, a, b, steps=8):   # an expression crescendo or fade
        for i in range(steps + 1):
            self.cc(ch, beat + dur * i / steps, 11, a + (b - a) * i / steps)

    def save(self, path, chans, tail_beats):
        import mido
        mid = mido.MidiFile(type=1, ticks_per_beat=TPB)
        meta = mido.MidiTrack(); meta.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(self.bpm), time=0)); mid.tracks.append(meta)
        end = 0
        for name in chans:
            key = name.rstrip('2')
            evs = self.ev.get(name, [])
            if not evs:
                continue
            ch = CH.get(key, 0)
            tr = mido.MidiTrack(); mid.tracks.append(tr)
            if key != 'drums':
                tr.append(mido.Message('program_change', channel=ch, program=PROG[key], time=0))
            tr.append(mido.Message('control_change', channel=ch, control=7, value=VOL.get(key, 100), time=0))
            tr.append(mido.Message('control_change', channel=ch, control=91, value=70, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=11, value=127, time=0))
            last = 0
            for tick, _, m in sorted(evs, key=lambda e: (e[0], e[1])):
                if m[0] == 'on':
                    msg = mido.Message('note_on', channel=ch, note=m[1], velocity=m[2], time=tick - last)
                elif m[0] == 'off':
                    msg = mido.Message('note_off', channel=ch, note=m[1], velocity=0, time=tick - last)
                else:
                    msg = mido.Message('control_change', channel=ch, control=m[1], value=m[2], time=tick - last)
                tr.append(msg); last = tick; end = max(end, tick)
        endtr = mido.MidiTrack(); mid.tracks.append(endtr)   # silence after the last note, so the reverb tail is rendered
        endtr.append(mido.Message('control_change', channel=15, control=7, value=100, time=end + int(tail_beats * TPB)))
        mid.save(path)


def compose(week, seconds):
    rnd = random.Random(week * 7919 + 13)
    mode = rnd.choice(['minor', 'minor', 'major'])
    tonic = rnd.choice([57, 58, 60, 62, 64, 65, 67]) - 12 if mode == 'minor' else rnd.choice([57, 60, 62, 64, 65, 67]) - 12   # tonic pitch around A2..G3
    prog = rnd.choice(PROGS[mode])
    n = max(3, min(8, round(seconds * 108 / 3840)))   # whole 16-bar loops across the recap, at a tempo near 108
    bpm = 3840.0 * n / seconds
    bpm = max(96, min(120, bpm))
    loop_sec = 16 * 4 * 60.0 / bpm
    s = Song(bpm)
    scale = [tonic + 12 + x for x in SCALES[mode]]   # one octave of the key, an octave above the tonic
    chords = []
    for bar in range(16):
        off, q = prog[bar % 4]
        if bar == 15:
            off, q = 7, 'M'   # the dominant turns the loop back to the start
        chords.append((tonic + off, q))
    # the melody: chord tones on the strong beats, steps between them
    lo_hi = {0: (67, 79), 1: (69, 81), 2: (69, 81), 3: (72, 84)}
    cells = [rnd.choice(CELLS[:5]) for _ in range(4)]
    prev = None
    mel = []
    for bar in range(16):
        sec = bar // 4
        lo, hi = lo_hi[sec]
        root, q = chords[bar]
        tones = []
        for base in (root, root + 12, root + 24, root + 36):
            tones += [p for p in (triad(base, q)) if lo <= p <= hi]
        tones = sorted(set(tones))
        allowed = sorted({p + 12 * o for p in scale for o in (-1, 0, 1) if lo <= p + 12 * o <= hi})
        cell = cells[bar % 4] if sec != 3 else cells[(bar + 1) % 4]
        if bar % 4 == 3:
            cell = [(0, 2), (2, 2)] if rnd.random() < .5 else [(0, 4)]   # a phrase ends on a long note
        direction = 1 if (bar % 4) < 2 else -1
        for j, (st, ln) in enumerate(cell):
            if j == 0 or bar % 4 == 3 and j == len(cell) - 1:
                pool = tones
                target = prev if prev is not None else tones[len(tones) // 2]
                if bar % 4 == 0 and sec == 3:
                    target = hi - 2   # the last section opens high
                pitch = min(pool, key=lambda p: (abs(p - target) + rnd.random() * 2))
            else:
                idx = min(range(len(allowed)), key=lambda i: abs(allowed[i] - prev))
                idx = max(0, min(len(allowed) - 1, idx + direction * rnd.choice([1, 1, 2])))
                pitch = allowed[idx]
            mel.append((bar * 4 + st, ln * .96, pitch))
            prev = pitch
    # ---- stem 0: the bed
    for bar in range(16):
        root, q = chords[bar]
        t = triad(root + 12, q)
        for p in t:
            s.note('strings', bar * 4, 4.05, p, 58 + (6 if bar % 4 == 3 else 0))
        s.note('strings', bar * 4, 4.05, root + 24, 50)
        s.note('choir', bar * 4, 4.05, root + 24, 46)
        s.note('choir', bar * 4, 4.05, t[1] + 12, 40)
        s.note('bass', bar * 4, 4.0, root - 12 + 12 if root - 12 < 28 else root - 12, 78)
        if bar % 4 == 3:
            s.ramp('strings', bar * 4, 4, 100, 127)
            s.ramp('choir', bar * 4, 4, 100, 127)
        else:
            s.cc('strings', bar * 4, 11, 100); s.cc('choir', bar * 4, 11, 100)
    # ---- stem 1: the drive
    for bar in range(16):
        root, q = chords[bar]
        t = triad(root, q)
        # cellos and violas in marcato eighths on root, fifth and octave
        for k in range(8):
            step = [0, 2, 1, 2][k % 4]
            acc = 96 if k % 4 == 0 else 74
            s.note('cello', bar * 4 + k * .5, .42, t[step] + 12 if step else t[0] + 12, acc)
            s.note('viola', bar * 4 + k * .5, .42, t[[1, 2, 1, 2][k % 4]] + 24, acc - 14)
        # timpani on the root, beats one and three
        s.note('timp', bar * 4, .5, root + 12 if root + 12 <= 52 else root, 100)
        s.note('timp', bar * 4 + 2, .5, root + 7 + 12 if root + 19 <= 55 else root + 7, 84)
        if bar % 4 == 3:   # a roll into the next phrase
            for i in range(8):
                s.note('timp', bar * 4 + 2 + i * .25, .24, root + 12 if root + 12 <= 52 else root, 60 + i * 8)
        # a snare cadence: the backbeat, a roll at the end of each phrase
        s.note('drums', bar * 4 + 1, .2, 38, 62); s.note('drums', bar * 4 + 3, .2, 38, 70)
        if bar % 4 == 3:
            for i in range(8):
                s.note('drums', bar * 4 + 2 + i * .25, .2, 38, 45 + i * 9)
    # ---- stem 2: the horns, trumpet and violins, and the cymbals
    for bar in range(16):
        root, q = chords[bar]
        t = triad(root + 12, q)
        for p in t:
            s.note('horn', bar * 4, 4.0, p, 82)
        sec = bar // 4
        if bar % 4 == 0:
            s.note('drums2', bar * 4, 3.5, 49, 100 if sec in (0, 3) else 84)
            s.note('drums2', bar * 4, .5, 36, 110)
            for p in (root + 12, root + 19, root + 24):
                s.note('brass', bar * 4, 1.0, p, 108 if sec == 3 else 96)
        if bar % 4 == 3:
            s.ramp('horn', bar * 4, 4, 96, 127); s.ramp('trumpet', bar * 4, 4, 100, 127)
    for st, ln, p in mel:
        s.note('trumpet', st, ln, p, 96); s.note('violin', st, ln, p + 12, 74); s.note('horn', st, ln, p - 12 if p - 12 >= 55 else p, 70)
    return s, dict(mode=mode, tonic=tonic, bpm=bpm, loops=n, loop=loop_sec, prog=[c[0] - tonic for c in chords[:4]], progq=[c[1] for c in chords[:4]]), chords


def hits(plan, tonic, mode, bpm):
    third = 3 if mode == 'minor' else 4
    out = {}
    # a big hit: a timpani roll into a full-orchestra open chord, bass drum and cymbal
    s = Song(bpm)
    for i in range(6):
        s.note('timp', i * .25, .3, tonic + 12 if tonic + 12 <= 52 else tonic, 70 + i * 9)
    for p in (tonic, tonic + 7, tonic + 12, tonic + 19):
        s.note('brass', 1.5, 2.5, p + 12, 120); s.note('horn', 1.5, 2.5, p + 12, 112); s.note('strings', 1.5, 3.5, p + 12, 100)
    s.note('trumpet', 1.5, 2.2, tonic + 31, 112); s.note('bass', 1.5, 3, tonic - 12 + 12, 110)
    s.note('drums', 1.5, 3.5, 49, 120); s.note('drums', 1.5, .5, 36, 127); s.note('timp', 1.5, 1.0, tonic + 12 if tonic + 12 <= 52 else tonic, 127)
    out['big'] = (s, 5)
    # a small hit: two drum strokes and a short brass stab
    s = Song(bpm)
    s.note('timp', 0, .4, tonic + 12 if tonic + 12 <= 52 else tonic, 100); s.note('timp', .5, .4, tonic + 19 if tonic + 19 <= 55 else tonic + 7, 110)
    for p in (tonic + 12, tonic + 19, tonic + 24):
        s.note('brass', .5, .8, p, 104); s.note('horn', .5, .8, p, 96)
    s.note('drums', .5, 1.5, 49, 80); s.note('drums', .5, .4, 36, 112)
    out['small'] = (s, 3)
    # the ending: a held chord resolved to the tonic (a major third at last, for a lift), a roll, a crash
    s = Song(bpm)
    for i in range(8):
        s.note('timp', i * .25, .3, tonic + 12 if tonic + 12 <= 52 else tonic, 64 + i * 8)
    chord = [tonic, tonic + 7, tonic + 12, tonic + 12 + 4, tonic + 19]
    for p in chord:
        s.note('brass', 2.0, 5, p + 12, 118); s.note('horn', 2.0, 5, p + 12, 108); s.note('strings', 2.0, 6, p + 12, 100)
    s.note('trumpet', 2.0, 4.5, tonic + 28, 112); s.note('bass', 2.0, 5, tonic, 110)
    s.note('drums', 2.0, 5, 49, 120); s.note('drums', 2.0, .5, 36, 127); s.note('timp', 2.0, 1.0, tonic + 12 if tonic + 12 <= 52 else tonic, 127)
    s.ramp('strings', 2.0, 6, 127, 40); s.ramp('horn', 2.0, 6, 127, 40)
    out['end'] = (s, 6)
    return out


def render(mid, mp3, gain_db=0.0, tail_trim=None):
    wav = mid[:-4] + '.wav'
    subprocess.run(['fluidsynth', '-ni', '-g', '0.9', '-r', '44100', '-F', wav, SF, mid], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    af = ['-af', 'volume=%.2fdB' % gain_db] if gain_db else []
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav] + af + ['-c:a', 'libmp3lame', '-b:a', '112k', '-ar', '44100', mp3], check=True)
    return wav


def current_week():
    try:
        return int(json.load(open(os.path.join(HUB, 'data', 'recap.json'))).get('week') or 0)
    except Exception:
        return 0


def needed():
    wk = current_week()
    if not wk:
        return False
    try:
        return int(json.load(open(os.path.join(OUT, 'plan.json'))).get('week') or 0) != wk
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--week', type=int)
    ap.add_argument('--seconds', type=int)
    args = ap.parse_args()
    if args.check:
        out = 'true' if needed() else 'false'
        print('needed=' + out)
        if os.environ.get('GITHUB_OUTPUT'):
            open(os.environ['GITHUB_OUTPUT'], 'a').write('needed=%s\n' % out)
        return
    if not SF:
        sys.exit('no soundfont (apt install musescore-general-soundfont)')
    rec = {}
    try:
        rec = json.load(open(os.path.join(HUB, 'data', 'recap.json')))
    except Exception:
        pass
    week = args.week or int(rec.get('week') or 0)
    seconds = args.seconds or int(rec.get('seconds') or 170)
    if not week:
        sys.exit('no recap week yet')
    song, plan, chords = compose(week, seconds)
    tmp = tempfile.mkdtemp()
    os.makedirs(OUT, exist_ok=True)
    wavs = {}
    try:
        for lv, chans in STEMS.items():
            mid = os.path.join(tmp, 'l%d.mid' % lv)
            song.save(mid, chans, 8)   # two bars of tail for the reverb
            wavs['l%d' % lv] = render(mid, os.path.join(OUT, 'l%d.mp3' % lv))
        for name, (hs, tail) in hits(plan, plan['tonic'], plan['mode'], plan['bpm']).items():
            mid = os.path.join(tmp, name + '.mid')
            hs.save(mid, ['timp', 'brass', 'horn', 'strings', 'trumpet', 'bass', 'drums'], tail)
            wavs[name] = render(mid, os.path.join(OUT, name + '.mp3'))
        if args.keep:
            for f in os.listdir(tmp):
                shutil.copy(os.path.join(tmp, f), os.path.join('/tmp', 'theme_' + f))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    info = {'week': week, 'seconds': seconds, 'bpm': round(plan['bpm'], 2), 'loop': round(plan['loop'], 3), 'loops': plan['loops'], 'key': '%s %s' % (names[plan['tonic'] % 12], plan['mode']),
            'generatedAt': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    json.dump(info, open(os.path.join(OUT, 'plan.json'), 'w'), indent=1)
    print('theme: week %d, %s, %.1f bpm, loop %.1fs x %d' % (week, info['key'], info['bpm'], info['loop'], info['loops']))


if __name__ == '__main__':
    main()
