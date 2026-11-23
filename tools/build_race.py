#!/usr/bin/env python3
"""Reads the playoff race out of Rumble Central into data/race.json (each team's chance at a playoff spot, a bye and the 1 seed, and what is clinched).

The odds come from the page's own simulation (the Playoff picture), so this opens the real page in a headless browser and reads window.__dtfRace().
build_recap.py turns the file into the recap's Playoff race card.

    python3 tools/build_race.py --check        # needed=true/false: is the file missing, or older than 6 hours while the season is on?
    python3 tools/build_race.py                # scrape it
    python3 tools/build_race.py --src /path    # serve sibling checkouts (/path/SleeperLiveRumbles/rumbles.html) instead of the published page (testing)
"""
import argparse, datetime as dt, json, mimetypes, os, sys
HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HUB, 'data', 'race.json')
BASE = 'https://namkurd.github.io/SleeperLiveRumbles/rumbles.html'
FRESH_HOURS = 6


def load(path):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return {}


def needed():
    if (load(os.path.join(HUB, 'league.json')).get('status') or '') != 'in_season':
        return False
    old = load(OUT).get('generatedAt')
    if not old:
        return True
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(old.replace('Z', '+00:00'))
    return age > dt.timedelta(hours=FRESH_HOURS)


def scrape(src):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--no-sandbox'], **({'executable_path': os.environ['CHROME_PATH']} if os.environ.get('CHROME_PATH') else {}))
        ctx = browser.new_context(viewport={'width': 900, 'height': 900})
        base = BASE
        if src:
            base = 'http://local.test/SleeperLiveRumbles/rumbles.html'

            def serve(route):
                path = os.path.join(src, route.request.url.split('local.test/', 1)[1].split('?', 1)[0])
                if os.path.isfile(path):
                    route.fulfill(body=open(path, 'rb').read(), content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
                else:
                    route.fulfill(status=404, body='')
            ctx.route('http://local.test/**', serve)
        page = ctx.new_page()
        page.goto(base, wait_until='load')
        page.wait_for_function("() => typeof window.__dtfRace === 'function'", timeout=60000)
        res = None
        for _ in range(90):   # the page loads the season's scores and schedule first
            res = page.evaluate('() => window.__dtfRace()')
            if not res.get('wait'):
                break
            page.wait_for_timeout(1000)
        browser.close()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--src')
    args = ap.parse_args()
    if args.check:
        out = 'true' if needed() else 'false'
        print('needed=' + out)
        if os.environ.get('GITHUB_OUTPUT'):
            open(os.environ['GITHUB_OUTPUT'], 'a').write('needed=%s\n' % out)
        return
    res = scrape(args.src)
    if not res or res.get('wait'):
        print('race: the page was not ready (%s); keeping the last file' % (res or {}).get('err'), file=sys.stderr)
        return
    res.pop('wait', None)
    res['generatedAt'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for t in res['teams']:
        for k in ('make', 'bye', 'one'):
            if t.get(k) is not None:
                t[k] = round(t[k], 3)
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('race: week %d played, %d teams' % (res['played'], len(res['teams'])))


if __name__ == '__main__':
    main()
