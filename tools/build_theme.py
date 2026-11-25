#!/usr/bin/env python3
"""The recap's theme song: a college fight-band march composed for the week and played by a sampled band (the MuseScore General soundfont, through
FluidSynth), then cut into the pieces the player mixes: three looping stems that stack (0 the bass line and soft woodwinds, 1 adds the afterbeat horns and
trombones and the snare cadence, 2 adds the trumpet and piccolo melody, brass stabs and cymbal crashes) and the ending.

    python3 tools/build_theme.py --check     # needed=true/false: is there no theme for the current recap week yet?
    python3 tools/build_theme.py             # compose, render, write data/theme/*
    python3 tools/build_theme.py --keep      # also keep the .mid files in /tmp (to look at)

Needs: fluidsynth, the soundfont (apt: fluidsynth musescore-general-soundfont), ffmpeg and `pip install mido`.
Every week is a different march: key, strain order, chords and melody come from the week number, and the tempo is chosen so a whole number of 16-bar
loops fills the recap.
"""
import argparse, json, os, random, shutil, subprocess, sys, tempfile

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HUB, 'data', 'theme')
SF = next((p for p in ('/usr/share/sounds/sf3/MuseScore_General.sf3', '/usr/share/sounds/sf3/MuseScore_General_Full.sf3', '/usr/share/sounds/sf2/FluidR3_GM.sf2') if os.path.exists(p)), None)
TPB = 480

# General MIDI programs (0-based): the band
TUBA, TROMBONE, TRUMPET, HORN, BRASS, CLARINET, PICCOLO = 58, 57, 56, 60, 61, 71, 72
CH = {'tuba': 0, 'clarinet': 1, 'horn': 2, 'trombone': 3, 'trumpet': 4, 'piccolo': 5, 'brass': 6, 'drums': 9}
STEMS = {0: ['tuba', 'clarinet', 'drums0'], 1: ['horn', 'trombone', 'drums'], 2: ['trumpet', 'piccolo', 'brass', 'drums2']}
PROG = {'tuba': TUBA, 'trombone': TROMBONE, 'trumpet': TRUMPET, 'horn': HORN, 'brass': BRASS, 'clarinet': CLARINET, 'piccolo': PICCOLO}
VOL = {'tuba': 112, 'clarinet': 70, 'horn': 100, 'trombone': 100, 'trumpet': 112, 'piccolo': 84, 'brass': 108, 'drums': 110}

SCALE = [0, 2, 4, 5, 7, 9, 11]
STRAIN_A = [[(0, 'M'), (0, 'M'), (7, 'M'), (0, 'M')], [(0, 'M'), (5, 'M'), (0, 'M'), (7, 'M')], [(0, 'M'), (7, 'M'), (0, 'M'), (5, 'M')]]
STRAIN_B = [[(0, 'M'), (9, 'm'), (5, 'M'), (7, 'M')], [(5, 'M'), (7, 'M'), (0, 'M'), (9, 'm')], [(0, 'M'), (4, 'm'), (5, 'M'), (7, 'M')]]
CELLS = [   # a bar of melody: (start beat, length in beats): dotted fanfare rhythms and marching eighths
    [(0, .75), (.75, .25), (1, 1), (2, 2)], [(0, .5), (.5, .5), (1, .5), (1.5, .5), (2, 2)], [(0, 1), (1, .5), (1.5, .5), (2, 1), (3, 1)],
    [(0, .75), (.75, .25), (1, .75), (1.75, .25), (2, 1), (3, 1)], [(0, 1.5), (1.5, .5), (2, .5), (2.5, .5), (3, 1)], [(0, .5), (.5, .5), (1, 1), (2, .5), (2.5, .5), (3, 1)]
]


def triad(root, q):
    third = 3 if q in ('m', 'd') else 4
    return [root, root + third, root + (6 if q == 'd' else 7)]


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
            key = name.rstrip('0123456789')
            evs = self.ev.get(name, [])
            if not evs:
                continue
            ch = CH.get(key, 0)
            tr = mido.MidiTrack(); mid.tracks.append(tr)
            if key != 'drums':
                tr.append(mido.Message('program_change', channel=ch, program=PROG[key], time=0))
            tr.append(mido.Message('control_change', channel=ch, control=7, value=VOL.get(key, 100), time=0))
            tr.append(mido.Message('control_change', channel=ch, control=91, value=55, time=0))
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
    tonic = rnd.choice([46, 53, 51, 56, 48, 55])   # Bb, F, Eb, Ab, C, G: the band keys
    n = max(3, min(8, round(seconds * 126 / 3840)))   # whole 16-bar loops across the recap, at a march tempo near 126
    bpm = max(116, min(138, 3840.0 * n / seconds))
    loop_sec = 16 * 4 * 60.0 / bpm
    a, a2 = rnd.choice(STRAIN_A), rnd.choice(STRAIN_A)
    b = rnd.choice(STRAIN_B)
    c = rnd.choice(STRAIN_A)
    prog = a + a2 + b + c
    chords = [(tonic + off, q) for off, q in prog]
    chords[15] = (tonic + 7, 'M')   # the dominant turns the loop back to the start
    scale = [tonic + 24 + x for x in SCALE]   # melody: two octaves above the tonic
    lo_hi = {0: (72, 84), 1: (72, 84), 2: (74, 86), 3: (76, 88)}
    cells = [rnd.choice(CELLS) for _ in range(4)]
    mel, prev = [], None
    for bar in range(16):
        sec = bar // 4
        lo, hi = lo_hi[sec]
        root, q = chords[bar]
        tones = sorted({p for base in (root, root + 12, root + 24, root + 36, root + 48) for p in triad(base, q) if lo <= p <= hi})
        allowed = sorted({p + 12 * o for p in scale for o in (-1, 0, 1) if lo <= p + 12 * o <= hi})
        cell = cells[bar % 4] if sec != 1 else cells[(bar + 1) % 4]
        if bar % 4 == 3:
            cell = [(0, 1), (1, 1), (2, 2)] if rnd.random() < .5 else [(0, .75), (.75, .25), (1, 1), (2, 2)]   # a strain ends on a long note
        direction = 1 if (bar % 4) < 2 else -1
        for j, (st, ln) in enumerate(cell):
            if j == 0 or (bar % 4 == 3 and j == len(cell) - 1):
                target = prev if prev is not None else tones[len(tones) // 2]
                if bar % 4 == 0 and sec in (2, 3):
                    target = hi - 3   # the later strains open high
                pitch = min(tones, key=lambda p: (abs(p - target) + rnd.random() * 2))
            else:
                idx = min(range(len(allowed)), key=lambda i: abs(allowed[i] - prev))
                idx = max(0, min(len(allowed) - 1, idx + direction * rnd.choice([1, 1, 2])))
                pitch = allowed[idx]
            mel.append((bar * 4 + st, ln * .9, pitch))
            prev = pitch
    s = Song(bpm)
    for bar in range(16):
        root, q = chords[bar]
        t = triad(root, q)
        sec = bar // 4
        # stem 0: the oom of the oom-pah (tuba, root then fifth) and soft clarinet afterbeats, the bass drum
        s.note('tuba', bar * 4, .5, root - 12, 100); s.note('tuba', bar * 4 + 2, .5, t[2] - 12, 94)
        for beat in (1, 3):
            for p in (t[0] + 12, t[1] + 12, t[2] + 12):
                s.note('clarinet', bar * 4 + beat, .4, p + 12, 62)
        s.note('drums0', bar * 4, .3, 36, 84); s.note('drums0', bar * 4 + 2, .3, 36, 84)
        # stem 1: the pah (horns and trombones on the afterbeats), a trombone line, the snare cadence
        for beat in (1, 3):
            for p in (t[0] + 12, t[1] + 12, t[2] + 12):
                s.note('horn', bar * 4 + beat, .42, p, 98)
            s.note('trombone', bar * 4 + beat, .42, t[1], 92)
        s.note('trombone', bar * 4, 1.0, root, 90); s.note('trombone', bar * 4 + 2, 1.0, t[2] - 12 + 12, 86)
        cad = [0, .5, .75, 1, 1.5, 2, 2.5, 2.75, 3, 3.5] if bar % 2 == 0 else [0, .5, 1, 1.5, 1.75, 2, 2.5, 3, 3.25, 3.5, 3.75]
        for k, bt in enumerate(cad):
            s.note('drums', bar * 4 + bt, .15, 38, 96 if bt in (1, 3) else 70)
        if bar % 4 == 3:   # a snare roll and a tom run into the next strain
            for i in range(8):
                s.note('drums', bar * 4 + 2 + i * .25, .15, 38, 50 + i * 10)
            for i, nn in enumerate((45, 43, 41, 38)):
                s.note('drums', bar * 4 + 3.0 + i * .25, .2, nn, 100)
        # stem 2: stabs and crashes
        if bar % 4 == 0:
            s.note('drums2', bar * 4, 3.0, 49, 108 if sec in (0, 3) else 92); s.note('drums2', bar * 4, .5, 36, 118)
            for p in (root + 12, root + 19, root + 24):
                s.note('brass', bar * 4, .9, p, 112 if sec >= 2 else 100)
    for st, ln, p in mel:
        s.note('trumpet', st, ln, p, 104); s.note('piccolo', st, ln, p + 12 if p + 12 <= 96 else p, 82)
    return s, dict(mode='major', tonic=tonic, bpm=bpm, loops=n, loop=loop_sec), chords


def ending(plan, tonic, bpm):
    """The ending: the full band on the tonic chord, a bass-drum flourish, a long crash."""
    s = Song(bpm)
    for i in range(8):
        s.note('drums', i * .25, .2, 38, 50 + i * 10)
    s.note('drums', 2.0, .3, 36, 127); s.note('drums', 2.5, .3, 36, 120)
    for p in (tonic + 12, tonic + 19, tonic + 24, tonic + 28):
        s.note('brass', 2.0, 4.0, p, 118); s.note('horn', 2.0, 4.0, p, 108); s.note('trombone', 2.0, 4.0, p - 12, 108)
    s.note('trumpet', 2.0, 4.0, tonic + 40, 118); s.note('tuba', 2.0, 4.0, tonic - 12, 112); s.note('piccolo', 2.0, 4.0, tonic + 52, 90)
    s.note('drums', 2.0, 4.5, 49, 127)
    return s, 6


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
            wavs['l%d' % lv] = render(mid, os.path.join(OUT, 'l%d.mp3' % lv), -9.0)   # the three stems stack, so each is rendered with headroom
        es, etail = ending(plan, plan['tonic'], plan['bpm'])
        mid = os.path.join(tmp, 'end.mid')
        es.save(mid, ['tuba', 'horn', 'trombone', 'trumpet', 'piccolo', 'brass', 'drums'], etail)
        wavs['end'] = render(mid, os.path.join(OUT, 'end.mp3'), -8.0)
        if args.keep:
            for f in os.listdir(tmp):
                shutil.copy(os.path.join(tmp, f), os.path.join('/tmp', 'theme_' + f))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    for old in ('big.mp3', 'small.mp3'):
        try:
            os.remove(os.path.join(OUT, old))
        except OSError:
            pass
    info = {'week': week, 'seconds': seconds, 'bpm': round(plan['bpm'], 2), 'loop': round(plan['loop'], 3), 'loops': plan['loops'], 'key': '%s major' % names[plan['tonic'] % 12],
            'generatedAt': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    json.dump(info, open(os.path.join(OUT, 'plan.json'), 'w'), indent=1)
    print('theme: week %d, %s, %.1f bpm, loop %.1fs x %d' % (week, info['key'], info['bpm'], info['loop'], info['loops']))


if __name__ == '__main__':
    main()
