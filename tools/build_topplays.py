#!/usr/bin/env python3
"""Collects each finished week's biggest head-to-head win-probability plays (with their video clips) into data/topplays.json.

Rumble Central's win-probability model and its play-by-play clips live in the page, so this opens the real page in a headless
browser and reads window.__dtfTop(week) (every head-to-head's marked plays: swing, player, play, the clip). Only plays that have an
embeddable clip are kept; YouTube's oEmbed endpoint says whether a video allows embedding. build_feed.py takes the season's top plays.

    python3 tools/build_topplays.py --check     # needed=true/false: is a finished week missing from the cache?
    python3 tools/build_topplays.py             # scrapes only the missing weeks (finished weeks never change)
    python3 tools/build_topplays.py --season 2024   # an archived season: reads Rumble Central's ?season=2024 archive into data/topplays_2024.json (once)
"""
import argparse, datetime as dt, hashlib, json, os, re, sys, urllib.error, urllib.parse, urllib.request
PENDING_HASH = {}   # week -> hash of its wp_clips file, set by plan()

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HUB, 'data', 'topplays.json')   # the current season; an archived season is data/topplays_<year>.json (see main)
NOT_A_PLAY = re.compile(r'stat correction|scoring adjustment|allowed', re.I)   # a correction or a defense's points-allowed line is not a play
BASE = 'https://namkurd.github.io/SleeperLiveRumbles/rumbles.html'
KEEP_RULE = b'|keep:30+3def'   # bump when what is kept per week changes
KEEP = 30   # plays kept per week: the page checks in the viewer's browser which clips embed, so there must be spares


def keep_plays(plays):
    """The week's best plays (KEEP of them), plus up to three team-defense plays when they fall outside that: a defense's swings are small, and the
    recap shows one defensive play of the week."""
    isdef = lambda x: bool(re.match(r'^[A-Z]{2,4}$', x.get('sid') or ''))
    keep = plays[:KEEP]
    need = 3 - sum(1 for x in keep if isdef(x))
    return keep + ([x for x in plays[KEEP:] if isdef(x)][:need] if need > 0 else [])


def get_json(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'dtf-club-hub'}), timeout=60))


def load_cache(season, path=None):
    try:
        c = json.load(open(path or CACHE, encoding='utf-8'))
        if c.get('season') == season:
            return c
    except Exception:
        pass
    return {'schema': 1, 'season': season, 'weeks': {}, 'embed': {}}


def plan(base, root=None, path=None):
    root = root or base.rsplit('/', 1)[0]
    hist = get_json(root + '/rumbles_history.json')
    season = int(hist['season'])
    try:
        timeline = set(get_json(root + '/wp_timeline/index.json').get('weeks', []))
    except Exception:
        timeline = set()
    done = {int(w) for w in hist.get('weeks_completed', [])}
    cache = load_cache(season, path)
    have = set(int(w) for w in cache['weeks'])
    todo = []
    for w in sorted(done & timeline):
        try:
            raw = urllib.request.urlopen(urllib.request.Request('%s/wp_clips/week_%d.json' % (root, w), headers={'User-Agent': 'dtf-club-hub'}), timeout=60).read()   # a week's plays are only cached once its clips exist
        except Exception:
            continue
        h = hashlib.md5(raw + KEEP_RULE).hexdigest()[:12]   # the keep rule is part of the stamp: changing it re-reads the weeks once
        PENDING_HASH[w] = h
        if w not in have or cache.get('clipsHash', {}).get(str(w)) != h:   # new week, or its clips changed (the audit drops interviews and videos taken down)
            todo.append(w)
    return season, todo


def add_scores(cache, root):
    """Each play also carries the final fantasy score of its head-to-head (pa = the first-named manager a, pb = b), from Rumble Central's rumbles_history.json.
    Returns True when something was filled in."""
    need = [p for w in cache['weeks'].values() for p in w if 'pa' not in p and p.get('aid') is not None]
    if not need:
        return False
    try:
        weekly = get_json(root + '/rumbles_history.json').get('weekly', {})
    except Exception as e:
        print('scores: %s' % e, file=sys.stderr); return False
    done = False
    for p in need:
        wk = weekly.get(str(p['week']), {})
        a, b = wk.get(str(p['aid'])), wk.get(str(p['bid']))
        if a and b and a.get('points') is not None and b.get('points') is not None:
            p['pa'], p['pb'] = round(float(a['points']), 2), round(float(b['points']), 2); done = True
    return done


def embeddable(vid, memo):
    """True/False from YouTube's oEmbed (401/403 = owner disabled embedding, 404 = gone). Network trouble counts as OK."""
    if vid in memo:
        return memo[vid]
    url = 'https://www.youtube.com/oembed?format=json&url=' + urllib.parse.quote('https://www.youtube.com/watch?v=' + vid, safe='')
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'dtf-club-hub'}), timeout=20); ok = True
    except urllib.error.HTTPError as e:
        ok = e.code not in (401, 403, 404)
    except Exception:
        return True   # unknown: don't remember it
    memo[vid] = ok
    return ok


def scrape(base, season, weeks, path=None):
    from playwright.sync_api import sync_playwright
    cache = load_cache(season, path)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--no-sandbox'], **({'executable_path': os.environ['CHROME_PATH']} if os.environ.get('CHROME_PATH') else {}))
        page = browser.new_page(viewport={'width': 900, 'height': 900})
        page.goto(base, wait_until='load')
        page.wait_for_function("() => typeof window.__dtfTop === 'function'", timeout=60000)
        page.wait_for_timeout(4000)
        for w in weeks:
            res = None
            for _ in range(80):   # the page loads the week's lineups, play-by-play and clips on first ask
                res = page.evaluate('(w) => window.__dtfTop(w)', w)
                if not res['wait']:
                    break
                page.wait_for_timeout(500)
            if not res or res['wait'] or not res['plays']:
                print('week %d: not ready' % w, file=sys.stderr); continue
            plays = [x for x in res['plays'] if x.get('clip') and x['clip'].get('id') and not NOT_A_PLAY.search(x.get('label') or '')]   # whether a clip embeds is checked in the viewer's browser (an NFL-owned video can refuse only some sites)
            plays.sort(key=lambda x: -abs(x['d']))
            cache.setdefault('clipsHash', {})[str(w)] = PENDING_HASH.get(w)
            cache['weeks'][str(w)] = [{'week': w, 'a': x['a'], 'b': x['b'], 'who': x['who'], 'label': x['label'], 'swing': round(abs(x['d']), 3), 'by': x.get('by'), 'help': bool(x.get('help', True)), 'sid': x.get('sid'), 'tot': x.get('tot'), 'pts': x.get('pts'), **({'stk': x['stk'], 'slab': x['slab']} if x.get('stk') and x.get('slab') else {}), 'aid': x['arid'], 'bid': x['brid'], 'rt': x.get('rt'), 'et': x.get('et'), **({'sit': x['sit']} if x.get('sit') else {}), 'from': round((x['p0'] if x['d'] >= 0 else 1 - x['p0']) * 100), 'to': round((x['p1'] if x['d'] >= 0 else 1 - x['p1']) * 100),
                                       'clip': {'id': x['clip']['id'], 's': x['clip']['s'], 'e': x['clip']['e']},
                                       **({'alt': {'id': x['clip']['x']['id'], 's': x['clip']['x']['s'], 'e': x['clip']['x']['e']}} if x['clip'].get('x') else {})} for x in keep_plays(plays)]
            print('week %d: %d plays with clips, best %s' % (w, len(plays), plays[0]['who'] + ' ' + plays[0]['label'] if plays else '-'))
        browser.close()
    return cache


def run_one(args, year=None):
    """One season: the live page and the current cache, or (year) that season's archive and its own cache file."""
    root = args.base.rsplit('/', 1)[0]
    data_root = root + ('/seasons/%d' % year if year else '')
    page_url = args.base + ('?season=%d' % year if year else '')
    path = os.path.join(HUB, 'data', 'topplays_%d.json' % year) if year else CACHE
    if args.scores:
        season = int(get_json(data_root + '/rumbles_history.json')['season']); cache = load_cache(season, path)
        if add_scores(cache, data_root):
            cache['updatedAt'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            json.dump(cache, open(path, 'w', encoding='utf-8'), separators=(',', ':'), ensure_ascii=False); open(path, 'a').write('\n'); print('scores added')
        else:
            print('no scores to add')
        return
    season, missing = plan(args.base, data_root, path)
    if args.check:
        out = 'true' if missing else 'false'
        print('needed=' + out)
        if os.environ.get('GITHUB_OUTPUT'):
            open(os.environ['GITHUB_OUTPUT'], 'a').write('needed=%s\n' % out)
        return
    if not missing:
        print('%s: nothing to scrape' % (year or 'current season')); return
    cache = scrape(page_url, season, missing, path)
    add_scores(cache, data_root)
    cache['updatedAt'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(cache, open(path, 'w', encoding='utf-8'), separators=(',', ':'), ensure_ascii=False); open(path, 'a').write('\n')
    print('wrote', path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=BASE)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--season', type=int, help='an archived season (reads its ?season= archive into data/topplays_<year>.json)')
    ap.add_argument('--archives', action='store_true', help='every archived season Rumble Central has (seasons/index.json)')
    ap.add_argument('--scores', action='store_true', help='only fill in the fantasy scores of plays already cached (no browser)')
    args = ap.parse_args()
    if args.archives:
        root = args.base.rsplit('/', 1)[0]
        idx = get_json(root + '/seasons/index.json')
        years = sorted(int(x['season'] if isinstance(x, dict) else x) for x in (idx.get('seasons') or []))
        for y in years:
            run_one(args, y)
        return
    run_one(args, args.season)


if __name__ == '__main__':
    main()
