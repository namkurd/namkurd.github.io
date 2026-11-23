#!/usr/bin/env python3
"""Builds the weekly recap that /recap plays (data/recap.json and data/recap_<week>.json).

    python3 tools/build_recap.py                      # the last finished week, tools read from raw.githubusercontent.com
    python3 tools/build_recap.py --week 10            # a specific week
    python3 tools/build_recap.py --src /path          # sibling checkouts: /path/<Repo>/<file> (for testing)

The page is a short sequence of segments (cards and embedded clips). Which ones appear, how many, in what order and for how long is decided
here from what actually happened that week, so a wild week runs long and a quiet one is shorter. Everything comes from files the hub already
publishes; no Slack text is ever written to the repo (the Slack post adds a "comment of the week" at post time, see tools/recap_slack.py).
"""
import argparse, datetime as dt, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_feed as bf   # play_title / play_sub / fantasy / source / fetch

HUB = bf.HUB
BUDGET = 150          # seconds, the page never runs longer
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
def play_segment(p, kind, label):
    fa = bf.fantasy(p)
    return {'type': 'play', 'kind': kind, 'label': label, 'title': bf.play_title(p['who'], p['label'], p.get('sid'), p.get('stk'), p.get('slab')),
            'sub': bf.play_sub(p), 'by': p.get('by'), 'a': p['a'], 'b': p['b'], 'pts': p.get('tot') if p.get('tot') is not None else p.get('pts'),
            'from': pct(p.get('from')), 'to': pct(p.get('to')), 'swing': round(p['swing'] * 100), 'clip': p['clip'], **({'alt': p['alt']} if p.get('alt') else {}),
            'et': p.get('et'), 'sit': p.get('sit'), **({'fant': fa} if fa else {}),
            'href': 'https://www.youtube.com/watch?v=%s&t=%ds' % (p['clip']['id'], int(p['clip']['s'])),
            'replay': '/SleeperLiveRumbles/rumbles.html?wp=%d.%s.%s%s' % (p['week'], p.get('aid'), p.get('bid'), '&t=%d' % p['rt'] if p.get('rt') is not None else '')}


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

    # ---- the story of the week decides the opening line
    best_play = plays[0] if plays else None
    close = min(games, key=lambda g: g['margin']) if games else None
    wild = max(games, key=lambda g: (g['flips'], g['it'])) if games else None
    top_score = max(weekly.items(), key=lambda kv: kv[1]['points']) if weekly else None
    low_score = min(weekly.items(), key=lambda kv: kv[1]['points']) if weekly else None
    big_rumble = max(weekly.items(), key=lambda kv: kv[1].get('rumbles', 0)) if weekly else None
    intro = {'type': 'intro', 'dur': 5, 'week': week, 'season': season, 'title': 'Week %d recap' % week, 'stats': []}
    if top_score:
        intro['stats'].append({'k': 'High score', 'v': '%.1f' % top_score[1]['points'], 'm': names[int(top_score[0])]})
    if big_rumble:
        intro['stats'].append({'k': 'Most Rumbles', 'v': str(big_rumble[1].get('rumbles', 0)), 'm': names[int(big_rumble[0])]})
    if close:
        intro['stats'].append({'k': 'Closest game', 'v': '%.1f' % close['margin'], 'm': '%s over %s' % (close['w'], close['l'])})
    if best_play:
        intro['hook'] = 'Biggest swing: %s, %d%% → %d%%' % (bf.play_title(best_play['who'], best_play['label'], best_play.get('sid'), best_play.get('stk'), best_play.get('slab')),
                                                               pct(best_play.get('from')) or 0, pct(best_play.get('to')) or 0)
    segs.append(intro)

    # ---- plays: 3 to 4 clips, countdown to the biggest, never more than two from one matchup
    picks, per = [], {}
    for p in plays:
        key = tuple(sorted([p['a'], p['b']]))
        if per.get(key, 0) >= 2 or p['clip']['id'] in used:
            continue
        if len(picks) >= 3 and p['swing'] < 0.12:
            break
        picks.append(p); used.add(p['clip']['id']); per[key] = per.get(key, 0) + 1
        if len(picks) == 4:
            break
    # the turning point of the wildest real game is a segment of its own, so keep it out of the countdown
    turning = None
    if wild and wild['flips'] >= 2:
        pool = [p for p in plays if {p['a'], p['b']} == {wild['w'], wild['l']} and p['clip']['id'] not in used]
        if pool:
            turning = pool[0]
            used.add(turning['clip']['id'])
    n = len(picks)
    for i, p in enumerate(reversed(picks)):
        rank = n - i
        s = play_segment(p, 'top', '#%d play of the week' % rank)
        s['dur'] = 16 if rank == 1 else 13
        segs.append(s)

    # ---- the game of the week: the closest real game, or the one that traded the lead most
    if games:
        g = close if close['margin'] <= 8 else wild
        why = ('Decided by %.1f' % g['margin']) if g is close else ('%d lead changes' % g['flips'])
        segs.append({'type': 'game', 'dur': 8, 'title': 'Game of the week', 'why': why, 'w': g['w'], 'l': g['l'], 'ws': g['ws'], 'ls': g['ls'], 'flips': g['flips'],
                     'others': [x for x in sorted(games, key=lambda x: x['margin']) if x is not g][:4]})
    if turning:
        s = play_segment(turning, 'turn', 'Turning point')
        s['dur'] = 14
        s['why'] = '%s vs %s · %d lead changes' % (wild['w'], wild['l'], wild['flips'])
        segs.append(s)

    # ---- shotguns that week
    shots = []
    for m in (load('shotguns.json') or {}).get('managers', []):
        for sh in m.get('shots', []):
            if sh.get('week') == week:
                shots.append({'m': m['name'], 'player': sh.get('full') or sh.get('player'), 'pos': sh.get('pos')})
    if shots:
        segs.append({'type': 'shotguns', 'dur': 6 if len(shots) < 3 else 8, 'title': 'Shotgun watch', 'items': shots})

    # ---- records broken that week (the Record Book's change log)
    rec, since = [], (asof - dt.timedelta(days=8)).isoformat()
    path = os.path.join(src, 'Recordbook', 'data', 'changelog.jsonl') if src else None
    lines = []
    try:
        if path:
            lines = open(path, encoding='utf-8').read().splitlines()
        else:
            import urllib.request
            req = urllib.request.Request(bf.RAW.format(repo='Recordbook', path='data/changelog.jsonl'), headers={'User-Agent': 'dtf-club-hub'})
            lines = urllib.request.urlopen(req, timeout=60).read().decode('utf-8').splitlines()
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
        LM = [('rumble_rank', 'Rumbles'), ('h2h_w_rank', 'H2H wins'), ('pf_rank', 'Points for'), ('field_rank', 'Vs. field record'), ('field_pct_rank', 'Vs. field %')]
        for r in bf.source(src, 'sleepersheet', 'data/standings.json')['all_time']['rows']:
            if r['name'] not in set(names.values()):
                continue
            mv = [{'m': r['name'], 'metric': lab, 'rank': r[k], 'delta': r[k + '_delta']} for k, lab in LM if r.get(k + '_delta')]
            if len(mv) > 1 and mv[-1]['metric'] == 'Vs. field %' and mv[-2]['delta'] == mv[-1]['delta']:
                mv.pop()   # the same move twice (record and percentage)
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
    segs.append({'type': 'standings', 'dur': 12 if moved >= 4 or big >= 2 else 9, 'title': 'Standings after week %d' % week, 'rows': st})

    # ---- outro: the next key date and the podcast
    lg = load('league.json') or {}
    today = asof
    nxt = None
    for d in lg.get('keyDates') or []:
        days = (dt.date.fromisoformat(d['date']) - today).days
        if days >= 0 and (nxt is None or days < nxt['days']):
            nxt = {'label': d['label'], 'date': d['date'], 'days': days}
    pod = load('podcast.json') or {}
    outro = {'type': 'outro', 'dur': 6, 'title': 'Next up', 'next': nxt, 'week': week + 1,
             **({'pod': {'title': pod.get('title'), 'url': pod.get('url')}} if pod.get('url') else {})}
    segs.append(outro)

    # ---- trim to the budget: drop the least important extras first
    def total():
        return sum(s['dur'] for s in segs)
    for drop in ('shotguns', 'records', 'game'):
        if total() <= BUDGET:
            break
        segs[:] = [s for s in segs if s['type'] != drop]
    while total() > BUDGET:
        tops = [s for s in segs if s.get('kind') == 'top']
        if len(tops) <= 2:
            break
        segs.remove(tops[0])   # the smallest of the countdown
    for i, s in enumerate(segs):
        s['id'] = i

    link = '%s/recap/?week=%d' % (SITE, week)
    lines = ['*Week %d recap* — %d seconds, tap to watch (clips play right in the page): %s' % (week, total(), link)]
    if best_play:
        lines.append('• Play of the week: %s (%s)' % (bf.play_title(best_play['who'], best_play['label'], best_play.get('sid'), best_play.get('stk'), best_play.get('slab')), bf.play_sub(best_play)))
    if close:
        lines.append('• Closest game: %s over %s by %.1f' % (close['w'], close['l'], close['margin']))
    if rec:
        lines.append('• New record: %s — %s (%s)' % (rec[0]['name'], rec[0]['new'], rec[0]['holder']))
    if life:
        x = life[0]
        lines.append('\u2022 Lifetime: %s %s %d spot%s in all-time %s rank (now #%d)' % (x['m'], 'up' if x['delta'] > 0 else 'down', abs(x['delta']), '' if abs(x['delta']) == 1 else 's', x['metric'], x['rank']))
    movers = sorted([r for r in st if r['rank'] != r['prev']], key=lambda r: -abs(r['prev'] - r['rank']))
    if movers:
        r = movers[0]
        lines.append('• Biggest mover: %s %s to #%d' % (r['m'], 'up' if r['rank'] < r['prev'] else 'down', r['rank']))
    return {'schema': 1, 'season': season, 'week': week, 'seconds': total(), 'segments': segs, 'slack': '\n'.join(lines), 'link': link,
            'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--week', type=int)
    ap.add_argument('--src')
    ap.add_argument('--asof', help='YYYY-MM-DD, the day the recap is for (default today); the records window is the 8 days before it')
    args = ap.parse_args()
    asof = dt.date.fromisoformat(args.asof) if args.asof else dt.date.today()
    week = args.week
    if not week:
        hist = bf.source(args.src, 'SleeperLiveRumbles', 'rumbles_history.json')
        week = int(hist.get('weeks_completed') or max(int(w) for w in hist['weekly']))
    out = build(week, args.src, asof)
    for name in ('recap.json', 'recap_%d.json' % week):
        with open(os.path.join(HUB, 'data', name), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print('week %d: %d segments, %ds' % (week, len(out['segments']), out['seconds']))
    print(out['slack'])


if __name__ == '__main__':
    main()
