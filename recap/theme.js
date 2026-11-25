/* The recap's theme song player. The music itself is composed each week by tools/build_theme.py and played by a sampled orchestra (strings, choir, basses,
   cellos, timpani, horns, trumpet, violins, cymbals) into data/theme/: three looping stems that stack (0 strings, choir and basses; 1 adds cellos, timpani
   and a snare cadence; 2 adds horns, trumpet, violins and cymbals) and three one-shots (a big and a small hit for card changes, and the ending).
   This file mixes them: the stems loop on the title card, the energy follows the card on screen, a hit lands on each card change, and the whole thing
   steps aside while an NFL clip is playing with its own sound. Nothing plays until the listener taps the theme button.

   Theme.setup()                      look for this week's theme (a promise; rejects when there is none)
   Theme.start()                      (from a tap) load the audio and start the title-card loop
   Theme.card(type, i, n)             a card change: set the energy and hit it
   Theme.mute(on)  Theme.duck(on)     silence it (the sound button), or dip it while an NFL clip plays with its own sound
   Theme.finish()  Theme.stop()       the ending; stop */
(function (global) {
  'use strict';
  var BASE = '/data/theme/', NAMES = ['l0', 'l1', 'l2', 'big', 'small', 'end'];
  // how much of the arrangement plays on each kind of card: 0 strings and choir, 1 adds the drive, 2 everything
  var LEVELS = { intro: 2, game: 2, finals: 1, race: 1, clinch: 2, trades: 1, slack: 1, pod: 0, shotguns: 1, records: 2, lifetime: 1, coming: 2, wait: 0 };

  var plan = null, planP = null, ctx = null, master = null, duckG = null, stemG = [], bufs = {}, loading = null, timer = null, loopSrcs = [];
  var armed = false, silent = false, ducked = false, level = 2, nextLoop = 0, ready = false, ended = false;

  function setup() {
    if (planP) return planP;
    planP = fetch(BASE + 'plan.json?h=' + Math.floor(Date.now() / 3600000), { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error('no theme'); return r.json(); }).then(function (p) { plan = p; return p; });
    return planP;
  }
  function ensure() {
    if (ctx) return ctx;
    var AC = global.AudioContext || global.webkitAudioContext; if (!AC) return null;
    ctx = new AC();
    var comp = ctx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 3; comp.attack.value = .01; comp.release.value = .25;
    master = ctx.createGain(); master.gain.value = 0.0001; duckG = ctx.createGain();
    for (var i = 0; i < 3; i++) { var g = ctx.createGain(); g.gain.value = i === 0 ? 1 : 0.0001; g.connect(comp); stemG.push(g); }
    comp.connect(duckG); duckG.connect(master); master.connect(ctx.destination);
    return ctx;
  }
  function load() {
    if (loading) return loading;
    var v = (plan.week || 0) + '-' + (plan.generatedAt || '');
    loading = Promise.all(NAMES.map(function (n) {
      return fetch(BASE + n + '.mp3?v=' + encodeURIComponent(v)).then(function (r) { if (!r.ok) throw new Error(n); return r.arrayBuffer(); })
        .then(function (ab) { return new Promise(function (res, rej) { ctx.decodeAudioData(ab, res, rej); }); }).then(function (b) { bufs[n] = b; });
    })).then(function () { ready = true; });
    return loading;
  }
  function vol(fast) {
    if (!ctx) return;
    var t = ctx.currentTime;
    master.gain.cancelScheduledValues(t); master.gain.setTargetAtTime((armed && !silent) ? 0.5 : 0.0001, t, fast ? .05 : .4);
    duckG.gain.cancelScheduledValues(t); duckG.gain.setTargetAtTime(ducked ? 0.0001 : 1, t, fast ? .05 : .25);
    stemG[1].gain.setTargetAtTime(level >= 1 ? 1 : 0.0001, t, .5); stemG[2].gain.setTargetAtTime(level >= 2 ? 1 : 0.0001, t, .5);
  }
  function scheduleLoops() {   // each pass starts exactly one loop length after the last; the stems carry their own reverb tails, so the seam is silent
    if (!ready || !armed || ended) return;
    while (nextLoop < ctx.currentTime + 3) {
      for (var i = 0; i < 3; i++) { var s = ctx.createBufferSource(); s.buffer = bufs['l' + i]; s.connect(stemG[i]); s.start(nextLoop); loopSrcs.push(s); s.onended = (function (x) { return function () { var k = loopSrcs.indexOf(x); if (k >= 0) loopSrcs.splice(k, 1); }; })(s); }
      nextLoop += plan.loop;
    }
  }
  function shot(name, gain) {
    if (!ready || !ctx || !armed || silent || !bufs[name]) return;
    var s = ctx.createBufferSource(), g = ctx.createGain(); s.buffer = bufs[name]; g.gain.value = gain; s.connect(g); g.connect(duckG); s.start(ctx.currentTime + .02);
  }
  function start() {
    if (!plan || !ensure()) return;
    armed = true; silent = false; ended = false;
    if (ctx.state === 'suspended') ctx.resume();
    vol();
    load().then(function () {
      if (!armed) return;
      if (!timer) { nextLoop = ctx.currentTime + .1; timer = setInterval(scheduleLoops, 400); scheduleLoops(); shot('big', .8); }
    }, function () { armed = false; });
  }
  function stop() {
    armed = false; ended = true; vol(true);
    if (timer) { clearInterval(timer); timer = null; }
    var old = loopSrcs; loopSrcs = [];
    setTimeout(function () { old.forEach(function (s) { try { s.stop(); } catch (e) { /* done */ } }); }, 400);
  }
  function card(type, i, n) {
    level = LEVELS[type] != null ? LEVELS[type] : 1;
    if (type === 'play') { ducked = true; vol(true); return; }
    var wasDucked = ducked; ducked = false; vol(true);
    shot((i === 0 || wasDucked || i === n - 1) ? 'big' : 'small', .8);
  }
  function mute(on) { silent = !!on; vol(true); }
  function duck(on) { ducked = !!on; vol(true); }
  function finish() {
    if (!armed) return;
    level = 0; vol(); shot('end', .9); ended = true;
    if (timer) { clearInterval(timer); timer = null; }
    var t = ctx.currentTime; stemG.forEach(function (g) { g.gain.cancelScheduledValues(t); g.gain.setTargetAtTime(0.0001, t, 1.2); });
    setTimeout(function () { var old = loopSrcs; loopSrcs = []; old.forEach(function (s) { try { s.stop(); } catch (e) { /* done */ } }); armed = false; }, 9000);
  }
  if (global.document) document.addEventListener('visibilitychange', function () { if (!ctx) return; if (document.hidden) ctx.suspend(); else if (armed) ctx.resume(); });

  global.Theme = { setup: setup, start: start, stop: stop, card: card, mute: mute, duck: duck, finish: finish, armed: function () { return armed; }, plan: function () { return plan; } };
})(window);
