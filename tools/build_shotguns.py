#!/usr/bin/env python3
"""Builds shotguns.json: this season's Shotguns, by manager, for the Home screen.

A Shotgun is a score of 0 or less from a non-defense starter who took the field and was not ruled out in the game (the Record Book's definition).
Ruled out in his game means: a starting QB whose backup's points the league credited (Rumble Central's QB-injury adjustment, confirmed or likely), or
any starter Sleeper marked Out/IR/PUP before the 2nd half of his own game (Rumble Central's live_injury_captures.json, logged during games from week 9
on), or a hand entry in Rumble Central's injury_overrides.json. A ruling that came once the 2nd half had started still leaves it a Shotgun. The Record Book already
works them out for every finished week (data/cache/facts.json: per team, per week, `shot` = [[player id, points]]; names.json gives the
players), so this reads that cache instead of repeating the rules.

    python3 tools/build_shotguns.py                  # the Record Book's cache from raw.githubusercontent.com
    python3 tools/build_shotguns.py --src /path      # /path/Recordbook/data/cache/{facts,names}.json (for testing)

Who has served their punishment is kept in data/shotguns_done.json: {"keys": ["2026-8-4881-9", ...]} (season-week-player id-roster id).
Each Shotgun carries `done` from it; the Home screen does not show it yet.
If the cache can't be read the previous shotguns.json is kept.
"""
import argparse, datetime as dt, json, os, re, sys, urllib.request

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RB_RAW = 'https://raw.githubusercontent.com/namkurd/Recordbook/%s/data/cache/%s'
RB_BRANCH = 'claude/initial-build'      # the Record Book's published branch
RC_RAW = 'https://raw.githubusercontent.com/namkurd/SleeperLiveRumbles/main/%s'   # this season's QB-injury adjustments and in-game injury log


def load(path):
    return json.load(open(os.path.join(HUB, path), encoding='utf-8'))


def fetch(name, src):
    if src:
        return json.load(open(os.path.join(src, 'Recordbook', 'data', 'cache', name), encoding='utf-8'))
    req = urllib.request.Request(RB_RAW % (RB_BRANCH, name), headers={'User-Agent': 'dtf-club-hub'})
    return json.load(urllib.request.urlopen(req, timeout=60))


def ruled_out(history, captures=None, overrides=None):
    """{(week, roster id, player id)}: starters ruled out in their game this season (see the module doc)."""
    out = {(int(e['week']), int(e['roster_id']), str(e['injured_qb']['player_id'])) for e in (history or {}).get('qb_adjustments') or []
           if e.get('confidence') in ('confirmed', 'likely') and e.get('injured_qb')}
    for e in (captures or {}).get('captures') or []:           # logged during games; only a ruling before the 2nd half exempts
        if e.get('player') and not e.get('second_half_started'):
            out.add((int(e['week']), int(e['roster_id']), str(e['player']['player_id'])))
    for e in (overrides or {}).get('ruled_out') or []:         # hand entries always do
        out.add((int(e['week']), int(e['roster_id']), str(e['player_id'])))
    return out


def fetch_rc(name, src):
    if src:
        return json.load(open(os.path.join(src, 'SleeperLiveRumbles', name), encoding='utf-8'))
    req = urllib.request.Request(RC_RAW % name, headers={'User-Agent': 'dtf-club-hub'})
    return json.load(urllib.request.urlopen(req, timeout=60))


def short(name):
    parts = (name or '').split()
    return parts[0][0] + '. ' + ' '.join(parts[1:]) if len(parts) >= 2 else name or ''


def build(facts, names, managers, season, done, out_qbs=frozenset()):
    """-> shotguns.json content. managers: [{'name', 'roster_id', 'id'}]"""
    by_roster = {int(m['roster_id']): m for m in managers}
    rows = {rid: [] for rid in by_roster}
    through = 0
    for key, wk in facts['weeks'].items():
        s, w = (int(x) for x in key.split('-'))
        if s != season:
            continue
        through = max(through, w)
        for rid, t in wk['teams'].items():
            if int(rid) not in by_roster:
                continue
            for pid, pts in t.get('shot') or []:
                if pid == '0' or (len(pid) <= 3 and pid.isalpha()):        # an empty slot / a defense
                    continue
                if (w, int(rid), pid) in out_qbs:        # ruled out in his game: no Shotgun
                    continue
                nm, pos = (names.get(pid) or [pid, ''])[:2]
                k = '%d-%d-%s-%s' % (season, w, pid, rid)
                rows[int(rid)].append({'week': w, 'player': short(nm), 'full': nm, 'pos': pos, 'pts': round(float(pts), 2), 'key': k, 'done': k in done})
    out = []
    for rid, shots in rows.items():
        shots.sort(key=lambda x: (x['week'], x['player']))
        m = by_roster[rid]
        out.append({'id': m['id'], 'name': m['name'], 'count': len(shots), 'shots': shots})
    out.sort(key=lambda x: (-x['count'], x['name']))
    return {'schema': 1, 'season': season, 'throughWeek': through, 'total': sum(x['count'] for x in out), 'managers': out,
            'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--src'); args = ap.parse_args()
    try:
        league = load('league.json'); managers = load('managers.json')['managers']
        season = int(league.get('season') or load('managers.json')['season'])
        try:
            done = set(load('data/shotguns_done.json').get('keys') or [])
        except Exception:
            done = set()
        try:
            opt = lambda name: (lambda: fetch_rc(name, args.src))
            def soft(name):
                try: return fetch_rc(name, args.src)
                except Exception: return {}
            out_qbs = ruled_out(fetch_rc('rumbles_history.json', args.src), soft('live_injury_captures.json'), soft('injury_overrides.json'))
        except Exception as e:
            print('injury data unavailable (%s); counting every 0-or-less starter who played' % e, file=sys.stderr); out_qbs = frozenset()
        out = build(fetch('facts.json', args.src), fetch('names.json', args.src), managers, season, done, out_qbs)
    except Exception as e:
        print('shotguns: %s; keeping shotguns.json' % e, file=sys.stderr); return
    path = os.path.join(HUB, 'shotguns.json')
    try:
        old = json.load(open(path, encoding='utf-8'))
        strip = lambda o: {k: v for k, v in o.items() if k != 'generatedAt'}
        if strip(old) == strip(out):
            print('shotguns: no change'); return
    except Exception:
        pass
    json.dump(out, open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); open(path, 'a').write('\n')
    print('shotguns: %d this season, through week %d' % (out['total'], out['throughWeek']))


if __name__ == '__main__':
    main()
