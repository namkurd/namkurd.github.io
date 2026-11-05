#!/usr/bin/env python3
"""Collects Rumble Central's own "best matchups" ranking, week by week, into data/matchups.json.

The ranking (wpInterest in rumbles.html: closeness, lead changes, late comebacks, one huge swing, and a 1.25x boost for a
head-to-head) lives in the page and rests on its win-probability model, so instead of re-implementing it this opens the real
page in a headless browser, picks each finished week in Scenarios > Best, and reads the scores the page publishes on every
card (data-best / data-it / data-flips / data-margin / data-h2h). build_feed.py then takes the season's top 3 from that file.

    python3 tools/build_matchups.py --check        # prints needed=true/false: is a finished week missing from the cache?
    python3 tools/build_matchups.py                # scrapes only the missing weeks (finished weeks never change)
    python3 tools/build_matchups.py --base http://localhost:8123/rumbles.html     # test against a local copy

Needs: pip install playwright && playwright install chromium (only when there is something to scrape).
"""
import argparse, datetime as dt, json, os, sys, urllib.request

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HUB, 'data', 'matchups.json')
BASE = 'https://namkurd.github.io/SleeperLiveRumbles/rumbles.html'


def get_json(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'dtf-club-hub'}), timeout=60))


def load_cache(season):
    try:
        c = json.load(open(CACHE, encoding='utf-8'))
        if c.get('season') == season:
            return c
    except Exception:
        pass
    return {'schema': 1, 'season': season, 'weeks': {}}


def plan(base):
    """-> (season, weeks that are finished, have a play-by-play timeline, and are not cached yet)"""
    root = base.rsplit('/', 1)[0]
    hist = get_json(root + '/rumbles_history.json')
    season = int(hist['season'])
    try:
        timeline = set(get_json(root + '/wp_timeline/index.json').get('weeks', []))
    except Exception:
        timeline = set()
    done = {int(w) for w in hist.get('weeks_completed', [])}
    have = set(int(w) for w in load_cache(season)['weeks'])
    return season, sorted((done & timeline) - have)


READ = """() => [...document.querySelectorAll('#scen-blocks .sc-blk.best')].map(s => ({
  best: s.dataset.best, it: +s.dataset.it, flips: +s.dataset.flips, margin: +s.dataset.margin, h2h: s.dataset.h2h === '1',
  names: [...s.querySelectorAll('.sc-bh b')].slice(0, 2).map(b => b.textContent.trim()),
  hl: (s.querySelector('.sc-hl') || {}).textContent || '' }))"""
READY = """(w) => { const s = document.querySelector('#scen-blocks .sc-blk.best'); return !!(s && s.dataset.best && s.dataset.best.split('.')[0] === String(w)); }"""


def scrape(base, season, weeks):
    from playwright.sync_api import sync_playwright
    cache = load_cache(season)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--no-sandbox'], **({'executable_path': os.environ['CHROME_PATH']} if os.environ.get('CHROME_PATH') else {}))   # CHROME_PATH: use an already-installed Chromium
        page = browser.new_page(viewport={'width': 900, 'height': 900})
        page.goto(base, wait_until='load')
        page.wait_for_function("() => document.getElementById('mode-scen') && document.getElementById('week-select')", timeout=60000)
        page.wait_for_timeout(4000)   # the page loads its history and the Sleeper rosters
        page.evaluate("() => document.getElementById('mode-scen').click()")   # no manager picked: it opens on Best
        page.wait_for_timeout(3000)
        for w in weeks:
            for attempt in (1, 2):   # the first pick can arrive before the page has set the Scenarios view up
                try:
                    page.evaluate("(w) => { const s = document.getElementById('week-select'); s.value = String(w); s.dispatchEvent(new Event('change', {bubbles: true})); }", w)
                    page.wait_for_function(READY, arg=w, timeout=60000)
                    rows = page.evaluate(READ)
                    if not rows:
                        raise RuntimeError('no cards')
                    cache['weeks'][str(w)] = rows
                    print('week %d: %d matchups, best %.3f %s' % (w, len(rows), rows[0]['it'], ' vs '.join(rows[0]['names'])))
                    break
                except Exception as e:
                    print('week %d attempt %d failed: %s' % (w, attempt, str(e).splitlines()[0]), file=sys.stderr)
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
