#!/usr/bin/env python3
"""Builds the hub's Home data from the tools' public data and the Sleeper league settings:

    feed.json    top 3 matchups (Rumble Central's own ranking, via data/matchups.json) / trades / waiver claims / free-agent pickups of the season, each linking into its tool
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
def top_matchups(season):
    """The season's best matchups by Rumble Central's own ranking (wpInterest: closeness, lead changes, late comebacks, one big swing,
    and a 1.25x boost for head-to-heads). The page computes it from its win-probability model; tools/build_matchups.py reads each finished
    week's scores from the real page into data/matchups.json, and this takes the top 3 across weeks."""
    c = json.load(open(os.path.join(HUB, 'data', 'matchups.json'), encoding='utf-8'))
    if c.get('season') != season:
        return []
    rows = sorted(((int(w), r) for w, lst in c['weeks'].items() for r in lst), key=lambda x: -x[1]['it'])
    out = []
    for i, (w, r) in enumerate(rows[:3], 1):
        pa, pb = (float(x) for x in re.findall(r'\d+\.\d+', r['hl'])[:2])
        n = r['flips']
        out.append({'rank': i, 'title': '%s %.1f \u2013 %.1f %s' % (r['names'][0], pa, pb, r['names'][1]),
                    'sub': 'Week %d \u00b7 %s \u00b7 %d lead change%s' % (w, 'H2H' if r['h2h'] else 'vs. field', n, '' if n == 1 else 's'),
                    'managers': list(r['names'][:2]),
                    'href': '/SleeperLiveRumbles/rumbles.html?season=%s&wp=%s' % (season, r['best'])})
    return out


# ---------------------------------------------------------------- trades
def top_trades(data, season):
    """Biggest trades of the season by total value moved. Winner = who came out ahead on trade value, as the Trade Network
    scores it (value received minus value given); every player on both sides is listed."""
    ts = sorted([t for t in data['trades'] if t['s'] == season], key=lambda t: -(t.get('tv') or 0))
    out = []
    for i, t in enumerate(ts[:3], 1):
        net = (t.get('vb') or 0) - (t.get('va') or 0)             # > 0: A received more value than A gave
        winner = t['a'] if net > 0.05 else t['b'] if net < -0.05 else None
        out.append({'rank': i, 'title': '%s \u21c4 %s' % (t['a'], t['b']), 'sub': 'Week %d' % t['w'], 'managers': [t['a'], t['b']],
                    'winner': winner, 'edge': round(abs(net), 1),
                    'gets': [{'m': t['a'], 'players': [short_player(x['n']) for x in t['bg']]},     # A receives what B gave
                             {'m': t['b'], 'players': [short_player(x['n']) for x in t['ag']]}],
                    'href': '/SleeperTradeNodes/?season=%d&manager=%s' % (season, urllib.request.quote(winner or t['a']))})
    return out


# ---------------------------------------------------------------- pickups
def top_adds(data, season, ty):
    """Best pickups of the season by points above replacement while started (the FAB tool's default yardstick)."""
    rows = sorted([a for a in data['adds'] if a['s'] == season and a['ty'] == ty and (a.get('par') or 0) > 0], key=lambda a: -a['par'])
    out = []
    for i, a in enumerate(rows[:3], 1):
        bid = ' · $%d' % a['b'] if ty == 'W' and a.get('b') else ''
        out.append({'rank': i, 'title': '%s · %s' % (a['pl'], a['m']), 'sub': '+%.0f PAR%s · Wk %d' % (a['par'], bid, a['w']), 'managers': [a['m']],
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


def build_managers(hist, league_id, season):
    """The people in the league this season: name (as every tool spells it), roster and Sleeper user. Feeds the 'Who are you?' picker."""
    users = {u['user_id']: u for u in fetch('%s/league/%s/users' % (SLEEPER, league_id))}
    owners = {int(r['roster_id']): r.get('owner_id') for r in fetch('%s/league/%s/rosters' % (SLEEPER, league_id))}
    out = []
    for r in sorted(hist['standings'], key=lambda r: r['manager'].lower()):
        uid = owners.get(int(r['roster_id']))
        out.append({'id': re.sub(r'[^a-z0-9]+', '-', r['manager'].lower()).strip('-'), 'name': r['manager'], 'roster_id': int(r['roster_id']),
                    'sleeper_user_id': uid, 'sleeper_name': (users.get(uid) or {}).get('display_name'), 'aliases': []})
    return {'schema': 1, 'season': season, 'managers': out}


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
    standings, managers = [], None
    try:
        hist = source(args.src, 'SleeperLiveRumbles', 'rumbles_history.json')
        standings = [{'m': r['manager'], 'rank': r['rank'], 'rumbles': r['rumbles']} for r in hist['standings']]
        managers = build_managers(hist, league_id, season)
    except Exception as e:
        print('standings: %s' % e, file=sys.stderr)
    sections = []
    try:
        items = top_matchups(season)
        if items:
            sections.append({'id': 'matchups', 'title': 'Matchups', 'items': items})
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
    feed = {'schema': 1, 'season': season, 'sections': sections, 'standings': standings or old_feed.get('standings', []), 'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}

    def write(name, obj):   # only touch the file when the content (ignoring the timestamp) changed, so the repo isn't committed to every hour
        path = os.path.join(HUB, name)
        strip = lambda o: {k: v for k, v in o.items() if k != 'generatedAt'}
        if os.path.exists(path) and strip(json.load(open(path))) == strip(obj):
            print(name, 'unchanged'); return
        json.dump(obj, open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); open(path, 'a').write('\n'); print(name, 'written')
    write('league.json', lj)
    if managers:
        write('managers.json', managers)
    write('feed.json', feed)


if __name__ == '__main__':
    main()
