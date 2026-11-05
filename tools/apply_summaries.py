#!/usr/bin/env python3
"""Applies the summaries a Claude routine wrote on a branch to main's slack.json.

    python3 tools/apply_summaries.py path/to/branch_slack.json

Only topics that main's slack.json still flags `needs_summary` are touched, matched by their Slack link: the title becomes the branch's
(one line, sensible length) and the flag is removed. Everything else in main's file stays as it is, so a run of the Slack job in between
can't be undone by an older copy.
"""
import json, os, sys

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ok(t):
    return isinstance(t, str) and '\n' not in t and 8 <= len(t.strip()) <= 120


def main(path):
    mine = os.path.join(HUB, 'slack.json')
    cur = json.load(open(mine, encoding='utf-8'))
    new = {t.get('href'): t for t in json.load(open(path, encoding='utf-8')).get('topics', [])}
    n = 0
    for t in cur.get('topics', []):
        b = new.get(t.get('href'))
        if t.get('needs_summary') and b and not b.get('needs_summary') and ok(b.get('title')):
            t['title'] = b['title'].strip(); t.pop('needs_summary', None); n += 1
    if n:
        json.dump(cur, open(mine, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); open(mine, 'a').write('\n')
    print('applied %d summar%s' % (n, 'y' if n == 1 else 'ies'))


if __name__ == '__main__':
    main(sys.argv[1])
