#!/usr/bin/env python3
"""Collects each finished week's biggest head-to-head win-probability plays (with their video clips) into data/topplays.json.

Rumble Central's win-probability model and its play-by-play clips live in the page, so this opens the real page in a headless
browser and reads window.__dtfTop(week) (every head-to-head's marked plays: swing, player, play, the clip). Only plays that have an
embeddable clip are kept; YouTube's oEmbed endpoint says whether a video allows embedding. build_feed.py takes the season's top plays.

    python3 tools/build_topplays.py --check     # needed=true/false: is a finished week missing from the cache?
    python3 tools/build_topplays.py             # scrapes only the missing weeks (finished weeks never change)
"""
import argparse, datetime as dt, json, os, sys, urllib.error, urllib.parse, urllib.request

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HUB, 'data', 'topplays.json')
BASE = 'https://namkurd.github.io/SleeperLiveRumbles/rumbles.html'
KEEP = 12   # plays kept per week (the feed shows the season's best few)


def get_json(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'dtf-club-hub'}), timeout=60))


def load_cache(season):
    try:
        c = json.load(open(CACHE, encoding='utf-8'))
        if c.get('season') == season:
            return c
    except Exception:
        pass
    return {'schema': 1, 'season': season, 'weeks': {}, 'embed': {}}


def plan(base):
    root = base.rsplit('/', 1)[0]
    hist = get_json(root + '/rumbles_history.json')
    season = int(hist['season'])
    try:
        timeline = set(get_json(root + '/wp_timeline/index.json').get('weeks', []))
    except Exception:
        timeline = set()
    done = {int(w) for w in hist.get('weeks_completed', [])}
    have = set(int(w) for w in load_cache(season)['weeks'])
    todo = []
    for w in sorted((done & timeline) - have):
        try:
            get_json('%s/wp_clips/week_%d.json' % (root, w)); todo.append(w)   # a week's plays are only cached once its clips exist
        except Exception:
            pass
    return season, todo


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


def scrape(base, season, weeks):
    from playwright.sync_api import sync_playwright
    cache = load_cache(season)
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
            plays = [x for x in res['plays'] if x.get('clip') and x['clip'].get('id') and embeddable(x['clip']['id'], cache['embed'])]
            plays.sort(key=lambda x: -abs(x['d']))
            cache['weeks'][str(w)] = [{'week': w, 'a': x['a'], 'b': x['b'], 'who': x['who'], 'label': x['label'], 'swing': round(abs(x['d']), 3), 'from': round((x['p0'] if x['d'] >= 0 else 1 - x['p0']) * 100), 'to': round((x['p1'] if x['d'] >= 0 else 1 - x['p1']) * 100),
                                       'clip': {'id': x['clip']['id'], 's': x['clip']['s'], 'e': x['clip']['e']}} for x in plays[:KEEP]]
            print('week %d: %d plays with clips, best %s' % (w, len(plays), plays[0]['who'] + ' ' + plays[0]['label'] if plays else '-'))
        browser.close()
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=BASE)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    season, missing = plan(args.base)
    if args.check:
        out = 'true' if missing else 'false'
        print('needed=' + out)
        if os.environ.get('GITHUB_OUTPUT'):
            open(os.environ['GITHUB_OUTPUT'], 'a').write('needed=%s\n' % out)
        return
    if not missing:
        print('nothing to scrape'); return
    cache = scrape(args.base, season, missing)
    cache['updatedAt'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), indent=0, ensure_ascii=False); open(CACHE, 'a').write('\n')
    print('wrote', CACHE)


if __name__ == '__main__':
    main()
