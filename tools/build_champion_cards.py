#!/usr/bin/env python3
"""Builds champions/cards.json: for each champion and sacko, the Rumble Central lineup card of the finals week
(the season's last playoff week: 17 for 2021 on, 16 before) with the team's name, logo and regular-season record.

    python3 tools/build_champion_cards.py                # reads Rumble Central's data from GitHub
    python3 tools/build_champion_cards.py --src /path    # reads local checkouts: /path/SleeperLiveRumbles, /path/sleepersheet

Sources: SleeperLiveRumbles seasons/<year>/{rumbles_history,epa_weekly}.json (lineups, regular-season H2H record, Rumbles),
sleepersheet data/playoffs_history.json (which week was the final), and each season's Sleeper league (team name and avatar).
Run it again after a season's playoffs finish and a new row is added to champions/data.json.
"""
import argparse, json, os, sys, urllib.request

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = 'https://raw.githubusercontent.com/namkurd/{repo}/main/{path}'
SLEEPER = 'https://api.sleeper.app/v1'
SLOT = {'FLEX': 'FLX', 'SUPER_FLEX': 'SF', 'REC_FLEX': 'FLX', 'WRRB_FLEX': 'FLX'}


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'rumble-hub'}), timeout=60))


def src(base, repo, path):
    if base:
        return json.load(open(os.path.join(base, repo, path), encoding='utf-8'))
    return get(RAW.format(repo=repo, path=path))


def short(name, pos):
    if pos == 'DEF':
        return name.split()[-1] if name else 'DEF'
    parts = (name or '').split()
    return (parts[0][0] + '. ' + ' '.join(parts[1:])) if len(parts) >= 2 else name


def team(league_id, rid):
    users = {u['user_id']: u for u in get('%s/league/%s/users' % (SLEEPER, league_id))}
    r = next(x for x in get('%s/league/%s/rosters' % (SLEEPER, league_id)) if x['roster_id'] == rid)
    u = users.get(r.get('owner_id')) or {}
    md, rmd = u.get('metadata') or {}, r.get('metadata') or {}
    logo = rmd.get('avatar') or md.get('avatar') or ('https://sleepercdn.com/avatars/thumbs/%s' % u['avatar'] if u.get('avatar') else None)
    return (md.get('team_name') or u.get('display_name')), logo


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--src'); args = ap.parse_args()
    data = json.load(open(os.path.join(HUB, 'champions', 'data.json'), encoding='utf-8'))
    games = src(args.src, 'sleepersheet', 'data/playoffs_history.json')['games']
    final = {}
    for g in games:
        final[g['season']] = max(final.get(g['season'], 0), g['week'])
    out, old = {}, {}
    try:
        old = json.load(open(os.path.join(HUB, 'champions', 'cards.json'), encoding='utf-8'))
    except Exception:
        pass
    for s in sorted(data['seasons'], key=lambda s: s['season']):
        y = s['season']
        try:
            hist = src(args.src, 'SleeperLiveRumbles', 'seasons/%d/rumbles_history.json' % y)
            epa = src(args.src, 'SleeperLiveRumbles', 'seasons/%d/epa_weekly.json' % y)
        except Exception:
            continue   # no Rumble Central data for this season
        wk = final.get(y)
        if not wk or str(wk) not in epa['lineups']:
            continue
        rows = {r['manager']: r for r in hist['standings']}
        unnamed = [r for r in hist['standings'] if r['manager'].startswith('Roster ')]   # a seat Sleeper had no owner name for that year
        week = (hist.get('extra_weekly') or {}).get(str(wk)) or hist['weekly'].get(str(wk)) or {}
        by_name = {r['manager']: r['roster_id'] for r in hist['standings']}
        for kind in ('champion', 'sacko'):
            e = s.get(kind)
            if not e or (e['m'] not in rows and len(unnamed) != 1):
                continue
            r = rows.get(e['m']) or unnamed[0]; rid = r['roster_id']; lineup = epa['lineups'][str(wk)].get(str(rid))
            if not lineup:
                continue
            try:
                name, logo = team(hist['league_id'], rid)
                name = name if name and not name.startswith('Roster ') else None
            except Exception as ex:
                prev = (old.get(str(y)) or {}).get(kind) or {}
                name, logo = prev.get('team'), prev.get('logo'); print('team lookup failed for %s %s (%s); keeping the old one' % (y, kind, ex), file=sys.stderr)
            slots = [x for x in epa['slots'] if x != 'BN'][:len(lineup)]
            lines = []
            for i, (pid, pts) in enumerate(lineup):
                nm, pos = epa['names'].get(str(pid), [str(pid), ''])
                lines.append({'s': SLOT.get(slots[i], slots[i]) if i < len(slots) else pos, 'n': short(nm, pos), 'p': round(pts, 2)})
            link = None
            if kind == 'champion':   # the final: the champion against the closest loser (a 3-team final is two rows), as a Rumble Central ?wp=week.me.them link
                rivals = [g for g in games if g['season'] == y and g['week'] == wk and g['winner'] == e['m'] and g['loser'] in by_name]
                if rivals:
                    opp = by_name[max(rivals, key=lambda g: g['loser_score'])['loser']]
                    link = '/SleeperLiveRumbles/rumbles.html?season=%d&wp=%d.%d.%d' % (y, wk, rid, opp)
            elif (week.get(str(rid)) or {}).get('opponent_roster_id') is not None:   # the sacko's own finals-week game
                link = '/SleeperLiveRumbles/rumbles.html?season=%d&wp=%d.%d.%d' % (y, wk, rid, week[str(rid)]['opponent_roster_id'])
            out.setdefault(str(y), {})[kind] = {'m': e['m'], 'team': name, 'logo': logo, 'record': '%d-%d' % (r['h2h_w'], r['h2h_l']), 'week': wk,
                                                 'total': round(sum(l['p'] for l in lines), 2), 'rumbles': (week.get(str(rid)) or {}).get('rumbles'), 'lineup': lines, **({'link': link} if link else {})}
    json.dump({'schema': 1, 'note': 'Built by tools/build_champion_cards.py', 'seasons': out}, open(os.path.join(HUB, 'champions', 'cards.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    open(os.path.join(HUB, 'champions', 'cards.json'), 'a').write('\n')
    print('wrote cards for', {y: sorted(v) for y, v in out.items()})


if __name__ == '__main__':
    main()
