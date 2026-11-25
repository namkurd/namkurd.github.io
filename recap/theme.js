/* The recap's theme song, made with Web Audio when the page opens: no audio files. A fast, royal, orchestral gridiron fanfare in the spirit of the great
   football-broadcast themes (NFL Films' brass and timpani, NBC and Fox pageantry, CBS and TNT drive): trumpets and horns on a triadic fanfare, a string
   ostinato running in sixteenths, marching snare cadences, timpani, bells on the hook, a cymbal swell into every phrase.
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

  var MODES = { major: [0, 2, 4, 5, 7, 9, 11], mixo: [0, 2, 4, 5, 7, 9, 10], lydian: [0, 2, 4, 6, 7, 9, 11], harm: [0, 2, 3, 5, 7, 8, 11] };
  var PROGS = {   // chord roots as scale degrees, one chord a bar
    major: [[0, 4, 5, 3], [0, 3, 4, 0], [0, 5, 3, 4], [0, 2, 3, 4]],
    mixo: [[0, 6, 3, 0], [0, 3, 6, 4], [0, 6, 4, 0]],
    lydian: [[0, 1, 4, 0], [0, 4, 3, 0], [0, 5, 1, 4]],
    harm: [[0, 5, 4, 0], [0, 3, 4, 0], [0, 5, 2, 4], [0, 6, 5, 4]]
  };
  var HOOKS = [   // the fanfare: [start step in the bar, length in steps]; dotted, trumpet-call rhythms
    [[0, 3], [3, 1], [4, 4], [8, 3], [11, 1], [12, 4]],
    [[0, 2], [2, 2], [4, 2], [6, 2], [8, 8]],
    [[0, 3], [3, 1], [4, 2], [6, 2], [8, 2], [10, 2], [12, 4]],
    [[0, 1], [1, 1], [2, 2], [4, 4], [8, 2], [10, 2], [12, 4]]
  ];
  var STYLES = [   // fast, brassy and bright; patterns are 16 sixteenth-note steps
    { name: 'pageant', bpm: [140, 152], modes: ['major', 'lydian'], snare: 'x.x.x.xxx.x.x.xx', accent: '....X.......X...', timp: 'x.......x.x.....', bass: 'x.x.x.x.x.x.x.x.', stab: 'x..x..x.x.......', ost: [0, 2, 1, 2] },
    { name: 'anthem', bpm: [134, 146], modes: ['mixo', 'major'], snare: 'x.xxx.x.x.xxx.xx', accent: '....X.......X...', timp: 'x.....x.x.......', bass: 'x..x..x.x..x..x.', stab: 'x.....x.x.x.....', ost: [0, 1, 2, 1] },
    { name: 'conquest', bpm: [138, 150], modes: ['harm', 'major'], snare: 'x.x.x.x.xxx.x.xx', accent: '....X.......X...', timp: 'x.x.....x.x.....', bass: 'x.xxx.xxx.xxx.xx', stab: 'x..x..x...x.x...', ost: [0, 2, 1, 2] },
    { name: 'gala', bpm: [132, 144], modes: ['lydian', 'mixo'], snare: 'x.x.x.x.x.x.xxxx', accent: '....X.......X...', timp: 'x.......x.......', bass: 'x.x.x.x.x.x.x.x.', stab: 'x.x...x.x.......', ost: [0, 2, 1, 2] }
  ];
  // how loud the arrangement is on each kind of card: 0 bed, 1 groove, 2 full
  var LEVELS = { intro: 2, game: 2, finals: 1, race: 1, clinch: 2, trades: 1, slack: 1, pod: 0, shotguns: 1, records: 2, lifetime: 1, coming: 2, wait: 0 };

  var plan = null, ctx = null, master = null, duckG = null, bus = null, verb = null, noise = null, timer = null;
  var armed = false, silent = false, ducked = false, level = 2, nextT = 0, step = 0;

  function setup(o) {
    var r = rng((o.seed * 2654435761) >>> 0), st = STYLES[Math.floor(r() * STYLES.length)];
    var mode = st.modes[Math.floor(r() * st.modes.length)], seconds = Math.max(30, o.seconds || 150);
    var target = st.bpm[0] + r() * (st.bpm[1] - st.bpm[0]);
    var bars = Math.max(8, Math.round(seconds * target / 240)), bpm = bars * 240 / seconds;   // a whole number of bars fills the recap exactly
    plan = {
      style: st, mode: mode, scale: MODES[mode], bpm: bpm, bars: bars, sec16: 60 / bpm / 4, tonic: [0, 2, 3, 5, 7, 9, 10][Math.floor(r() * 7)],
      prog: PROGS[mode][Math.floor(r() * PROGS[mode].length)], hook: HOOKS[Math.floor(r() * HOOKS.length)], hookDeg: [], seed: o.seed
    };
    var pool = [0, 2, 4, 7, 4, 7, 9, 4, 2, 7, 11, 9], k;   // fanfare tones: the key's triad and its octave, with a few passing notes
    for (k = 0; k < plan.hook.length; k++) plan.hookDeg.push(pool[Math.floor(r() * pool.length)]);
    plan.hookDeg[0] = r() < .5 ? 0 : 4; plan.hookDeg[plan.hookDeg.length - 1] = [0, 4, 7][Math.floor(r() * 3)];
    return plan;
  }

  function note(deg, oct) {   // scale degree (any size) -> midi
    var n = plan.scale.length, o = Math.floor(deg / n), d = ((deg % n) + n) % n;
    return plan.tonic + 12 * (oct + o) + plan.scale[d];
  }

  // ------------------------------------------------------------------ the orchestra
  function mkNoise(c) {
    var b = c.createBuffer(1, c.sampleRate, c.sampleRate), d = b.getChannelData(0), i, s = 22222;
    for (i = 0; i < d.length; i++) { s = (s * 1664525 + 1013904223) >>> 0; d[i] = (s / 2147483648) - 1; }
    return b;
  }
  function mkVerb(c) {   // a big hall
    var len = Math.floor(c.sampleRate * 2.2), b = c.createBuffer(2, len, c.sampleRate), ch, i, s = 777;
    for (ch = 0; ch < 2; ch++) { var d = b.getChannelData(ch); for (i = 0; i < len; i++) { s = (s * 1664525 + 1013904223) >>> 0; d[i] = ((s / 2147483648) - 1) * Math.pow(1 - i / len, 2.4); } }
    var cv = c.createConvolver(); cv.buffer = b; return cv;
  }
  function env(g, t, a, peak, hold, rel) {
    peak = Math.max(peak, 0.0002);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(peak, t + a);
    g.gain.setValueAtTime(peak, t + a + hold); g.gain.exponentialRampToValueAtTime(0.0001, t + a + hold + rel);
  }
  function send(g, amt) { var s = ctx.createGain(); s.gain.value = amt; g.connect(s); s.connect(verb); }
  function timp(c, t, v, midi) {   // timpani: a pitched thump with a skin knock
    var o = c.createOscillator(), g = c.createGain(), n = c.createBufferSource(), f = c.createBiquadFilter(), ng = c.createGain(), fr = hz(midi);
    o.type = 'sine'; o.frequency.setValueAtTime(fr * 1.35, t); o.frequency.exponentialRampToValueAtTime(fr, t + .07); env(g, t, .004, v, .02, .55);
    o.connect(g); g.connect(bus); send(g, .35); o.start(t); o.stop(t + .7);
    n.buffer = noise; f.type = 'bandpass'; f.frequency.value = 220; f.Q.value = .8; env(ng, t, .002, v * .5, .005, .09); n.connect(f); f.connect(ng); ng.connect(bus); n.start(t, Math.random() * .5); n.stop(t + .15);
  }
  function snare(c, t, v) {   // a tight marching snare: bright, short, snappy
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain(), o = c.createOscillator(), og = c.createGain();
    n.buffer = noise; f.type = 'bandpass'; f.frequency.value = 3300; f.Q.value = .6; env(g, t, .001, v, .004, .085);
    n.connect(f); f.connect(g); g.connect(bus); send(g, .25); n.start(t, Math.random() * .5); n.stop(t + .18);
    o.type = 'triangle'; o.frequency.value = 235; env(og, t, .001, v * .35, .004, .05); o.connect(og); og.connect(bus); o.start(t); o.stop(t + .12);
  }
  function crash(c, t, v) {
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    n.buffer = noise; n.loop = true; f.type = 'highpass'; f.frequency.value = 4200; env(g, t, .003, v, .05, 1.6);
    n.connect(f); f.connect(g); g.connect(bus); send(g, .5); n.start(t); n.stop(t + 2);
  }
  function swell(c, t, dur, v) {   // a cymbal swelling into the next phrase
    var n = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    n.buffer = noise; n.loop = true; f.type = 'highpass'; f.frequency.setValueAtTime(2500, t); f.frequency.linearRampToValueAtTime(7000, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(v, t + dur); g.gain.linearRampToValueAtTime(0.0001, t + dur + .04);
    n.connect(f); f.connect(g); g.connect(bus); n.start(t); n.stop(t + dur + .1);
  }
  function horn(c, t, midi, dur, v, bright) {   // brass: detuned saws through a filter that opens on the attack, with a touch of vibrato
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), i, lfo = c.createOscillator(), lg = c.createGain();
    f.type = 'lowpass'; f.Q.value = 1.1; f.frequency.setValueAtTime(fr * 1.8, t); f.frequency.exponentialRampToValueAtTime(Math.min(fr * (bright ? 9 : 5), 11000), t + .05); f.frequency.exponentialRampToValueAtTime(fr * 3.2, t + .25);
    env(g, t, .012, v, Math.max(0, dur - .1), .1);
    lfo.frequency.value = 5.4; lg.gain.value = 7; lfo.connect(lg); lfo.start(t); lfo.stop(t + dur + .2);
    for (i = 0; i < 3; i++) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = fr; o.detune.value = (i - 1) * 8; lg.connect(o.detune); o.connect(f); o.start(t); o.stop(t + dur + .2); }
    f.connect(g); g.connect(bus); send(g, .3);
  }
  function trumpet(c, t, midi, dur, v) {   // brighter and edgier than a horn: saw and square, a hard attack
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), a = c.createOscillator(), b = c.createOscillator();
    f.type = 'lowpass'; f.Q.value = 2.2; f.frequency.setValueAtTime(fr * 2.5, t); f.frequency.exponentialRampToValueAtTime(Math.min(fr * 8, 12000), t + .035); f.frequency.exponentialRampToValueAtTime(fr * 4, t + .2);
    env(g, t, .008, v, Math.max(0, dur - .08), .09);
    a.type = 'sawtooth'; b.type = 'square'; a.frequency.value = fr; b.frequency.value = fr * 1.003; a.connect(f); b.connect(f); a.start(t); b.start(t); a.stop(t + dur + .15); b.stop(t + dur + .15);
    f.connect(g); g.connect(bus); send(g, .35);
  }
  function strings(c, t, midi, dur, v) {   // a short, bowed-staccato string note: the ostinato
    var g = c.createGain(), f = c.createBiquadFilter(), fr = hz(midi), i;
    f.type = 'lowpass'; f.frequency.value = 3000; env(g, t, .006, v, Math.max(0, dur - .02), .05);
    for (i = 0; i < 2; i++) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = fr; o.detune.value = i ? 9 : -9; o.connect(f); o.start(t); o.stop(t + dur + .1); }
    f.connect(g); g.connect(bus); send(g, .18);
  }
  function lowBrass(c, t, midi, dur, v) {
    var o = c.createOscillator(), f = c.createBiquadFilter(), g = c.createGain();
    o.type = 'sawtooth'; o.frequency.value = hz(midi); f.type = 'lowpass'; f.frequency.value = 620; env(g, t, .008, v, Math.max(0, dur - .04), .06);
    o.connect(f); f.connect(g); g.connect(bus); o.start(t); o.stop(t + dur + .1);
  }
  function stringPad(c, t, midis, dur, v) {
    var f = c.createBiquadFilter(), g = c.createGain();
    f.type = 'lowpass'; f.frequency.value = 1700; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(v, t + dur * .25); g.gain.setValueAtTime(v, t + dur * .75); g.gain.exponentialRampToValueAtTime(0.0001, t + dur + .4);
    midis.forEach(function (m) { [-10, 10].forEach(function (d) { var o = c.createOscillator(); o.type = 'sawtooth'; o.frequency.value = hz(m); o.detune.value = d; o.connect(f); o.start(t); o.stop(t + dur + .5); }); });
    f.connect(g); g.connect(bus); send(g, .45);
  }
  function bell(c, t, midi, v) {   // glockenspiel sparkle on the fanfare
    var g = c.createGain(), a = c.createOscillator(), b = c.createOscillator();
    a.type = 'sine'; b.type = 'triangle'; a.frequency.value = hz(midi); b.frequency.value = hz(midi + 12); env(g, t, .002, v, .01, .7);
    a.connect(g); b.connect(g); g.connect(bus); send(g, .4); a.start(t); b.start(t); a.stop(t + .9); b.stop(t + .9);
  }

  // ------------------------------------------------------------------ the score
  function chord(bar) {
    var deg = plan.prog[bar % plan.prog.length];
    return { deg: deg, root: note(deg, 3), third: note(deg + 2, 3), fifth: note(deg + 4, 3) };
  }
  function tim(m) { while (m > 52) m -= 12; while (m < 38) m += 12; return m; }
  function playStep(c, s, t, lv) {
    var p = plan, st = p.style, bar = Math.floor(s / 16), k = s % 16, ch = chord(bar), phrase = bar % 4, last = phrase === 3, d16 = p.sec16;
    var tones = [ch.root + 12, ch.third + 12, ch.fifth + 12, ch.root + 24, ch.third + 24];
    // the bed: strings holding the chord, a timpani beat on each bar
    if (k === 0) { stringPad(c, t, [ch.root + 12, ch.third + 12, ch.fifth + 12, ch.root + 24], d16 * 16, lv === 0 ? .03 : .04); timp(c, t, .55, tim(ch.root)); }
    if (lv >= 1) {
      if (k === 8) timp(c, t, .42, tim(ch.fifth));
      if (st.timp[k] === 'x' && k !== 0 && k !== 8) timp(c, t, .3, tim(ch.root));
      if (st.bass[k] === 'x') lowBrass(c, t, (k % 8 === 0 || k % 4 === 0 ? ch.root : ch.fifth) - 12, d16 * 1.6, .13);
      strings(c, t, tones[st.ost[k % 4]], d16 * .8, k % 4 === 0 ? .075 : .05);   // the sixteenth-note drive
      if (st.snare[k] === 'x') snare(c, t, st.accent[k] === 'X' ? .5 : .3);
      if (last && k >= 12) snare(c, t, .14 + (k - 12) * .1);   // the roll into the next phrase
    }
    if (lv >= 2) {
      if (st.stab[k] === 'x') [ch.root + 12, ch.fifth + 12, ch.root + 24, ch.third + 24].forEach(function (m, i) { horn(c, t, m, d16 * 1.5, i === 3 ? .05 : .08, true); });
      if (k === 0 && phrase === 0) crash(c, t, .22);
      if (last && k === 8) swell(c, t, d16 * 8, .16);   // the cymbal swell into the next phrase
      p.hook.forEach(function (h, i) {   // the fanfare, trumpets over horns with bells on top; it calls on the first bar and answers on the second
        if (h[0] !== k) return;
        if (phrase % 2 === 0) { trumpet(c, t, note(p.hookDeg[i], 5), d16 * h[1] * .92, .1); horn(c, t, note(p.hookDeg[i], 4), d16 * h[1] * .92, .075, true); bell(c, t, note(p.hookDeg[i], 6), .05); }
        else if (i < 4) { trumpet(c, t, note(p.hookDeg[i] + 2, 5), d16 * h[1] * .92, .085); horn(c, t, note(p.hookDeg[i] + 2, 4), d16 * h[1] * .92, .06, true); }
      });
    }
  }
  function hitNow(c, t, kind) {   // a card change: the whole orchestra on one chord, a cymbal, a timpani roll
    var ch = chord(Math.floor(step / 16)), big = kind === 'big';
    crash(c, t, big ? .26 : .15);
    [ch.root, ch.fifth, ch.root + 12, ch.third + 12].forEach(function (m) { horn(c, t, m, big ? .5 : .32, big ? .1 : .065, true); });
    trumpet(c, t, ch.root + 24, big ? .45 : .28, big ? .08 : .05);
    timp(c, t, .5, tim(ch.root)); timp(c, t + .07, .4, tim(ch.fifth)); timp(c, t + .14, .5, tim(ch.root));
    if (big) { snare(c, t + .04, .3); snare(c, t + .1, .35); bell(c, t, ch.root + 24, .07); }
  }

  // ------------------------------------------------------------------ playing it live
  function ensure() {
    if (ctx) return ctx;
    var AC = global.AudioContext || global.webkitAudioContext; if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain(); master.gain.value = 0.0001;
    var comp = ctx.createDynamicsCompressor(); comp.threshold.value = -16; comp.ratio.value = 5; comp.attack.value = .004; comp.release.value = .14;
    duckG = ctx.createGain(); bus = ctx.createGain(); verb = mkVerb(ctx); var vg = ctx.createGain(); vg.gain.value = .26; verb.connect(vg);
    bus.connect(comp); vg.connect(comp); comp.connect(duckG); duckG.connect(master); master.connect(ctx.destination);
    noise = mkNoise(ctx);
    return ctx;
  }
  function applyVol(fast) {
    if (!ctx) return;
    var tgt = (armed && !silent) ? 0.3 : 0.0001, g = duckG.gain;
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
    level = 0; setTimeout(stop, 2800);
  }
  if (global.document) document.addEventListener('visibilitychange', function () { if (!ctx) return; if (document.hidden) ctx.suspend(); else if (armed) ctx.resume(); });

  // ------------------------------------------------------------------ the same music into an offline buffer
  function render(oc, seconds, cards) {   // cards: [{ t: seconds, type }]: the tune plays at the level of the card on screen, with a hit at each change
    ctx = oc; armed = true; silent = false; ducked = false;
    master = oc.createGain(); master.gain.value = .3;
    var comp = oc.createDynamicsCompressor(); comp.threshold.value = -16; comp.ratio.value = 5; comp.attack.value = .004; comp.release.value = .14;
    duckG = oc.createGain(); bus = oc.createGain(); verb = mkVerb(oc); var vg = oc.createGain(); vg.gain.value = .26; verb.connect(vg);
    bus.connect(comp); vg.connect(comp); comp.connect(duckG); duckG.connect(master); master.connect(oc.destination); noise = mkNoise(oc);
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
