/* The recap's theme song, made with Web Audio when the page opens: no audio files. Every week gets a different tune (key, mode, tempo, chords, hook) from the
   week's number, and its tempo is set so the whole arrangement is as long as the recap. The styles lean on the great sports-broadcast themes: the big
   orchestral minor of NFL Films, the bright syncopated brass of NBA on NBC, the hard four-on-the-floor of Fox football, the horn stabs of TNT.

   Theme.setup({ seed, seconds })     plan the tune
   Theme.start()                      (from a tap) start the title-card loop
   Theme.card(type, i, n)             a card change: set the energy and hit the beat
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

  var MODES = { minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10], mixo: [0, 2, 4, 5, 7, 9, 10], major: [0, 2, 4, 5, 7, 9, 11] };
  var PROGS = {   // chord roots as scale degrees, one chord a bar
    minor: [[0, 5, 6, 0], [0, 6, 5, 4], [0, 3, 6, 2], [0, 2, 6, 3], [0, 5, 2, 6]],
    dorian: [[0, 3, 6, 0], [0, 6, 3, 4], [0, 2, 3, 6]],
    mixo: [[0, 6, 3, 0], [0, 3, 6, 4], [0, 4, 6, 3]],
    major: [[0, 3, 4, 0], [0, 4, 5, 3], [0, 5, 3, 4]]
  };
  var HOOKS = [   // [start step in the bar, length in steps]
    [[0, 3], [3, 1], [4, 2], [6, 2], [8, 6], [14, 2]],
    [[0, 2], [2, 2], [4, 4], [8, 2], [10, 2], [12, 4]],
    [[0, 1], [1, 1], [2, 2], [4, 2], [6, 2], [8, 8]],
    [[0, 4], [4, 2], [6, 2], [8, 3], [11, 1], [12, 4]]
  ];
  var STYLES = [
    { name: 'films', bpm: [92, 110], modes: ['minor'], kick: ['x.......x.x.....', 'x.......x...x...'], snare: '....x.......x...', hat: 'x.x.x.x.x.x.x.x.', bass: 'x.......x.......', stab: 'x.....x.........', tim: 1, pad: .9 },
    { name: 'nbc', bpm: [116, 130], modes: ['mixo', 'major'], kick: ['x..x..x...x.x...', 'x..x....x.x..x..'], snare: '....x.......x...', hat: 'xxxxxxxxxxxxxxxx', bass: 'x..x..x.x..x..x.', stab: 'x..x..x...x.x...', tim: 0, pad: .5 },
    { name: 'fox', bpm: [124, 138], modes: ['minor', 'dorian'], kick: ['x...x...x...x...', 'x...x...x..xx...'], snare: '....x.......x...', hat: 'x.x.x.x.x.x.x.x.', bass: 'x.x.x.x.x.x.x.x.', stab: 'x..x..x.x.......', tim: 0, pad: .6 },
    { name: 'tnt', bpm: [108, 122], modes: ['dorian', 'minor'], kick: ['x.....x...x.....', 'x.....x..x.x....'], snare: '....x.......x..x', hat: 'x.xxx.xxx.xxx.xx', bass: 'x..x....x..x....', stab: 'x.......x.x.....', tim: 0, pad: .5 }
  ];
  // how loud the arrangement is on each kind of card: 0 bed, 1 groove, 2 full
  var LEVELS = { intro: 2, game: 2, finals: 1, race: 1, clinch: 2, trades: 1, slack: 1, pod: 0, shotguns: 1, records: 2, lifetime: 1, coming: 2, wait: 0 };

  var plan = null, ctx = null, master = null, duckG = null, bus = null, verb = null, noise = null, timer = null;
  var armed = false, silent = false, ducked = false, level = 2, nextT = 0, step = 0, startedAt = 0;

  function setup(o) {
    var r = rng((o.seed * 2654435761) >>> 0), st = STYLES[Math.floor(r() * STYLES.length)];
    var mode = st.modes[Math.floor(r() * st.modes.length)], seconds = Math.max(30, o.seconds || 150);
    var target = st.bpm[0] + r() * (st.bpm[1] - st.bpm[0]);
    var bars = Math.max(8, Math.round(seconds * target / 240)), bpm = bars * 240 / seconds;   // a whole number of bars fills the recap exactly
    plan = {
      style: st, mode: mode, scale: MODES[mode], bpm: bpm, bars: bars, sec16: 60 / bpm / 4, tonic: [0, 2, 3, 5, 7, 9, 10][Math.floor(r() * 7)],
      prog: PROGS[mode][Math.floor(r() * PROGS[mode].length)], kickPat: st.kick[Math.floor(r() * st.kick.length)], hook: HOOKS[Math.floor(r() * HOOKS.length)], hookDeg: [], seed: o.seed
    };
    var pool = [0, 2, 4, 7, 4, 2, 0, 4, 9, 7, 11, 2], k;   // fanfare tones: the key's triad and its octave, a few passing notes
    for (k = 0; k < plan.hook.length; k++) plan.hookDeg.push(pool[Math.floor(r() * pool.length)]);
    plan.hookDeg[0] = r() < .5 ? 0 : 4; plan.hookDeg[plan.hookDeg.length - 1] = [0, 4, 7][Math.floor(r() * 3)];
    return plan;
  }

  function note(deg, oct) {   // scale degree (any size, may exceed an octave) -> midi
    var n = plan.scale.length, o = Math.floor(deg / n), d = ((deg % n) + n) % n;
    return plan.tonic + 12 * (oct + o) + plan.scale[d];
  }

  // ------------------------------------------------------------------ voices
  function mkNoise(c) {
    var b = c.createBuffer(1, c.sampleRate, c.sampleRate), d = b.getChannelData(0), i, s = 22222;
    for (i = 0; i < d.length; i++) { s = (s * 1664525 + 1013904223) >>> 0; d[i] = (s / 2147483648) - 1; }
    return b;
  }
  function mkVerb(c) {
    var len = Math.floor(c.sampleRate * 1.7), b = c.createBuffer(2, len, c.sampleRate), ch, i, s = 777;
    for (ch = 0; ch < 2; ch++) { var d = b.getChannelData(ch); for (i = 0; i < len; i++) { s = (s * 1664525 + 1013904223) >>> 0; d[i] = ((s / 2147483648) - 1) * Math.pow(1 - i / len, 2.6); } }
    var cv = c.createConvolver(); cv.buffer = b; return cv;
  }
  function env(g, t, a, peak, hold, rel) {
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.0002), t + a);
    g.gain.setValueAtTime(Math.max(peak, 0.0002), t + a + hold); g.gain.exponentialRampToValueAtTime(0.0001, t + a + hold + rel);
  }
  function kick(c, t, v) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(135, t); o.frequency.exponentialRampToValueAtTime(42, t + .11);
    env(g, t, .004, v, .02, .24); o.connect(g); g.connect(bus); o.start(t); o.stop(t + .4);
  }
  function snare(c, t, v) {
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain(), o = c.createOscillator(), og = c.createGain();
    n.buffer = noise; f.type = 'bandpass'; f.frequency.value = 2100; f.Q.value = .7; env(g, t, .002, v, .01, .2);
    n.connect(f); f.connect(g); g.connect(bus); g.connect(verb); n.start(t, Math.random() * .5); n.stop(t + .3);
    o.type = 'triangle'; o.frequency.setValueAtTime(210, t); o.frequency.exponentialRampToValueAtTime(140, t + .1); env(og, t, .002, v * .5, .01, .11); o.connect(og); og.connect(bus); o.start(t); o.stop(t + .2);
  }
  function hat(c, t, v, open) {
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    n.buffer = noise; f.type = 'highpass'; f.frequency.value = 7200; env(g, t, .001, v, .004, open ? .16 : .04);
    n.connect(f); f.connect(g); g.connect(bus); n.start(t, Math.random() * .5); n.stop(t + .3);
  }
  function crash(c, t, v) {
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    n.buffer = noise; n.loop = true; f.type = 'highpass'; f.frequency.value = 3600; env(g, t, .004, v, .05, 1.5);
    n.connect(f); f.connect(g); g.connect(bus); g.connect(verb); n.start(t); n.stop(t + 1.8);
  }
  function tom(c, t, v, f0) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f0 * .55, t + .28); env(g, t, .004, v, .02, .34);
    o.connect(g); g.connect(bus); g.connect(verb); o.start(t); o.stop(t + .5);
  }
  function brass(c, t, midi, dur, v, bright) {   // two detuned saws through a filter that opens on the attack, like a section of horns
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), i;
    f.type = 'lowpass'; f.Q.value = 1.4; f.frequency.setValueAtTime(fr * 1.6, t); f.frequency.exponentialRampToValueAtTime(Math.min(fr * (bright ? 7 : 5), 9000), t + .06); f.frequency.exponentialRampToValueAtTime(fr * 2.6, t + .22);
    env(g, t, .018, v, Math.max(0, dur - .12), .1);
    for (i = 0; i < 2; i++) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = fr; o.detune.value = i ? 7 : -7; o.connect(f); o.start(t); o.stop(t + dur + .15); }
    f.connect(g); g.connect(bus); var s = c.createGain(); s.gain.value = .35; g.connect(s); s.connect(verb);
  }
  function bass(c, t, midi, dur, v) {
    var o = c.createOscillator(), f = c.createBiquadFilter(), g = c.createGain();
    o.type = 'sawtooth'; o.frequency.value = hz(midi); f.type = 'lowpass'; f.frequency.value = 420; env(g, t, .006, v, Math.max(0, dur - .05), .06);
    o.connect(f); f.connect(g); g.connect(bus); o.start(t); o.stop(t + dur + .1);
  }
  function pad(c, t, midis, dur, v) {
    var f = c.createBiquadFilter(), g = c.createGain();
    f.type = 'lowpass'; f.frequency.value = 900; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(v, t + dur * .35); g.gain.setValueAtTime(v, t + dur * .7); g.gain.exponentialRampToValueAtTime(0.0001, t + dur + .5);
    midis.forEach(function (m) { [-9, 9].forEach(function (d) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = hz(m); o.detune.value = d; o.connect(f); o.start(t); o.stop(t + dur + .6); }); });
    f.connect(g); g.connect(bus); var s = c.createGain(); s.gain.value = .5; g.connect(s); s.connect(verb);
  }

  // ------------------------------------------------------------------ the score
  function chord(bar) {
    var deg = plan.prog[bar % plan.prog.length];
    return { deg: deg, root: note(deg, 3), third: note(deg + 2, 3), fifth: note(deg + 4, 3) };
  }
  function playStep(c, s, t, lv) {
    var p = plan, st = p.style, bar = Math.floor(s / 16), k = s % 16, ch = chord(bar), phrase = bar % 4, lastBar = (bar % 4 === 3);
    var d16 = p.sec16;
    // the bed: a pad on each bar, and a bass note on the bass pattern
    if (k === 0) pad(c, t, [ch.root + 12, ch.third + 12, ch.fifth + 12], d16 * 16, .028 * st.pad);
    if (st.bass[k] === 'x') bass(c, t, ch.root - 12, d16 * 1.8, lv === 0 ? .1 : .16);
    if (lv >= 0 && st.hat[k] !== '.') hat(c, t, lv === 0 ? .03 : (k % 4 === 0 ? .08 : .05), k === 14 && lv === 2);
    if (lv >= 1) {
      if (p.kickPat[k] === 'x') kick(c, t, .62);
      if (st.snare[k] === 'x') snare(c, t, lastBar && k >= 12 ? .34 : .4);
      if (lastBar && k >= 12 && lv >= 1) snare(c, t, .12 + (k - 12) * .08);   // the roll into the next phrase
      if (st.tim && (k === 0 || k === 6) && phrase % 2 === 0) tom(c, t, .42, 120);
    }
    if (lv >= 2) {
      if (st.stab[k] === 'x') [ch.root + 12, ch.fifth + 12, ch.root + 24, ch.third + 12].forEach(function (m, i) { brass(c, t, m, d16 * 1.7, i === 3 ? .045 : .075, true); });
      if (k === 0 && phrase === 0) crash(c, t, .18);
      if (phrase % 2 === 0) {   // the hook, over the first and third bar of every phrase
        p.hook.forEach(function (h, i) { if (h[0] === k) brass(c, t, note(p.hookDeg[i] + (phrase === 2 ? 0 : 0), 4), d16 * h[1] * .95, .1, true); });
      }
    }
  }
  function hitNow(c, t, kind) {   // a card change: a crash, a low hit and a short fill, whatever the groove is doing
    var ch = chord(Math.floor(step / 16));
    crash(c, t, kind === 'big' ? .2 : .13);
    [ch.root, ch.fifth, ch.root + 12].forEach(function (m) { brass(c, t, m, .35, kind === 'big' ? .09 : .06, true); });
    tom(c, t, .4, 100); snare(c, t + .06, .16); tom(c, t + .12, .3, 150);
  }

  // ------------------------------------------------------------------ playing it live
  function ensure() {
    if (ctx) return ctx;
    var AC = global.AudioContext || global.webkitAudioContext; if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain(); master.gain.value = 0.0001;
    var comp = ctx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 4;
    duckG = ctx.createGain(); bus = ctx.createGain(); bus.gain.value = 1; verb = mkVerb(ctx); var vg = ctx.createGain(); vg.gain.value = .22; verb.connect(vg);
    bus.connect(comp); vg.connect(comp); comp.connect(duckG); duckG.connect(master); master.connect(ctx.destination);
    noise = mkNoise(ctx);
    return ctx;
  }
  function vol() { return (armed && !silent) ? 0.2 : 0.0001; }
  function applyVol(fast) {
    if (!ctx) return;
    var tgt = (armed && !silent) ? 0.32 : 0.0001, g = duckG.gain;
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
    if (!timer) { step = 0; nextT = ctx.currentTime + .08; startedAt = ctx.currentTime; timer = setInterval(tick, 30); }
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
    if (ctx && armed && !silent) { var t = ctx.currentTime + .02; hitNow(ctx, t, 'big'); }
    level = 0; setTimeout(stop, 2600);
  }
  if (global.document) document.addEventListener('visibilitychange', function () { if (!ctx) return; if (document.hidden) ctx.suspend(); else if (armed) ctx.resume(); });

  // ------------------------------------------------------------------ the same music into an offline buffer
  function render(oc, seconds, cards) {   // cards: [{ t: seconds, type }]: the tune plays at the level of the card on screen, with a hit at each change
    ctx = oc; armed = true; silent = false; ducked = false;
    master = oc.createGain(); master.gain.value = .32;
    var comp = oc.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 4;
    duckG = oc.createGain(); bus = oc.createGain(); verb = mkVerb(oc); var vg = oc.createGain(); vg.gain.value = .22; verb.connect(vg);
    bus.connect(comp); vg.connect(comp); comp.connect(duckG); duckG.connect(master); master.connect(oc.destination); noise = mkNoise(oc);
    var s, lv, ci = -1, total = Math.floor(seconds / plan.sec16);
    (cards || []).forEach(function (cd) { if (cd.type !== 'play') { step = Math.floor(cd.t / plan.sec16); hitNow(oc, cd.t, 'small'); } });
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
