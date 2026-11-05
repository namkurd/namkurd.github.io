#!/usr/bin/env python3
"""Builds the hub's Home data from the tools' public data and the Sleeper league settings:

    feed.json    top 3 matchups / trades / waiver claims / free-agent pickups of the season, each linking into its tool
    league.json  season, week and key dates (trade deadline, playoffs, championship) taken from the Sleeper league settings

    python3 tools/build_feed.py                 # reads the tools from raw.githubusercontent.com (main)
    python3 tools/build_feed.py --src /path     # reads sibling checkouts: /path/<Repo>/<file>  (for testing)

Nothing in the tools has to change: this only reads files they already publish. If a source can't be read the
previous output is kept, so a bad hour never blanks the Home screen.
"""
import argparse, datetime as dt, json, os, re, sys, urllib.request

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = 'https://raw.githubusercontent.com/namkurd/{repo}/main/{path}'
SLEEPER = 'https://api.sleeper.app/v1'
DEFAULT_LEAGUE = '1389416556617801728'   # only a fallback: league.json's league_id wins, and that is the one place to change it


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'dtf-club-hub'})
    return json.load(urllib.request.urlopen(req, timeout=60))


def source(src, repo, path):
    if src:
        return json.load(open(os.path.join(src, repo, path), encoding='utf-8'))
    return fetch(RAW.format(repo=repo, path=path))


def prev(name):
    try:
        return json.load(open(os.path.join(HUB, name), encoding='utf-8'))
    except Exception:
        return {}


def short_player(n):
    """'RB Tyler Allgeier - ARI' -> 'T. Allgeier'"""
    n = re.sub(r'^(QB|RB|WR|TE|K|DEF|DST)\s+', '', n or '')
    n = re.sub(r'\s+-\s+[A-Z]{2,3}$', '', n).strip()
    parts = n.split()
    if len(parts) >= 2 and not re.match(r'^(Jr\.?|Sr\.?|II|III|IV)$', parts[-1]):
        return parts[0][0] + '. ' + ' '.join(parts[1:])
    return n


# ---------------------------------------------------------------- matchups
def top_matchups(hist, timeline_weeks, season):
    """Most entertaining head-to-heads of the season: lots of points, decided narrowly.
    score = combined points - 2 x margin. Only weeks Rumble Central has a replay for, so every row opens a replay."""
    names = {int(s['roster_id']): s['manager'] for s in hist['standings']}
    seen, games = set(), []
    for wk, teams in hist['weekly'].items():
        w = int(wk)
        for rid, g in teams.items():
            rid, opp = int(rid), int(g['opponent_roster_id'])
            key = (w, min(rid, opp), max(rid, opp))
            if key in seen or w not in timeline_weeks:
                continue
            seen.add(key)
            a, b = g['points'], g['opponent_points']
            win, lose = (rid, opp) if a >= b else (opp, rid)
            pw, pl = max(a, b), min(a, b)
            games.append({'w': w, 'win': win, 'lose': lose, 'pw': pw, 'pl': pl, 'score': pw + pl - 2 * (pw - pl)})
    games.sort(key=lambda x: -x['score'])
    out = []
    for i, g in enumerate(games[:3], 1):
        out.append({'rank': i, 'title': '%s %.1f – %.1f %s' % (names.get(g['win'], '?'), g['pw'], g['pl'], names.get(g['lose'], '?')),
                    'sub': 'Week %d · %.0f pts combined' % (g['w'], g['pw'] + g['pl']),
                    'href': '/SleeperLiveRumbles/rumbles.html?season=%s&wp=%d.%d.%d' % (season, g['w'], g['win'], g['lose'])})
    return out


# ---------------------------------------------------------------- trades
def top_trades(data, season):
    """Biggest trades of the season by total value moved."""
    ts = sorted([t for t in data['trades'] if t['s'] == season], key=lambda t: -(t.get('tv') or 0))
    out = []
    for i, t in enumerate(ts[:3], 1):
        def side(assets):
            names = [short_player(x['n']) for x in assets]
            return (names[0] + (' +%d' % (len(names) - 1) if len(names) > 1 else '')) if names else '?'
        out.append({'rank': i, 'title': '%s ⇄ %s' % (t['a'], t['b']),
                    'sub': '%s ⇄ %s · Wk %d' % (side(t['ag']), side(t['bg']), t['w']),
                    'href': '/SleeperTradeNodes/?season=%d&manager=%s' % (season, urllib.request.quote(t['a']))})
    return out


# ---------------------------------------------------------------- pickups
def top_adds(data, season, ty):
    """Best pickups of the season by points above replacement while started (the FAB tool's default yardstick)."""
    rows = sorted([a for a in data['adds'] if a['s'] == season and a['ty'] == ty and (a.get('par') or 0) > 0], key=lambda a: -a['par'])
    out = []
    for i, a in enumerate(rows[:3], 1):
        bid = ' · $%d' % a['b'] if ty == 'W' and a.get('b') else ''
        out.append({'rank': i, 'title': '%s · %s' % (a['pl'], a['m']), 'sub': '+%.0f PAR%s · Wk %d' % (a['par'], bid, a['w']),
                    'href': '/FAB-Management/?season=%d&manager=%s' % (season, urllib.request.quote(a['m']))})
    return out


# ---------------------------------------------------------------- league settings / key dates
def key_dates(league, state):
    s = league.get('settings', {})
    start = dt.date.fromisoformat(state['season_start_date']) + dt.timedelta(days=1)   # the Thursday that opens Week 1

    def wk(n):
        return (start + dt.timedelta(days=7 * (n - 1))).isoformat()
    out = []
    if s.get('trade_deadline'):
        out.append({'id': 'trade-deadline', 'label': 'Trade deadline', 'week': s['trade_deadline'], 'date': wk(s['trade_deadline'])})
    pw = s.get('playoff_week_start')
    if pw:
        out.append({'id': 'playoffs', 'label': 'Playoffs begin', 'week': pw, 'date': wk(pw)})
        rounds = 3 if (s.get('playoff_teams') or 6) > 4 else 2   # 5-6 teams: a bye round, then three rounds
        out.append({'id': 'championship', 'label': 'Championship', 'week': pw + rounds - 1, 'date': wk(pw + rounds - 1)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', help='directory holding sibling checkouts of the tool repos')
    args = ap.parse_args()
    old_league, old_feed = prev('league.json'), prev('feed.json')
    league_id = old_league.get('league_id') or DEFAULT_LEAGUE
    try:
        state = fetch(SLEEPER + '/state/nfl')
        league = fetch('%s/league/%s' % (SLEEPER, league_id))
        season = int(league['season'])
        lj = {'schema': 1, 'name': league.get('name', 'DTF Club'), 'season': season, 'league_id': league_id, 'week': state.get('week'),
              'status': league.get('status'), 'keyDates': key_dates(league, state), 'slack': old_league.get('slack', 'https://dtf-club.slack.com/'),
              'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    except Exception as e:
        print('Sleeper unreachable (%s); keeping league.json' % e, file=sys.stderr)
        lj, season = old_league, int(old_league.get('season') or dt.date.today().year)
    sections = []
    try:
        hist = source(args.src, 'SleeperLiveRumbles', 'rumbles_history.json')
        tl = source(args.src, 'SleeperLiveRumbles', 'wp_timeline/index.json')
        sections.append({'id': 'matchups', 'title': 'Matchups', 'items': top_matchups(hist, set(tl.get('weeks', [])), season)})
    except Exception as e:
        print('matchups: %s' % e, file=sys.stderr)
    try:
        sections.append({'id': 'trades', 'title': 'Trades', 'items': top_trades(source(args.src, 'SleeperTradeNodes', 'data.json'), season)})
    except Exception as e:
        print('trades: %s' % e, file=sys.stderr)
    try:
        fab = source(args.src, 'FAB-Management', 'data.json')
        sections.append({'id': 'waivers', 'title': 'Waivers', 'items': top_adds(fab, season, 'W')})
        sections.append({'id': 'free-agents', 'title': 'Free agents', 'items': top_adds(fab, season, 'F')})
    except Exception as e:
        print('pickups: %s' % e, file=sys.stderr)
    have = {s['id'] for s in sections}
    for s in old_feed.get('sections', []):   # a source that failed this run keeps its last good section
        if s['id'] not in have:
            sections.append(s)
    order = ['matchups', 'trades', 'waivers', 'free-agents']
    sections.sort(key=lambda s: order.index(s['id']) if s['id'] in order else 99)
    feed = {'schema': 1, 'season': season, 'sections': sections, 'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}

    def write(name, obj):   # only touch the file when the content (ignoring the timestamp) changed, so the repo isn't committed to every hour
        path = os.path.join(HUB, name)
        strip = lambda o: {k: v for k, v in o.items() if k != 'generatedAt'}
        if os.path.exists(path) and strip(json.load(open(path))) == strip(obj):
            print(name, 'unchanged'); return
        json.dump(obj, open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); open(path, 'a').write('\n'); print(name, 'written')
    write('league.json', lj)
    write('feed.json', feed)


if __name__ == '__main__':
    main()
