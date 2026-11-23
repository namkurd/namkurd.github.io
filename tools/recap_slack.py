#!/usr/bin/env python3
"""Posts the weekly recap to Slack with a "comment of the week": the message with the most emoji reactions in the recap week.

    SLACK_BOT_TOKEN=xoxb-...  python3 tools/recap_slack.py --channel standings [--days 7] [--dry-run]

Reads data/recap.json (tools/build_recap.py), looks through the public channels' last `--days` days for the message with the most reactions
(counted per person per emoji; the league's own bot posts and the recap itself are skipped; ties go to the earlier message), and posts the
recap text plus that comment. The comment's text goes only into the Slack post; it is never written to this repo. Needs channels:read,
channels:history, chat:write. --dry-run prints the post instead of sending it.
"""
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build_slack import Slack, SKIP_SUBTYPES, HUB


def best_comment(slack, oldest, skip_ts=()):
    best = None
    for ch in slack.pages('conversations.list', 'channels', types='public_channel', exclude_archived='true', limit=200):
        if ch.get('name') in ('voting', 'slackmojis', 'trade-voting'):
            continue
        try:
            msgs = list(slack.pages('conversations.history', 'messages', channel=ch['id'], oldest='%.6f' % oldest, limit=200))
        except RuntimeError:
            continue
        for m in msgs:
            n = sum(r.get('count', 0) for r in m.get('reactions', []))
            if not n or m.get('subtype') in SKIP_SUBTYPES or m.get('bot_id') or not m.get('user') or m['ts'] in skip_ts or not (m.get('text') or '').strip():
                continue
            key = (n, -float(m['ts']))
            if best is None or key > best[0]:
                best = (key, ch, m, n)
    if not best:
        return None
    _, ch, m, n = best
    who = slack.call('users.info', user=m['user'])['user']
    link = slack.call('chat.getPermalink', channel=ch['id'], message_ts=m['ts'])['permalink']
    emo = ''.join(':%s:' % r['name'] + ('×%d' % r['count'] if r['count'] > 1 else '') for r in m['reactions'][:4])
    text = (m['text'] if len(m['text']) <= 280 else m['text'][:277] + '…').replace('\n', ' ')
    return {'n': n, 'channel': ch['name'], 'who': who.get('profile', {}).get('display_name') or who.get('real_name'), 'text': text, 'emoji': emo, 'link': link}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--channel', default='standings')
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    token = os.environ.get('SLACK_BOT_TOKEN')
    if not token:
        sys.exit('SLACK_BOT_TOKEN is not set')
    slack = Slack(token)
    recap = json.load(open(os.path.join(HUB, 'data', 'recap.json'), encoding='utf-8'))
    msg = recap['slack']
    c = best_comment(slack, time.time() - args.days * 86400)
    if c:
        msg += '\n\n*Comment of the week* (%d reactions %s) — %s in #%s: “%s” <%s|link>' % (c['n'], c['emoji'], c['who'], c['channel'], c['text'], c['link'])
    if args.dry_run:
        print(msg); return
    ch = next(x for x in slack.pages('conversations.list', 'channels', types='public_channel', exclude_archived='true', limit=200) if x['name'] == args.channel)
    slack.call('chat.postMessage', channel=ch['id'], text=msg, unfurl_links='false')
    print('posted to #%s' % args.channel)


if __name__ == '__main__':
    main()
