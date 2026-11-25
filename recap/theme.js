/* The recap's theme song, made with Web Audio when the page opens: no audio files. Dark, heavy and relentless, like the open to a primetime football game
   or a fight song: a minor key, war drums and a booming kick, a gritty low-brass riff, a choir holding the chords, trumpets and horns on a big fanfare,
   a cymbal and a riser into every phrase and a cinematic hit on every card change.
   Every week is a different tune (style, key, mode, chords, fanfare) from the week's number, and its tempo is set so the whole arrangement is exactly as
   long as the recap.

   Theme.setup({ seed, seconds })     plan the tune
   Theme.start()                      (from a tap) start the title-card loop
   Theme.card(type, i, n)             a card change: set the energy and hit it
   Theme.mute(on)  Theme.duck(on)     silence it (the sound button), or dip it while an NFL clip is playing with its own sound
   Theme.finish()  Theme.stop()       the closing hit; stop
   Theme.render(OfflineAudioContext, seconds, cards)   the same music into an offline buffer (tests and a listening sample) */
(function (global) {
  'use strict';

  function rng(seed) {
    var s = (seed >>> 0) || 1;
    return function () { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }
  function hz(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  var MODES = { minor: [0, 2, 3, 5, 7, 8, 10], harm: [0, 2, 3, 5, 7, 8, 11], phryg: [0, 1, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10] };
  var PROGS = {   // chord roots as scale degrees, one chord a bar
    minor: [[0, 5, 6, 0], [0, 6, 5, 4], [0, 3, 5, 6], [0, 0, 5, 6]],
    harm: [[0, 5, 4, 0], [0, 3, 5, 4], [0, 0, 5, 4], [0, 5, 2, 4]],
    phryg: [[0, 1, 0, 1], [0, 1, 5, 4], [0, 0, 1, 0]],
    dorian: [[0, 3, 6, 0], [0, 6, 3, 4], [0, 0, 3, 6]]
  };
  var HOOKS = [   // the fanfare: [start step in the bar, length in steps]; big, slow-burning, a trumpet call
    [[0, 4], [4, 2], [6, 2], [8, 6], [14, 2]],
    [[0, 2], [2, 2], [4, 4], [8, 4], [12, 4]],
    [[0, 6], [6, 2], [8, 4], [12, 2], [14, 2]],
    [[0, 3], [3, 1], [4, 4], [8, 3], [11, 1], [12, 4]]
  ];
  var STYLES = [   // heavy and driving; patterns are 16 sixteenth-note steps
    { name: 'primetime', bpm: [126, 136], modes: ['harm', 'minor'], kick: 'x..x..x.x.......', snare: '....x.......x...', riff: 'x.xx.x..x.xx.x..', ost: 'x.x.x.x.x.x.x.x.', stab: 'x.......x.......' },
    { name: 'heavy action', bpm: [122, 132], modes: ['minor', 'phryg'], kick: 'x..x..x.x..x....', snare: '....x.......x...', riff: 'x..x..x.x..x.x..', ost: 'x.x.x.x.x.x.x.x.', stab: 'x..x..x.........' },
    { name: 'fight song', bpm: [130, 140], modes: ['minor', 'harm'], kick: 'x...x...x...x...', snare: 'x.xxx.x.x.xxx.xx', riff: 'x.x.x.x.x.x.x.x.', ost: 'xxxxxxxxxxxxxxxx', stab: 'x...x...x...x...' },
    { name: 'main event', bpm: [120, 130], modes: ['dorian', 'harm', 'phryg'], kick: 'x.....x...x.x...', snare: '....x.......x..x', riff: 'xxx.xxx.xxx.xx..', ost: 'x.x.x.x.x.x.x.x.', stab: 'x.....x.x.......' }
  ];
  // how loud the arrangement is on each kind of card: 0 bed, 1 groove, 2 full
  var LEVELS = { intro: 2, game: 2, finals: 1, race: 1, clinch: 2, trades: 1, slack: 1, pod: 0, shotguns: 1, records: 2, lifetime: 1, coming: 2, wait: 0 };

  var plan = null, ctx = null, master = null, duckG = null, bus = null, gritIn = null, verb = null, noise = null, timer = null;
  var armed = false, silent = false, ducked = false, level = 2, nextT = 0, step = 0;

  function setup(o) {
    var r = rng((o.seed * 2654435761) >>> 0), st = STYLES[Math.floor(r() * STYLES.length)];
    var mode = st.modes[Math.floor(r() * st.modes.length)], seconds = Math.max(30, o.seconds || 150);
    var target = st.bpm[0] + r() * (st.bpm[1] - st.bpm[0]);
    var bars = Math.max(8, Math.round(seconds * target / 240)), bpm = bars * 240 / seconds;   // a whole number of bars fills the recap exactly
    plan = {
      style: st, mode: mode, scale: MODES[mode], bpm: bpm, bars: bars, sec16: 60 / bpm / 4, tonic: [0, 2, 3, 4, 5, 7][Math.floor(r() * 6)],
      prog: PROGS[mode][Math.floor(r() * PROGS[mode].length)], hook: HOOKS[Math.floor(r() * HOOKS.length)], hookDeg: [], seed: o.seed
    };
    var pool = [0, 4, 7, 4, 2, 7, 9, 6, 11, 7, 4, 0], k;   // fanfare tones: the minor triad and its octave, the flat seventh for bite
    for (k = 0; k < plan.hook.length; k++) plan.hookDeg.push(pool[Math.floor(r() * pool.length)]);
    plan.hookDeg[0] = r() < .6 ? 4 : 0; plan.hookDeg[plan.hookDeg.length - 1] = [0, 4, 7][Math.floor(r() * 3)];
    return plan;
  }

  function note(deg, oct) {   // scale degree (any size) -> midi
    var n = plan.scale.length, o = Math.floor(deg / n), d = ((deg % n) + n) % n;
    return plan.tonic + 12 * (oct + 1 + o) + plan.scale[d];   // octave 3 is the one above middle C's lower neighbour (C3 = 48)
  }

  // ------------------------------------------------------------------ the band
  function mkNoise(c) {
    var b = c.createBuffer(1, c.sampleRate, c.sampleRate), d = b.getChannelData(0), i, s = 22222;
    for (i = 0; i < d.length; i++) { s = (s * 1664525 + 1013904223) >>> 0; d[i] = (s / 2147483648) - 1; }
    return b;
  }
  function mkVerb(c) {   // a stadium
    var len = Math.floor(c.sampleRate * 2.6), b = c.createBuffer(2, len, c.sampleRate), ch, i, s = 777;
    for (ch = 0; ch < 2; ch++) { var d = b.getChannelData(ch); for (i = 0; i < len; i++) { s = (s * 1664525 + 1013904223) >>> 0; d[i] = ((s / 2147483648) - 1) * Math.pow(1 - i / len, 2.2); } }
    var cv = c.createConvolver(); cv.buffer = b; return cv;
  }
  function mkGrit(c) {   // a distortion bus for the riff: it turns clean saws into something that growls
    var ws = c.createWaveShaper(), n = 2048, cur = new Float32Array(n), i, x;
    for (i = 0; i < n; i++) { x = i * 2 / n - 1; cur[i] = Math.tanh(x * 7) * .8; }
    ws.curve = cur; ws.oversample = '2x';
    var inp = c.createGain(), lp = c.createBiquadFilter(), hp = c.createBiquadFilter();
    hp.type = 'highpass'; hp.frequency.value = 70; lp.type = 'lowpass'; lp.frequency.value = 2600;
    inp.connect(ws); ws.connect(hp); hp.connect(lp); lp.connect(bus);
    return inp;
  }
  function env(g, t, a, peak, hold, rel) {
    peak = Math.max(peak, 0.0002);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(peak, t + a);
    g.gain.setValueAtTime(peak, t + a + hold); g.gain.exponentialRampToValueAtTime(0.0001, t + a + hold + rel);
  }
  function send(g, amt) { var s = ctx.createGain(); s.gain.value = amt; g.connect(s); s.connect(verb); }
  function kick(c, t, v) {   // a big, round kick with a beater click
    var o = c.createOscillator(), g = c.createGain(), n = c.createBufferSource(), f = c.createBiquadFilter(), ng = c.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(155, t); o.frequency.exponentialRampToValueAtTime(42, t + .12); env(g, t, .003, v, .03, .34);
    o.connect(g); g.connect(bus); o.start(t); o.stop(t + .5);
    n.buffer = noise; f.type = 'highpass'; f.frequency.value = 2500; env(ng, t, .001, v * .25, .002, .015); n.connect(f); f.connect(ng); ng.connect(bus); n.start(t, Math.random() * .5); n.stop(t + .05);
  }
  function boom(c, t, v) {   // the cinematic sub drop
    var o = c.createOscillator(), g = c.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(85, t); o.frequency.exponentialRampToValueAtTime(30, t + 1.0); env(g, t, .005, v, .08, 1.1);
    o.connect(g); g.connect(bus); send(g, .3); o.start(t); o.stop(t + 1.4);
  }
  function tom(c, t, v, f0) {   // a war drum
    var o = c.createOscillator(), g = c.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(f0 * 1.5, t); o.frequency.exponentialRampToValueAtTime(f0, t + .09); env(g, t, .004, v, .03, .5);
    o.connect(g); g.connect(bus); send(g, .5); o.start(t); o.stop(t + .7);
  }
  function snare(c, t, v) {   // a fat backbeat: noise, a body, and a stacked clap
    var f = c.createBiquadFilter(), g = c.createGain(), o = c.createOscillator(), og = c.createGain(), i;
    f.type = 'bandpass'; f.frequency.value = 2000; f.Q.value = .5; env(g, t, .001, v, .01, .17); f.connect(g); g.connect(bus); send(g, .55);
    for (i = 0; i < 3; i++) { var n = c.createBufferSource(); n.buffer = noise; n.connect(f); n.start(t + i * .011, Math.random() * .5); n.stop(t + i * .011 + .2); }
    o.type = 'triangle'; o.frequency.setValueAtTime(230, t); o.frequency.exponentialRampToValueAtTime(150, t + .08); env(og, t, .001, v * .55, .01, .1); o.connect(og); og.connect(bus); o.start(t); o.stop(t + .2);
  }
  function rim(c, t, v) {   // the marching cadence's ghost notes
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    n.buffer = noise; f.type = 'bandpass'; f.frequency.value = 3600; f.Q.value = .7; env(g, t, .001, v, .004, .06); n.connect(f); f.connect(g); g.connect(bus); n.start(t, Math.random() * .5); n.stop(t + .12);
  }
  function crash(c, t, v) {
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    n.buffer = noise; n.loop = true; f.type = 'highpass'; f.frequency.value = 3800; env(g, t, .003, v, .06, 1.9);
    n.connect(f); f.connect(g); g.connect(bus); send(g, .55); n.start(t); n.stop(t + 2.3);
  }
  function riser(c, t, dur, v, midi) {   // tension: noise and a saw sweeping up into the next phrase
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain(), o = c.createOscillator(), og = c.createGain(), of = c.createBiquadFilter();
    n.buffer = noise; n.loop = true; f.type = 'bandpass'; f.Q.value = 1.2; f.frequency.setValueAtTime(500, t); f.frequency.exponentialRampToValueAtTime(7000, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(v, t + dur); g.gain.linearRampToValueAtTime(0.0001, t + dur + .03);
    n.connect(f); f.connect(g); g.connect(bus); n.start(t); n.stop(t + dur + .1);
    o.type = 'sawtooth'; o.frequency.setValueAtTime(hz(midi), t); o.frequency.exponentialRampToValueAtTime(hz(midi + 12), t + dur); of.type = 'lowpass'; of.frequency.setValueAtTime(400, t); of.frequency.exponentialRampToValueAtTime(5000, t + dur);
    og.gain.setValueAtTime(0.0001, t); og.gain.exponentialRampToValueAtTime(v * .5, t + dur); og.gain.linearRampToValueAtTime(0.0001, t + dur + .03);
    o.connect(of); of.connect(og); og.connect(bus); o.start(t); o.stop(t + dur + .1);
  }
  function riff(c, t, midi, dur, v) {   // the gritty low-brass guitar riff: palm-muted saws into the distortion bus
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), i;
    f.type = 'lowpass'; f.frequency.setValueAtTime(fr * 7, t); f.frequency.exponentialRampToValueAtTime(fr * 2.5, t + dur);
    env(g, t, .004, v, Math.max(0, dur * .5), Math.max(.03, dur * .5));
    for (i = 0; i < 2; i++) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = fr; o.detune.value = i ? 6 : -6; o.connect(f); o.start(t); o.stop(t + dur + .15); }
    f.connect(g); g.connect(gritIn);
  }
  function horn(c, t, midi, dur, v) {   // a brass section: three detuned saws, a filter that opens on the attack, a slow vibrato
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), i, lfo = c.createOscillator(), lg = c.createGain();
    f.type = 'lowpass'; f.Q.value = 1; f.frequency.setValueAtTime(fr * 1.6, t); f.frequency.exponentialRampToValueAtTime(Math.min(fr * 6, 7000), t + .07); f.frequency.exponentialRampToValueAtTime(fr * 2.6, t + .3);
    env(g, t, .02, v, Math.max(0, dur - .12), .12);
    lfo.frequency.value = 5; lg.gain.value = 8; lfo.connect(lg); lfo.start(t); lfo.stop(t + dur + .3);
    for (i = 0; i < 3; i++) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = fr; o.detune.value = (i - 1) * 9; lg.connect(o.detune); o.connect(f); o.start(t); o.stop(t + dur + .3); }
    f.connect(g); g.connect(bus); send(g, .32);
  }
  function trumpet(c, t, midi, dur, v) {   // the fanfare lead: edgy and loud, not sweet
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), a = c.createOscillator(), b = c.createOscillator();
    f.type = 'lowpass'; f.Q.value = 2; f.frequency.setValueAtTime(fr * 2, t); f.frequency.exponentialRampToValueAtTime(Math.min(fr * 6, 8000), t + .04); f.frequency.exponentialRampToValueAtTime(fr * 3.2, t + .25);
    env(g, t, .01, v, Math.max(0, dur - .1), .12);
    a.type = 'sawtooth'; b.type = 'square'; a.frequency.value = fr; b.frequency.value = fr * 1.004; a.connect(f); b.connect(f); a.start(t); b.start(t); a.stop(t + dur + .2); b.stop(t + dur + .2);
    f.connect(g); g.connect(bus); send(g, .38);
  }
  function cello(c, t, midi, dur, v) {   // low strings, short and driving
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), i;
    f.type = 'lowpass'; f.frequency.value = 1300; env(g, t, .006, v, Math.max(0, dur - .02), .05);
    for (i = 0; i < 2; i++) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = fr; o.detune.value = i ? 8 : -8; o.connect(f); o.start(t); o.stop(t + dur + .1); }
    f.connect(g); g.connect(bus);
  }
  function choir(c, t, midis, dur, v) {   // an "ahh" choir holding the chord: saws through two vowel-shaped filters
    var g = c.createGain(), f1 = c.createBiquadFilter(), f2 = c.createBiquadFilter();
    f1.type = 'bandpass'; f1.frequency.value = 760; f1.Q.value = 5; f2.type = 'bandpass'; f2.frequency.value = 1250; f2.Q.value = 6;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(v, t + dur * .3); g.gain.setValueAtTime(v, t + dur * .75); g.gain.exponentialRampToValueAtTime(0.0001, t + dur + .5);
    midis.forEach(function (m) { [-12, 0, 12].forEach(function (d) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = hz(m); o.detune.value = d; o.connect(f1); o.connect(f2); o.start(t); o.stop(t + dur + .6); }); });
    f1.connect(g); f2.connect(g); g.connect(bus); send(g, .6);
  }

  // ------------------------------------------------------------------ the score
  function chord(bar) {
    var deg = plan.prog[bar % plan.prog.length];
    return { deg: deg, root: note(deg, 2), third: note(deg + 2, 2), fifth: note(deg + 4, 2), root3: note(deg, 3), third3: note(deg + 2, 3), fifth3: note(deg + 4, 3) };
  }
  function playStep(c, s, t, lv) {
    var p = plan, st = p.style, bar = Math.floor(s / 16), k = s % 16, ch = chord(bar), phrase = bar % 4, last = phrase === 3, d16 = p.sec16;
    // the bed: the choir holds the chord; a deep drum on each bar
    if (k === 0) { choir(c, t, [ch.root3 + 12, ch.third3 + 12, ch.fifth3 + 12], d16 * 16, lv === 0 ? .045 : .07); tom(c, t, .4, 62 + (ch.root % 12) * .6); }
    if (lv >= 1) {
      if (st.kick[k] === 'x') kick(c, t, .7);
      if (st.snare[k] === 'x') { if (k % 8 === 4) snare(c, t, .62); else rim(c, t, .18); }
      if (st.ost[k] === 'x') cello(c, t, ch.root3 + 12 + (k % 8 === 6 ? 7 : 0), d16 * .75, k % 4 === 0 ? .12 : .07);
      if (st.riff[k] === 'x') riff(c, t, (k === 6 || k === 14 ? ch.fifth : k === 10 ? ch.root + 12 : ch.root) + 12, d16 * 1.2, .3);
      if (last && k >= 8) rim(c, t, .1 + (k - 8) * .04);   // the cadence rolls into the next phrase
      if (last && k >= 12) snare(c, t, .15 + (k - 12) * .1);
      if (last && k === 12) tom(c, t, .5, 90);
      if (last && k === 14) tom(c, t, .5, 75);
    }
    if (lv >= 2) {
      if (st.stab[k] === 'x') [ch.root3, ch.fifth3, ch.root3 + 12].forEach(function (m) { horn(c, t, m, d16 * 1.7, .15); });
      if (k === 0 && phrase === 0) { crash(c, t, .26); boom(c, t, .4); }
      if (last && k === 0) riser(c, t, d16 * 16, .16, ch.root + 12);
      p.hook.forEach(function (h, i) {   // the fanfare: trumpets over horns in octaves; it calls on the first bar of a phrase and answers on the third
        if (h[0] !== k) return;
        if (phrase % 2 === 0) { var m = note(p.hookDeg[i], 4); trumpet(c, t, m, d16 * h[1] * .93, .22); horn(c, t, m - 12, d16 * h[1] * .93, .13); horn(c, t, m, d16 * h[1] * .93, .13); }
        else if (i < 3) { var a = note(p.hookDeg[i] - 2, 4); trumpet(c, t, a, d16 * h[1] * .93, .18); horn(c, t, a - 12, d16 * h[1] * .93, .1); }
      });
    }
  }
  function hitNow(c, t, kind) {   // a card change: a sub drop, a crash, the horns on one low chord, drums
    var ch = chord(Math.floor(step / 16)), big = kind === 'big';
    boom(c, t, big ? .6 : .4); crash(c, t, big ? .3 : .18);
    [ch.root3, ch.fifth3, ch.root3 + 12, ch.third3 + 12].forEach(function (m) { horn(c, t, m, big ? .7 : .4, big ? .16 : .1); });
    riff(c, t, ch.root + 12, big ? .5 : .3, big ? .3 : .18);
    tom(c, t, .4, 78); tom(c, t + .1, .35, 100); if (big) { tom(c, t + .2, .4, 66); snare(c, t + .06, .5); }
  }

  // ------------------------------------------------------------------ playing it live
  function chain(c) {
    var comp = c.createDynamicsCompressor(); comp.threshold.value = -18; comp.ratio.value = 6; comp.attack.value = .003; comp.release.value = .16;
    master = c.createGain(); master.gain.value = .0001; duckG = c.createGain(); bus = c.createGain(); verb = mkVerb(c);
    var vg = c.createGain(); vg.gain.value = .3; verb.connect(vg);
    bus.connect(comp); vg.connect(comp); comp.connect(duckG); duckG.connect(master); master.connect(c.destination);
    gritIn = mkGrit(c); noise = mkNoise(c);
  }
  function ensure() {
    if (ctx) return ctx;
    var AC = global.AudioContext || global.webkitAudioContext; if (!AC) return null;
    ctx = new AC(); chain(ctx);
    return ctx;
  }
  function applyVol(fast) {
    if (!ctx) return;
    var tgt = (armed && !silent) ? 0.15 : 0.0001, g = duckG.gain;
    g.cancelScheduledValues(ctx.currentTime); g.setTargetAtTime(ducked ? 0.0001 : 1, ctx.currentTime, fast ? .05 : .25);
    master.gain.cancelScheduledValues(ctx.currentTime); master.gain.setTargetAtTime(tgt, ctx.currentTime, fast ? .05 : .4);
  }
  function tick() {
    if (!ctx || ctx.state !== 'running') return;
    while (nextT < ctx.currentTime + .18) {
      if (nextT >= ctx.currentTime - .05) playStep(ctx, step, nextT, level);
      nextT += plan.sec16; step++;
    }
  }
  function start() {
    if (!plan || !ensure()) return;
    armed = true; silent = false;
    if (ctx.state === 'suspended') ctx.resume();
    if (!timer) { step = 0; nextT = ctx.currentTime + .08; timer = setInterval(tick, 30); }
    applyVol();
  }
  function stop() {
    armed = false; applyVol(true);
    if (timer) { clearInterval(timer); timer = null; }
  }
  function card(type, i, n) {
    level = LEVELS[type] != null ? LEVELS[type] : 1;
    if (type === 'play') { ducked = true; applyVol(true); return; }
    var wasDucked = ducked; ducked = false; applyVol(true);
    if (ctx && armed && !silent && plan) hitNow(ctx, ctx.currentTime + .02, (i === 0 || wasDucked || i === n - 1) ? 'big' : 'small');
  }
  function mute(on) { silent = !!on; applyVol(true); }
  function duck(on) { ducked = !!on; applyVol(true); }
  function finish() {
    if (ctx && armed && !silent) hitNow(ctx, ctx.currentTime + .02, 'big');
    level = 0; setTimeout(stop, 3000);
  }
  if (global.document) document.addEventListener('visibilitychange', function () { if (!ctx) return; if (document.hidden) ctx.suspend(); else if (armed) ctx.resume(); });

  // ------------------------------------------------------------------ the same music into an offline buffer
  function render(oc, seconds, cards) {   // cards: [{ t: seconds, type }]: the tune plays at the level of the card on screen, with a hit at each change
    ctx = oc; armed = true; silent = false; ducked = false; chain(oc); master.gain.value = .15;
    var s, lv, ci = -1, total = Math.floor(seconds / plan.sec16);
    (cards || []).forEach(function (cd) { if (cd.type !== 'play') { step = Math.floor(cd.t / plan.sec16); hitNow(oc, cd.t, cd.t === 0 ? 'big' : 'small'); } });
    for (s = 0; s < total; s++) {
      var t = s * plan.sec16; lv = 2;
      (cards || []).forEach(function (cd, i) { if (cd.t <= t) { ci = i; } });
      if (ci >= 0) { var ty = cards[ci].type; lv = ty === 'play' ? -1 : (LEVELS[ty] != null ? LEVELS[ty] : 1); }
      if (lv >= 0) playStep(oc, s, t, lv);
    }
    return plan;
  }

  global.Theme = { setup: setup, start: start, stop: stop, card: card, mute: mute, duck: duck, finish: finish, render: render, plan: function () { return plan; }, armed: function () { return armed; } };
})(window);
