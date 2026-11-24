#!/usr/bin/env python3
"""Builds the weekly recap that /recap plays (data/recap.json and data/recap_<week>.json).

    python3 tools/build_recap.py                      # the last finished week, tools read from raw.githubusercontent.com
    python3 tools/build_recap.py --week 10            # a specific week
    python3 tools/build_recap.py --src /path          # sibling checkouts: /path/<Repo>/<file> (for testing)

The page is a short sequence of segments (cards and embedded clips). Which ones appear, how many, in what order and for how long is decided
here from what actually happened that week, so a wild week runs long and a quiet one is shorter. Everything comes from files the hub already
publishes. Nothing is posted to Slack from here; the page is the only place the recap lives.
"""
import argparse, datetime as dt, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_feed as bf   # play_title / play_sub / fantasy / source / fetch

HUB = bf.HUB
BUDGET = 250          # seconds, the page never runs longer (clips usually end before their slot does)
SITE = 'https://namkurd.github.io'


def load(path, default=None):
    try:
        return json.load(open(os.path.join(HUB, path), encoding='utf-8'))
    except Exception:
        return default


def pct(x):
    return None if x is None else int(round(x))


# ---------------------------------------------------------------- standings
def standings_move(hist, week):
    """Rank and Rumbles before and after `week` (the cumulative Rumbles of the weeks completed, ties broken by points scored)."""
    names = {int(r['roster_id']): r['manager'] for r in hist['standings']}
    weekly = hist['weekly']

    def table(upto):
        tot = {rid: [0, 0.0] for rid in names}
        for w in range(1, upto + 1):
            for rid, d in (weekly.get(str(w)) or {}).items():
                rid = int(rid)
                if rid in tot:
                    tot[rid][0] += d.get('rumbles', 0)
                    tot[rid][1] += d.get('points', 0)
        order = sorted(tot, key=lambda r: (-tot[r][0], -tot[r][1]))
        return {r: (i + 1, tot[r][0]) for i, r in enumerate(order)}
    before, after = table(week - 1), table(week)
    rows = []
    for rid, (rk, rb) in after.items():
        pk, pb = before[rid]
        wk = (weekly.get(str(week)) or {}).get(str(rid)) or {}
        rows.append({'m': names[rid], 'rank': rk, 'prev': pk, 'rumbles': rb, 'gain': wk.get('rumbles', 0), 'pts': wk.get('points')})
    rows.sort(key=lambda r: r['rank'])
    return rows


# ---------------------------------------------------------------- segments
def chart_for(p):
    """The head-to-head's win-probability curve (data/wpcharts.json, from Rumble Central) turned to the play-maker's side, and where the play sits on it."""
    ch = (((load('data/wpcharts.json') or {}).get('weeks') or {}).get(str(p['week'])) or {}).get('%s.%s' % (p.get('aid'), p.get('bid')))
    if not ch or p.get('x') is None:
        return None, None
    flip = p.get('by') != p['a']   # the curve is the first manager's chance; show the play-maker's
    return ch, {'flip': flip, 'x': p['x'], 'pp': round(1 - p['pp'], 3) if flip else p['pp']}


def play_segment(p, kind, label):
    fa = bf.fantasy(p)
    return {'type': 'play', 'kind': kind, 'label': label, 'title': bf.play_title(p['who'], p['label'], p.get('sid'), p.get('stk'), p.get('slab')),
            'sub': bf.play_sub(p), 'by': p.get('by'), 'a': p['a'], 'b': p['b'], 'pts': p.get('tot') if p.get('tot') is not None else p.get('pts'),
            'from': pct(p.get('from')), 'to': pct(p.get('to')), 'swing': round(p['swing'] * 100), 'clip': p['clip'], **({'alt': p['alt']} if p.get('alt') else {}),
            'et': p.get('et'), 'sit': p.get('sit'), **({'fant': fa} if fa else {}),
            'href': 'https://www.youtube.com/watch?v=%s&t=%ds' % (p['clip']['id'], int(p['clip']['s'])),
            'replay': '/SleeperLiveRumbles/rumbles.html?wp=%d.%s.%s%s' % (p['week'], p.get('aid'), p.get('bid'), '&t=%d' % p['rt'] if p.get('rt') is not None else ''),
            '_ck': '%s.%s.%s' % (p['week'], p.get('aid'), p.get('bid')), **({'star': chart_for(p)[1]} if chart_for(p)[1] else {})}


# ---------------------------------------------------------------- podcast transcript -> "From the pod" quote
def fetch_transcript(video_id):
    """[{text, start}] from the video's captions, or None. youtube-transcript-api (pip install youtube-transcript-api); YouTube sometimes refuses
    data-center addresses, in which case this returns None and the recap simply has no pod card (it is retried on a later run)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        if hasattr(api, 'fetch'):
            return [{'text': x.text, 'start': x.start} for x in api.fetch(video_id, languages=['en'])]
        return [{'text': x['text'], 'start': x['start']} for x in YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])]
    except Exception as e:
        print('transcript: %s: %s' % (type(e).__name__, str(e)[:160]), file=sys.stderr)
        return None


def pod_quote(cues, keywords, window=28, width=230):
    """The stretch of the episode that talks most about this week: keywords = {word: weight}. Cues are cut into `window`-second spans, each scored by
    the weight of the distinct keywords it names; returns {at, quote, hits} for the best span (at least two distinct keywords), or None."""
    import re
    spans, cur = [], []
    for c in cues:
        if cur and c['start'] - cur[0]['start'] > window:
            spans.append(cur); cur = []
        cur.append(c)
    if cur:
        spans.append(cur)
    best = None
    for sp in spans:
        text = re.sub(r'\s+', ' ', ' '.join(c['text'] for c in sp).replace('\n', ' ')).strip()
        hits = {}
        for w, wt in keywords.items():
            m = re.search(r'\b%s\b' % re.escape(w), text, re.I)
            if m:
                hits[w] = (wt, m.start())
        if len(hits) < 2:
            continue
        score = sum(wt for wt, _ in hits.values())
        if best is None or score > best[0]:
            best = (score, sp, text, hits)
    if not best:
        return None
    _, sp, text, hits = best
    first = min(pos for _, pos in hits.values())
    lo = max(0, first - 70)
    if lo:
        lo = text.rfind(' ', 0, lo) + 1 if text.rfind(' ', 0, lo) >= 0 else 0
    q = text[lo:lo + width]
    if lo + width < len(text):
        q = q[:q.rfind(' ')] if ' ' in q else q
        q += '\u2026'
    return {'at': int(sp[0]['start']), 'quote': (('\u2026' if lo else '') + q).strip(), 'hits': sorted(hits)}


def pod_card(pod, names, picks, asof, transcript=None):
    """The "From the pod" segment for the latest episode, or None. Retries a failed transcript fetch at most every 6 hours (data/recap_pod.json)."""
    vid = (pod or {}).get('videoId')
    if not vid:
        return None
    path = os.path.join(HUB, 'data', 'recap_pod.json')
    prev = load('data/recap_pod.json', {}) or {}
    now = dt.datetime.now(dt.timezone.utc)
    kw = {}
    for n in names:
        kw[n] = 1
    for p in picks:
        for who in (p.get('stk') or [p['who']]):
            last = (who or '').split()[-1].strip('.')
            if len(last) >= 4:
                kw[last] = 2
    if transcript is None:
        if prev.get('videoId') == vid and (prev.get('card') or (prev.get('tried') and now - dt.datetime.fromisoformat(prev['tried']) < dt.timedelta(hours=6))):
            return prev.get('card')
        transcript = fetch_transcript(vid)
    card = None
    if transcript:
        q = pod_quote(transcript, kw)
        if q:
            card = {'type': 'pod', 'dur': 9, 'title': 'From the pod', 'ep': pod.get('episode'), 'name': pod.get('name'), 'quote': q['quote'], 'at': q['at'],
                    'url': 'https://www.youtube.com/watch?v=%s&t=%ds' % (vid, q['at']), 'hits': q['hits']}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'videoId': vid, 'tried': now.isoformat(), 'card': card}, f, ensure_ascii=False, indent=1)
    return card


# ---------------------------------------------------------------- career head to head
def text_source(src, repo, path):
    if src:
        return open(os.path.join(src, repo, path), encoding='utf-8').read()
    import urllib.request
    url = bf.RAW.format(repo=repo, path=path) + '?t=%d' % __import__('time').time()
    if repo == 'Recordbook':
        url = url.replace('/main/', '/claude/initial-build/')   # that repo's default branch
    req = urllib.request.Request(url, headers={'User-Agent': 'dtf-club-hub'})
    return urllib.request.urlopen(req, timeout=60).read().decode('utf-8')


def h2h_book(src, hist):
    """Every real head-to-head the league has on record (regular season 2021 on from the Head-to-Head tool's frozen record, then this season from
    Rumble Central's history, plus the playoff games): a function series(a, b) -> the career meetings of two managers, oldest first."""
    import csv, io
    games = []   # (season, week, kind, winner, loser)
    try:
        for r in csv.DictReader(io.StringIO(text_source(src, 'Sleeper-Head-to-Head', 'history_baseline.tsv')), delimiter='\t'):
            if int(r['Season']) < int(hist.get('season', 9999)):
                games.append((int(r['Season']), int(r['Week']), 'R', r['Winner'], r['Loser']))
    except Exception as e:
        print('h2h baseline: %s' % e, file=sys.stderr)
    try:
        for r in csv.DictReader(io.StringIO(text_source(src, 'Sleeper-Head-to-Head', 'playoff_baseline.tsv')), delimiter='\t'):
            games.append((int(r['Season']), int(r['Week']), 'P', r['Winner'], r['Loser']))
    except Exception as e:
        print('h2h playoffs: %s' % e, file=sys.stderr)
    names = {int(r['roster_id']): r['manager'] for r in hist['standings']}
    for wk, rows in (hist.get('weekly') or {}).items():
        for rid, d in rows.items():
            if d.get('h2h_win') and d.get('opponent_roster_id') in names:
                games.append((int(hist['season']), int(wk), 'R', names[int(rid)], names[d['opponent_roster_id']]))
    games.sort(key=lambda g: (g[0], g[1]))

    def series(a, b):
        return [g for g in games if {g[3], g[4]} == {a, b}]
    return series


def series_card(series, a, b):
    """a's career against b: wins each (regular season), the playoff record, the current streak and the last meetings."""
    gs = series(a, b)
    reg = [g for g in gs if g[2] == 'R']
    aw, bw = sum(1 for g in reg if g[3] == a), sum(1 for g in reg if g[3] == b)
    po = [g for g in gs if g[2] == 'P']
    streak = 0
    for g in reversed(gs):
        if streak == 0 or g[3] == gs[-1][3]:
            streak += 1 if g[3] == gs[-1][3] else 0
        if g[3] != gs[-1][3]:
            break
    last = gs[-1][3] if gs else None
    return {'a': a, 'b': b, 'aw': aw, 'bw': bw, 'pa': sum(1 for g in po if g[3] == a), 'pb': sum(1 for g in po if g[3] == b),
            'streak': {'m': last, 'n': streak} if last else None,
            'last': [{'w': g[3], 's': g[0], 'wk': g[1], 'p': g[2] == 'P'} for g in gs[-5:]][::-1]}


# ---------------------------------------------------------------- trades: how they are panning out (lineup PAR) against what the chat thought
def trade_report(src, season, week, asof):
    """An update on this season's trades that are more than a week old, from the Trade Network: lineup gain in points above replacement (lga for the
    first manager, lgb for the second) and the chat's lean (its sentiment notes: how each commenter rated each side). Each trade's gap is also
    compared with last week's (data/trade_pnl.json keeps one snapshot per recap week). Returns None when there is nothing to say."""
    import statistics
    d = bf.source(src, 'SleeperTradeNodes', 'data.json')
    try:
        sent = bf.source(src, 'SleeperTradeNodes', 'sentiment.json')
    except Exception:
        sent = {}
    cutoff = dt.datetime.combine(asof, dt.time(23, 59, 59), tzinfo=dt.timezone.utc).timestamp() * 1000 - 7 * 864e5
    ts = [t for t in d['trades'] if t['s'] == season and (t.get('ts') or 0) <= cutoff]   # done more than a week ago
    rows, tot = [], {}
    for t in sorted(ts, key=lambda t: t['w']):
        if t.get('lga') is None or t.get('lgb') is None or (t.get('lgw') or 0) < 1:
            continue
        notes = [n for n in (sent.get(t['id']) or {}).get('notes', []) if n.get('a') is not None and n.get('b') is not None and not n.get('inv')]
        lean = (statistics.mean(n['a'] for n in notes) - statistics.mean(n['b'] for n in notes)) if notes else None   # > 0: the chat favoured A
        par = t['lgNet']                                                                                             # > 0: A's lineup gained more
        for m, v in ((t['a'], t['lga']), (t['b'], t['lgb'])):
            tot[m] = tot.get(m, 0) + v
        r = {'id': t['id'], 'a': t['a'], 'b': t['b'], 'w': t['w'], 'weeks': t.get('lgw'),
             'ga': [{'n': bf.short_player(x['n']), 'p': (re.match(r'^(QB|RB|WR|TE|K|DEF|DST)\b', x['n']) or [None])[0]} for x in t.get('bg', [])],   # what A received
             'gb': [{'n': bf.short_player(x['n']), 'p': (re.match(r'^(QB|RB|WR|TE|K|DEF|DST)\b', x['n']) or [None])[0]} for x in t.get('ag', [])],   # what B received
             'sa': None if not notes else round(statistics.mean(n['a'] for n in notes), 1), 'sb': None if not notes else round(statistics.mean(n['b'] for n in notes), 1), 'nn': len(notes), 'lga': t['lga'], 'lgb': t['lgb'], 'par': par, 'lean': None if lean is None else round(lean, 2)}
        r['parw'] = None if abs(par) < 5 else (t['a'] if par > 0 else t['b'])
        r['chatw'] = None if lean is None or abs(lean) < 0.2 else (t['a'] if lean > 0 else t['b'])
        r['verdict'] = None if not (r['parw'] and r['chatw']) else 'right' if r['parw'] == r['chatw'] else 'wrong'
        rows.append(r)
    if not rows:
        return None
    # last week's gap for each trade, then this week's is saved for next time
    path = os.path.join(HUB, 'data', 'trade_pnl.json')
    snap = load('data/trade_pnl.json', {}) or {}
    snap.setdefault('weeks', {})
    prev = {}
    for wk in sorted((int(k) for k in snap['weeks'] if int(k) < week)):
        prev = snap['weeks'][str(wk)]
    for r in rows:
        if r['id'] in prev:
            r['moved'] = round(r['par'] - prev[r['id']], 1)   # > 0: A's side gained on B since last week
    snap['weeks'][str(week)] = {r['id']: r['par'] for r in rows}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(snap, f, separators=(',', ':'))
    clear = [r for r in rows if r['verdict']]
    right = sum(1 for r in clear if r['verdict'] == 'right')
    shown = sorted(rows, key=lambda r: -abs(r['par']))   # every trade made more than a week ago
    if not shown:
        return None
    lead = sorted(tot.items(), key=lambda kv: -kv[1])
    return {'rows': [{k: v for k, v in r.items() if k != 'id'} for r in shown], 'clear': len(clear), 'right': right, 'n': len(rows),
            'best': [{'m': m, 'v': round(v, 1)} for m, v in lead[:2] if v > 0], 'worst': [{'m': m, 'v': round(v, 1)} for m, v in lead[::-1][:1] if v < 0]}


# ---------------------------------------------------------------- the comment of the week (most reactions), frozen once chosen
def comment_of_week(week, asof):
    path = os.path.join(HUB, 'data', 'comment_%d.json' % week)
    c = load('data/comment_%d.json' % week)
    if c:
        return c
    token = os.environ.get('SLACK_BOT_TOKEN')
    if not token:
        return None
    try:
        import build_slack, recap_slack
        import time as _t
        c = recap_slack.best_comment(build_slack.Slack(token), _t.time() - 7 * 86400)
    except Exception as e:
        print('comment of the week: %s' % e, file=sys.stderr)
        return None
    if c:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
    return c


# ---------------------------------------------------------------- the Mount Rushmore vote: closes five days after the post (kept in data/mountrushmore.json)
MR_CHANNEL = 'C0CJXBMAYHM'


def mr_vote(asof):
    """The open Mount Rushmore vote as {label, when, days, kind} or None. With SLACK_BOT_TOKEN the newest "Episode N Mount Rushmore: topic" post in
    #mountrushmore is read and the file refreshed; the vote closes five days after it was posted."""
    from zoneinfo import ZoneInfo
    path = os.path.join(HUB, 'data', 'mountrushmore.json')
    cur = load('data/mountrushmore.json') or {}
    token = os.environ.get('SLACK_BOT_TOKEN')
    if token:
        try:
            import build_slack, time as _t
            sl = build_slack.Slack(token)
            best = None
            for m in sl.pages('conversations.history', 'messages', channel=MR_CHANNEL, oldest='%.6f' % (_t.time() - 14 * 86400), limit=200):
                mt = re.match(r'^\s*Episode (\d+) Mount Rushmore: (.+?)\s*(?:\n|\*Sent using\*|$)', m.get('text') or '')
                if mt and (not m.get('thread_ts') or m.get('thread_ts') == m.get('ts')) and (best is None or int(mt.group(1)) > best[0]):   # the latest EPISODE, not the latest post (last week's can be re-posted after)
                    best = (int(mt.group(1)), mt.group(2).strip(), float(m['ts']))
            if best:
                posted = dt.datetime.fromtimestamp(best[2], dt.timezone.utc)
                host = ((load('league.json') or {}).get('slack') or 'https://dtf-club.slack.com/').rstrip('/')
                cur = {'episode': best[0], 'topic': best[1], 'ts': '%.6f' % best[2], 'href': '%s/archives/%s/p%s' % (host, MR_CHANNEL, ('%.6f' % best[2]).replace('.', '')), 'postedAt': posted.strftime('%Y-%m-%dT%H:%M:%SZ'), 'closesAt': (posted + dt.timedelta(days=5)).strftime('%Y-%m-%dT%H:%M:%SZ')}
                json.dump(cur, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except Exception as e:
            print('mount rushmore: %s' % e, file=sys.stderr)
    if not cur.get('closesAt'):
        return None
    closes = dt.datetime.fromisoformat(cur['closesAt'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York'))
    days = (closes.date() - asof).days
    if days < 0:
        return None
    return {'label': 'Mount Rushmore vote closes', 'sub': 'Episode %s: %s' % (cur.get('episode'), cur.get('topic')), 'when': closes.strftime('%a %b %-d') + ', ' + closes.strftime('%-I:%M %p ET'), 'days': days, 'kind': 'vote'}


def build(week, src, asof):
    season = (load('league.json') or {}).get('season') or asof.year
    hist = bf.source(src, 'SleeperLiveRumbles', 'rumbles_history.json')
    names = {int(r['roster_id']): r['manager'] for r in hist['standings']}
    tp = load('data/topplays.json') or {}
    plays = [p for p in (tp.get('weeks') or {}).get(str(week), []) if p.get('clip')]
    plays.sort(key=lambda p: -p['swing'])
    weekly = (hist['weekly'].get(str(week)) or {})
    segs, used = [], set()

    # ---- the week's real head-to-head games
    games, seen = [], set()
    for rid, d in weekly.items():
        rid = int(rid); opp = d.get('opponent_roster_id')
        if (opp, rid) in seen:
            continue
        seen.add((rid, opp))
        a, b = (rid, opp) if d.get('h2h_win') or d['points'] >= d['opponent_points'] else (opp, rid)
        w, l = (d['points'], d['opponent_points']) if a == rid else (d['opponent_points'], d['points'])
        games.append({'w': names[a], 'l': names[b], 'ws': round(w, 2), 'ls': round(l, 2), 'margin': round(w - l, 2)})
    mu = {tuple(sorted(x['names'])): x for x in ((load('data/matchups.json') or {}).get('weeks', {}).get(str(week)) or []) if x.get('h2h')}
    for g in games:
        x = mu.get(tuple(sorted([g['w'], g['l']])))
        g['flips'] = (x or {}).get('flips', 0)
        g['it'] = (x or {}).get('it', 0)

    # ---- the story of the week
    close = min(games, key=lambda g: g['margin']) if games else None
    wild = max(games, key=lambda g: (g['flips'], g['it'])) if games else None
    # the opener is the week's scoreboard: every real game, final, most interesting first (no stat that the standings already say)
    segs.append({'type': 'intro', 'dur': 6, 'week': week, 'season': season, 'title': 'Week %d recap' % week, 'rundown': []})

    # ---- clips: candidates only; the page keeps the first ones that really play in the viewer's browser (an owner who blocks embedding is skipped)
    def is_def(p):
        return bool(re.match(r'^[A-Z]{2,4}$', p.get('sid') or ''))   # a team defense's score is credited to the team code

    def spread(rows, n):   # best first, never more than three from one matchup
        out, per = [], {}
        for p in rows:
            key = tuple(sorted([p['a'], p['b']]))
            if per.get(key, 0) >= 3 or len(out) >= n:
                continue
            out.append(p); per[key] = per.get(key, 0) + 1
        return out
    offense, defense = spread([p for p in plays if not is_def(p)], 8), spread([p for p in plays if is_def(p)], 3)
    cands = offense + defense
    picks = offense[:3] + defense[:1]
    if cands:
        segs.append({'type': 'clips', 'dur': 17, 'want': 4 if defense else min(4, len(offense)), 'defWant': 1 if defense else 0, 'label': 'play of the week',
                     'charts': {'%s.%s.%s' % (p['week'], p.get('aid'), p.get('bid')): chart_for(p)[0] for p in cands if chart_for(p)[0]},
                     'cands': [dict(play_segment(p, 'top', ''), **({'def': True} if is_def(p) else {})) for p in cands]})
    turning = None   # (the turning-point clip card was removed: the plays are the plays)

    # ---- the game of the week: the closest real game, or the one that traded the lead most, with the plays that decided it as its box score
    if games:
        g = close if close['margin'] <= 8 else wild
        why = ('Decided by %.1f' % g['margin']) if g is close else ('%d lead changes' % g['flips'])
        recs = {r['manager']: '%d-%d' % (r.get('h2h_w', 0), r.get('h2h_l', 0)) for r in hist['standings']}
        allp = [p for p in (tp.get('weeks') or {}).get(str(week), []) if {p['a'], p['b']} == {g['w'], g['l']}]

        def side(m):
            mine = sorted([p for p in allp if p.get('by') == m], key=lambda p: -(p.get('tot') if p.get('tot') is not None else (p.get('pts') or 0)))[:3]
            return {'m': m, 'rec': recs.get(m), 'lines': [{'t': bf.play_title(p['who'], p['label'], p.get('sid'), p.get('stk'), p.get('slab')),
                                                          'pts': p.get('tot') if p.get('tot') is not None else p.get('pts')} for p in mine]}
        gseg = {'type': 'game', 'dur': 9, 'title': 'Game of the week', 'why': why, 'w': g['w'], 'l': g['l'], 'ws': g['ws'], 'ls': g['ls'], 'flips': g['flips'],
                'sides': [side(g['w']), side(g['l'])]}
        pair = [p for p in allp if {p['a'], p['b']} == {g['w'], g['l']}]   # the week's win-probability curve for this matchup (the winner's side)
        gch = chart_for(pair[0])[0] if pair else None
        if gch:
            gseg['chart'] = {'x': gch['x'], 'p': gch['p'], 'flip': g['w'] != pair[0]['a'], 'gaps': gch.get('gaps') or []}
        segs.append(gseg)

    # ---- career head to head: every game's career record, a column on the scores card
    series = None
    try:
        series = h2h_book(src, hist)
    except Exception as e:
        print('h2h: %s' % e, file=sys.stderr)
    if series and games:
        for gm in games:
            r = series_card(series, gm['w'], gm['l'])
            gm['sr'] = '%d\u2013%d' % (r['aw'], r['bw'])

    # ---- around the league: the other scores, one line per game (the box score lives on the Game card)
    if games:
        allsc = sorted([g['ws'] for g in games] + [g['ls'] for g in games], reverse=True)   # every team's score this week
        hi, lo = max(games, key=lambda g: g['ws']), min(games, key=lambda g: g['ls'])
        blow, nail = max(games, key=lambda g: g['ws'] - g['ls']), min(games, key=lambda g: g['ws'] - g['ls'])
        robbed = max(games, key=lambda g: g['ls'])   # the best score on a losing side
        rrank = allsc.index(robbed['ls']) + 1
        ords = {1: 'highest', 2: '2nd-highest', 3: '3rd-highest', 4: '4th-highest', 5: '5th-highest', 6: '6th-highest'}
        gl = []
        for g in sorted(games, key=lambda g: -g['it']):
            tags = []
            if g is hi: tags.append('HIGH SCORE')
            if g is blow: tags.append('BLOWOUT')
            if g is nail: tags.append('CLOSEST')
            if g is robbed and rrank <= 4: tags.append('UNLUCKY')
            gl.append({'w': g['w'], 'l': g['l'], 'ws': g['ws'], 'ls': g['ls'], 'sr': g.get('sr'), 'tags': tags})
        fhead = '%s scored %.1f, the week\u2019s best' % (hi['w'], hi['ws'])
        if rrank <= 4 and robbed['ls'] > 0:
            fhead += ' \u00b7 %s lost with the %s score (%.1f)' % (robbed['l'], ords.get(rrank, '%dth-highest' % rrank), robbed['ls'])
        segs.append({'type': 'finals', 'dur': 8, 'title': 'Around the league', 'head': fhead, 'games': gl})

    # ---- trades: how the ones made more than a week ago are panning out (lineup PAR) against what the chat thought at the time
    try:
        tr = trade_report(src, int(season), week, asof)
        if tr:
            top = tr['rows'][0]
            ahead, behind = (top['a'], top['b']) if top['par'] > 0 else (top['b'], top['a'])
            hd = '%s is %d PAR ahead in the %s trade' % (ahead, round(abs(top['par'])), behind)
            segs.append({'type': 'trades', 'dur': 11, 'title': 'Trade report', 'head': hd, **tr})
    except Exception as e:
        print('trades: %s' % e, file=sys.stderr)

    # ---- the podcast: the latest episode, with the stretch where the hosts talk about this week when the captions could be read
    try:
        pod = load('podcast.json') or {}
        posted = (pod.get('postedAt') or '')[:10]
        if pod.get('videoId') and posted and abs((asof - dt.date.fromisoformat(posted)).days) <= 10:
            pc = pod_card(pod, set(names.values()), picks + ([turning] if turning else []), asof,
                          transcript=None if not os.environ.get('RECAP_TRANSCRIPT') else json.load(open(os.environ['RECAP_TRANSCRIPT'])))
            if pc:   # no captions, no card: the picture alone says nothing
                segs.append({'type': 'pod', 'dur': 9, 'title': 'The podcast', 'ep': pod.get('episode'), 'name': pod.get('name'), 'quote': pc['quote'], 'at': pc['at'], 'url': pc['url'], 'hits': pc['hits']})
    except Exception as e:
        print('pod: %s' % e, file=sys.stderr)

    # ---- the league chat: the comment of the week (most reactions) and the busiest conversations (slack.json titles, channel and counts)
    try:
        sl = load('slack.json') or {}
        rows = [t for t in sl.get('topics', []) if not (t.get('title') or '').startswith('*CONTENT BOYS')][:3]
        cm = comment_of_week(week, asof)
        if rows or cm:
            segs.append({'type': 'slack', 'dur': 9, 'title': 'League chat', 'comment': cm, 'items': [{'t': t['title'], 'ch': t['channel'], 'n': t['messages'], 'p': t['people'], 'href': t.get('href')} for t in rows]})
    except Exception as e:
        print('slack: %s' % e, file=sys.stderr)

    # ---- shotguns: new this week, and every one still owed (the punishment not served yet), oldest first, grouped by manager
    new_s, owed = [], {}
    for m in (load('shotguns.json') or {}).get('managers', []):
        for sh in m.get('shots', []):
            if sh.get('week', 99) > week:
                continue
            row = {'m': m['name'], 'player': sh.get('full') or sh.get('player'), 'short': sh.get('player'), 'pos': sh.get('pos'), 'wk': sh.get('week')}
            if sh.get('week') == week:
                new_s.append(row)
            if not sh.get('done'):
                owed.setdefault(m['name'], []).append(row)
    owed_rows = sorted(({'m': k, 'n': len(v), 'shots': sorted(v, key=lambda x: x['wk']), 'oldest': min(x['wk'] for x in v)} for k, v in owed.items()), key=lambda r: (-r['n'], r['oldest'], r['m']))   # most owed first
    if new_s or owed_rows:
        segs.append({'type': 'shotguns', 'dur': 8, 'title': 'Shotgun watch', 'new': new_s, 'owed': owed_rows, 'week': week})

    # ---- records broken that week (the Record Book's change log)
    end = min(dt.datetime.now(dt.timezone.utc), dt.datetime.combine(asof, dt.time(23, 59, 59), tzinfo=dt.timezone.utc))   # only records broken in the last 7 days
    rec, since = [], (end - dt.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    path = os.path.join(src, 'Recordbook', 'data', 'changelog.jsonl') if src else None
    lines = []
    try:
        if path:
            lines = open(path, encoding='utf-8').read().splitlines()
        else:
            import urllib.request
            lines = text_source(None, 'Recordbook', 'data/changelog.jsonl').splitlines()
    except Exception as e:
        print('records: %s' % e, file=sys.stderr)
    for l in lines:
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d.get('ts', '') >= since and (d.get('cause') or '').startswith('auto') and d.get('new'):
            rec.append({'name': d.get('name'), 'old': (d.get('old') or {}).get('value'), 'new': d['new'].get('value'), 'holder': d['new'].get('holder'),
                        'prev': (d.get('old') or {}).get('holder')})
    if rec:
        segs.append({'type': 'records', 'dur': 6 if len(rec) < 3 else 9, 'title': 'New records', 'items': rec[:5]})

    # ---- lifetime standings: who moved in the Lifetime tool's all-time ranks since its last update (this season's managers only)
    life = []
    try:
        LM = [('rumble_rank', 'Rumbles', lambda r: '{:,} Rumbles'.format(int(r['rumbles']))), ('h2h_w_rank', 'H2H wins', lambda r: '%d wins' % r['w']),
              ('pf_rank', 'Points for', lambda r: '{:,.1f} pts'.format(r['pf'])), ('field_pct_rank', 'Field win %', lambda r: '%.1f%%' % (r['field_pct'] * 100))]
        allrows = bf.source(src, 'sleepersheet', 'data/standings.json')['all_time']['rows']
        for r in allrows:
            if r['name'] not in set(names.values()):
                continue
            mv = []
            for k, lab, fmtv in LM:
                dl = r.get(k + '_delta')
                if not dl:
                    continue
                # who they just passed (a climb) or who just passed them (a slide): the neighbour on the other side of the move
                nb = [o for o in allrows if o.get(k) == r[k] + (1 if dl > 0 else -1)]
                mv.append({'m': r['name'], 'metric': lab, 'rank': r[k], 'delta': dl, 'val': fmtv(r),
                           **({'vs': {'m': nb[0]['name'], 'val': fmtv(nb[0]), 'passed': dl > 0}} if nb else {})})
            life += mv
        life.sort(key=lambda x: (x['metric'] != 'Rumbles', -abs(x['delta']), x['rank']))
    except Exception as e:
        print('lifetime: %s' % e, file=sys.stderr)
    if life:
        segs.append({'type': 'lifetime', 'dur': 7 if len(life) < 4 else 9, 'title': 'Lifetime standings', 'items': life[:5]})

    # ---- standings, toward the end; longer when the table moved
    st = standings_move(hist, week)
    moved = sum(1 for r in st if r['rank'] != r['prev'])
    big = max((abs(r['prev'] - r['rank']) for r in st), default=0)

    # ---- the playoff race (data/race.json, read out of Rumble Central by tools/build_race.py)
    race = load('data/race.json')
    if race and race.get('teams') and race.get('season') == season and race.get('played') >= week:
        ts_ = sorted(race['teams'], key=lambda t: t['rank'])
        P = race['spots']
        shown = ts_
        bub = sorted(sorted([t for t in ts_ if 0.05 < t['make'] < 0.95], key=lambda t: abs(t['make'] - .5))[:3], key=lambda t: -t['make'])
        hd = ('On the bubble: ' + ', '.join('%s %d%%' % (t['m'], round(t['make'] * 100)) for t in bub)) if bub else ''
        # each recap keeps its odds (data/race_<week>.json), so the next one can show how every team's chance moved
        prevp = load('data/race_%d.json' % (week - 1)) or {}
        try:
            with open(os.path.join(HUB, 'data', 'race_%d.json' % week), 'w', encoding='utf-8') as f:
                json.dump({t['m']: round(t['make'], 3) for t in ts_}, f, separators=(',', ':'))
        except Exception as e:
            print('race snapshot: %s' % e, file=sys.stderr)
        segs.append({'type': 'race', 'dur': 12, 'title': 'Playoff hunt', 'head': '', 'bubble': hd, 'spots': P, 'byes': race['byes'], 'weeksLeft': race['weeksLeft'],
                     'teams': [{'m': t['m'], 'rank': t['rank'], 'R': t.get('R'), 'make': t['make'], 'prev': prevp.get(t['m']), 'bye': t.get('bye'), 'x': t['x'], 'z': t['z'], 'top': t['top'], 'dead': t['dead']} for t in shown]})

    # ---- clinching scenarios for this week (Rumble Central's cards, read into data/race.json): who can lock it up and what has to happen
    if race and race.get('teams') and race.get('season') == season and race.get('played') >= week:
        items = []
        for t in sorted(race['teams'], key=lambda t: t['rank']):
            sc = t.get('scen') or {}
            p_, o_ = sc.get('p'), sc.get('o')
            if t['x'] or t['dead']:
                continue   # already settled
            if p_ and t['make'] >= 0.5 and (p_.get('own') is not None or p_.get('real') is not None):
                items.append({'m': t['m'], 'kind': 'clinch', 'own': p_.get('own'), 'need': p_.get('real') if p_.get('real') is not None else p_.get('long'), 'allow': p_['help']['allow'],
                              'help': [{'n': h['n'], 'th': h['th']} for h in p_['help']['list'][:5]], 'make': t['make']})
            elif o_ and (o_.get('own') is not None or o_.get('real') is not None):
                items.append({'m': t['m'], 'kind': 'elim', 'own': o_.get('own'), 'need': o_.get('real') if o_.get('real') is not None else o_.get('long'), 'must': max(0, len(o_['help']['list']) - o_['help']['allow']),
                              'help': [{'n': h['n'], 'th': h['th']} for h in o_['help']['list'][:5]], 'make': t['make']})
        for t in sorted(race['teams'], key=lambda t: t['rank']):   # a first-round bye
            b_ = (t.get('scen') or {}).get('b')
            if b_ and not t['z'] and not t['dead'] and (t.get('bye') or 0) >= 0.2 and (b_.get('own') is not None or b_.get('real') is not None):
                items.append({'m': t['m'], 'kind': 'bye', 'own': b_.get('own'), 'need': b_.get('real') if b_.get('real') is not None else b_.get('long'), 'allow': b_['help']['allow'],
                              'help': [{'n': h['n'], 'th': h['th']} for h in b_['help']['list'][:5]], 'make': t.get('bye')})
        cl = [i for i in items if i['kind'] == 'clinch'][:2] + sorted([i for i in items if i['kind'] == 'bye'], key=lambda i: -i['make'])[:2]
        al = sorted([i for i in items if i['kind'] == 'elim'], key=lambda i: i['make'])[:3]   # the most endangered first
        segs.append({'type': 'clinch', 'dur': 12, 'title': 'Clinch & elimination', 'weeksLeft': race['weeksLeft'], 'max': hist.get('max_rumbles_per_week'), 'items': cl[:3] + al, 'noElim': not al, 'noClinch': not cl}) if (cl or al or race.get('scenWeek')) else None

    # ---- what is coming: the trade deadline, the Mount Rushmore vote closing, the start of the playoffs
    lg = load('league.json') or {}
    coming = []
    for d in lg.get('keyDates') or []:
        days = (dt.date.fromisoformat(d['date']) - asof).days
        if 0 <= days <= 30 and d['id'] in ('trade-deadline', 'playoffs'):
            coming.append({'label': d['label'], 'when': dt.date.fromisoformat(d['date']).strftime('%a %b %-d'), 'days': days, 'kind': d['id']})
    mr = mr_vote(asof)
    if mr:
        coming.append(mr)
    coming.sort(key=lambda c: c['days'])
    if coming:
        segs.append({'type': 'coming', 'dur': 8, 'title': 'Coming up', 'items': coming[:3]})

    # ---- plain-words headlines, the rundown on the opener, and how long each card holds (by how much there is to read)
    def names_and(rows):
        n = [r['m'] for r in rows]
        return n[0] if len(n) == 1 else ', '.join(n[:-1]) + ' and ' + n[-1]

    def head_play(p):
        f, t, by = p.get('from'), p.get('to'), p.get('by') or ''
        if f is None or t is None:
            return ''
        if f < 50 <= t:
            return '%s takes the lead' % by
        if f >= 50 and t > f:
            return '%s pulls away' % by
        if t < 50 and t > f:
            return '%s fights back' % by
        return '%s swings it' % by
    for sg in segs:
        if sg['type'] == 'clips':
            for c in sg['cands']:
                c['head'] = head_play({'from': c.get('from'), 'to': c.get('to'), 'by': c.get('by')})
        elif sg['type'] == 'game':
            sg['head'] = '%s beats %s%s' % (sg['w'], sg['l'], (' after %d lead changes' % sg['flips']) if sg['flips'] >= 2 else ' by %.1f' % (sg['ws'] - sg['ls']))
        elif sg['type'] == 'standings':
            ups = [r for r in sg['rows'] if r['prev'] - r['rank'] >= 2]
            downs = [r for r in sg['rows'] if r['rank'] - r['prev'] >= 2]
            bits = []
            if ups:
                bits.append('%s climb%s %d' % (names_and(ups[:3]), '' if len(ups) > 1 else 's', max(r['prev'] - r['rank'] for r in ups)))
            if downs:
                bits.append('%s drop%s %d' % (names_and(downs[:2]), '' if len(downs) > 1 else 's', max(r['rank'] - r['prev'] for r in downs)))
            sg['head'] = ' \u00b7 '.join(bits)
        elif sg['type'] == 'lifetime' and sg['items']:
            x = sg['items'][0]
            sg['head'] = '%s %s %d in career %s' % (x['m'], 'climbs' if x['delta'] > 0 else 'slips', abs(x['delta']), x['metric'].lower())
        elif sg['type'] == 'records' and sg['items']:
            x = sg['items'][0]
            sg['head'] = '%s: %s' % (x['holder'], x['name'])
    tops = [sg for sg in segs if sg['type'] == 'clips' and not sg.get('turn')]
    rd = []
    if tops and tops[0]['cands']:
        c = tops[0]['cands'][0]
        rd.append({'k': 'Play', 't': '%s, %s' % (c['title'], c['head'] or c['by'])})
    for sg in segs:
        if sg['type'] == 'game':
            rd.append({'k': 'Game', 't': sg['head']})
        elif sg['type'] == 'records' and sg.get('head'):
            rd.append({'k': 'Record', 't': '%s \u2014 %s' % (sg['items'][0]['name'], sg['items'][0]['new'])})
        elif sg['type'] == 'race' and sg.get('bubble'):
            rd.append({'k': 'Race', 't': sg['bubble']})
        elif sg['type'] == 'shotguns' and sg['new']:
            rd.append({'k': 'Shotgun', 't': ', '.join(x['m'] for x in sg['new'])})
    segs[0]['rundown'] = rd[:4]

    def words(x):
        return len(str(x or '').split())

    def read_time(sg):   # seconds to take a card in: a few to see it, more for each line, plus the words
        t = sg['type']
        if t == 'intro': return 3 + 1.3 * len(sg['rundown'])
        if t == 'game': return 10
        if t == 'finals': return 3 + 0.9 * len(sg['games'])
        if t == 'series': return 4 + 0.8 * len(sg['last'])
        if t == 'trades': return 3 + words(sg.get('head')) / 3.5 + 1.1 * len(sg['rows']) + 2   # two sides, players and numbers each, then the season totals
        if t == 'race': return 5 + 0.6 * len(sg['teams']) + (2 if sg.get('bubble') else 0)
        if t == 'pod': return 4 + words(sg.get('quote')) / 2.8
        if t == 'slack':
            cm = sg.get('comment')
            return min(9, 3 + (2 + words(cm.get('text')) / 3.0 if cm else 0) + sum(1.5 + words(x['t']) / 3.5 for x in sg['items']))
        if t == 'shotguns': return 3 + 1.2 * len(sg['new']) + 0.4 * len(sg['owed'])   # a short list of small numbers: a glance
        if t == 'records': return 3 + sum(1.8 + words(x['name']) / 5.0 for x in sg['items'])   # name, new value, holder, what it was
        if t == 'lifetime': return 3 + 1.8 * len(sg['items'])
        if t == 'standings': return 4 + 0.6 * len(sg['rows']) + (2 if sg.get('head') else 0)
        if t == 'coming': return 3 + 2 * len(sg['items'])
        if t == 'clinch': return min(10, 4 + 3 * len(sg['items']) + (2 if sg.get('noElim') else 0))
        return sg['dur']
    for sg in segs:
        if sg['type'] != 'clips':
            sg['dur'] = int(round(read_time(sg)))

    # ---- trim to the budget: drop the least important extras first
    def total():
        return sum(s['dur'] * (s['want'] if s['type'] == 'clips' else 1) for s in segs)
    for drop in ('finals', 'pod', 'slack', 'lifetime', 'records'):   # the records card is the last extra to go
        if total() <= BUDGET:
            break
        segs[:] = [s for s in segs if s['type'] != drop]
    have = {x['type'] for x in segs}   # the opener only teases cards that are still in
    segs[0]['rundown'] = [x for x in segs[0]['rundown'] if not (x['k'] == 'Record' and 'records' not in have)]
    for s_ in segs:
        while total() > BUDGET and s_['type'] == 'clips' and not s_.get('turn') and s_['want'] > 2:
            s_['want'] -= 1
    # ---- the running order: the week's action, what it did to the race, then league life, then history and what is next
    ORDER = ['intro', 'clips', 'game', 'finals', 'race', 'clinch', 'trades', 'slack', 'pod', 'shotguns', 'records', 'lifetime', 'coming']
    segs.sort(key=lambda x: ORDER.index(x['type']) if x['type'] in ORDER else len(ORDER))   # stable: ties keep their order
    for i, s in enumerate(segs):
        s['id'] = i

    link = '%s/recap/?week=%d' % (SITE, week)
    return {'schema': 1, 'season': season, 'week': week, 'seconds': total(), 'segments': segs, 'link': link,
            'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


def readiness(week, src):
    """What the recap for `week` is still waiting for: the tools it draws on update on their own schedules, and a recap built before they catch up to the
    week's end shows old career standings and records. Returns a list of plain-words reasons; empty means every source has the week."""
    waiting = []
    season = (load('league.json') or {}).get('season')

    def has(label, fn):
        try:
            ok, got = fn()
        except Exception as e:
            waiting.append('%s (could not be read: %s)' % (label, str(e)[:60])); return
        if not ok:
            waiting.append('%s (through week %s, needs %d)' % (label, got, week))
    hist = bf.source(src, 'SleeperLiveRumbles', 'rumbles_history.json')
    done = [int(w) for w in hist.get('weeks_completed', [])]
    has('Rumble Central results', lambda: (week in done, max(done) if done else 0))

    def lifetime():
        rows = bf.source(src, 'sleepersheet', 'data/standings.json')['seasons']
        wp = next((x.get('weeks_played', 0) for x in rows if x.get('season') == season), 0)
        return wp >= week, wp
    has('Lifetime standings', lifetime)

    def record_book():
        facts = json.loads(text_source(src, 'Recordbook', 'data/cache/facts.json'))['weeks']
        got = max([int(k.split('-')[1]) for k in facts if k.startswith('%s-' % season)] or [0])
        return ('%s-%d' % (season, week)) in facts, got
    has('Record Book', record_book)
    def top_plays():
        wks = (load('data/topplays.json') or {}).get('weeks') or {}
        return str(week) in wks, max([int(w) for w in wks] or [0])
    has('Top plays', top_plays)
    has('Shotguns', lambda: ((load('shotguns.json') or {}).get('throughWeek', 0) >= week, (load('shotguns.json') or {}).get('throughWeek', 0)))
    return waiting


def pod_only(week, src, asof):
    """Only the podcast quote (data/recap_pod.json), from the transcript in $RECAP_TRANSCRIPT; the recap itself is left alone (it is published by the feed
    job once every source has the week). Used by tools/pod_local.py."""
    hist = bf.source(src, 'SleeperLiveRumbles', 'rumbles_history.json')
    names = {r['manager'] for r in hist['standings']}
    plays = sorted([p for p in ((load('data/topplays.json') or {}).get('weeks') or {}).get(str(week), []) if p.get('clip')], key=lambda p: -p['swing'])[:6]
    card = pod_card(load('podcast.json') or {}, names, plays, asof, transcript=json.load(open(os.environ['RECAP_TRANSCRIPT'], encoding='utf-8')))
    print('pod card: %s' % ('quote at %d:%02d' % (card['at'] // 60, card['at'] % 60) if card else 'none (the captions do not name two of this week\'s managers or players)'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pod-only', action='store_true', help='only refresh the podcast quote from $RECAP_TRANSCRIPT')
    ap.add_argument('--force', action='store_true', help='build even if a source has not caught up to the week yet')
    ap.add_argument('--week', type=int)
    ap.add_argument('--src')
    ap.add_argument('--asof', help='YYYY-MM-DD, the day the recap is for (default today); the records window is the 8 days before it')
    args = ap.parse_args()
    asof = dt.date.fromisoformat(args.asof) if args.asof else dt.date.today()
    week = args.week
    if not week:
        hist = bf.source(args.src, 'SleeperLiveRumbles', 'rumbles_history.json')
        wc = hist.get('weeks_completed')   # Rumble Central's history lists the finished weeks ([1, 2, ... 10]); an older file may hold a count
        week = int(max(wc) if isinstance(wc, list) and wc else wc or max(int(w) for w in hist['weekly']))
    if args.pod_only:
        pod_only(week, args.src, asof); return
    status_path = os.path.join(HUB, 'data', 'recap_status.json')
    if not args.week and not args.force:   # the automatic path only publishes a week once every tool it draws on has that week
        waiting = readiness(week, args.src)
        status = {'week': week, 'ready': not waiting, 'waiting': waiting}
        if load('data/recap_status.json') != status:
            json.dump(status, open(status_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        if waiting:
            cur = load('data/recap.json') or {}
            if cur and int(cur.get('week', 0)) < week and os.path.exists(os.path.join(HUB, 'data', 'recap.json')):   # no recap is better than last week's
                os.remove(os.path.join(HUB, 'data', 'recap.json'))
            print('week %d recap is not ready yet (nothing is published until it is); waiting on: %s' % (week, '; '.join(waiting)))
            return
    out = build(week, args.src, asof)
    for name in ('recap.json', 'recap_%d.json' % week):
        with open(os.path.join(HUB, 'data', name), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print('week %d: %d segments, %ds' % (week, len(out['segments']), out['seconds']))


if __name__ == '__main__':
    main()
