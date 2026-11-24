#!/usr/bin/env python3
"""Nudge the tools the weekly recap reads (Lifetime = sleepersheet, Record Book) to update themselves once Rumble Central has the finished week, then
wait for them, so the recap is built in the same feed run instead of whenever those repos' own (unreliable) crons fire.

Needs a token that may run workflows in those repos ($SYNC_TOKEN: a fine-grained PAT, Actions read/write on namkurd/sleepersheet and namkurd/Recordbook;
GITHUB_TOKEN is limited to this repo). Without one it says so and does nothing. `--dry-run` only reports what it would do."""
import argparse, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_feed as bf
import build_recap as br

API = 'https://api.github.com/repos/namkurd/%s'
TARGETS = [  # (label, repo, ref, workflow file)
    ('Lifetime standings', 'sleepersheet', 'main', 'update.yml'),
    ('Record Book', 'Recordbook', 'claude/initial-build', 'update.yml'),
]


def gh(path, token, body=None):
    req = urllib.request.Request(API % path if not path.startswith('http') else path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'dtf-club-hub',
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def behind(week):
    """labels (from TARGETS) whose data does not have `week` yet, in dependency order (the Record Book reads Lifetime)."""
    waiting = ' | '.join(br.readiness(week, None))
    return [t for t in TARGETS if t[0] in waiting]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--wait', type=int, default=540, help='seconds to wait per run')
    args = ap.parse_args()
    hist = bf.source(None, 'SleeperLiveRumbles', 'rumbles_history.json')
    wc = hist.get('weeks_completed'); week = int(max(wc) if isinstance(wc, list) and wc else wc or 0)
    if not week:
        print('no finished week yet'); return
    todo = behind(week)
    if not todo:
        print('week %d: every source is current' % week); return
    names = [t[0] for t in todo]
    token = os.environ.get('SYNC_TOKEN')
    if args.dry_run or not token:
        print('week %d: behind: %s. %s' % (week, ', '.join(names), 'dry run' if args.dry_run else 'SYNC_TOKEN is not set, so they are left to their own schedules'))
        return
    for label, repo, ref, wf in todo:
        before = gh('%s/actions/workflows/%s/runs?event=workflow_dispatch&per_page=1' % (repo, wf), token).get('workflow_runs') or []
        last = before[0]['id'] if before else 0
        gh('%s/actions/workflows/%s/dispatches' % (repo, wf), token, {'ref': ref})
        print('dispatched %s (%s)' % (label, repo))
        t0 = time.time(); run = None
        while time.time() - t0 < args.wait:
            time.sleep(15)
            runs = gh('%s/actions/workflows/%s/runs?event=workflow_dispatch&per_page=3' % (repo, wf), token).get('workflow_runs') or []
            run = next((r for r in runs if r['id'] > last), None)
            if run and run['status'] == 'completed':
                break
        print('%s: %s' % (label, (run or {}).get('conclusion') or 'still running'))
        if not run or run.get('conclusion') != 'success':
            break
        time.sleep(60)   # let raw.githubusercontent.com catch up before the next source reads it


if __name__ == '__main__':
    main()
