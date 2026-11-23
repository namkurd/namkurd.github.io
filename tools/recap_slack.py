#!/usr/bin/env python3
"""Posts the weekly recap to Slack with a "comment of the week": the message with the most emoji reactions in the recap week.

    SLACK_BOT_TOKEN=xoxb-...  python3 tools/recap_slack.py --channel standings [--days 7] [--dry-run]

Reads data/recap.json (tools/build_recap.py), looks through the public channels' last `--days` days for the message with the most reactions
(counted per person per emoji; the league's own bot posts and the recap itself are skipped; ties go to the earlier message), and posts the
recap text plus that comment. The comment's text goes only into the Slack post; it is never written to this repo. Needs channels:read,
channels:history, chat:write. --dry-run prints the post instead of sending it.
"""
import argparse, json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build_slack import Slack, SKIP_SUBTYPES, HUB


def clean_text(slack, text, cache):
    """Slack markup to plain text: <@U123|name> and <@U123> become the person's name, <#C1|chan> the channel, <url|label> the label."""
    def user(m):
        if m.group(2):
            return m.group(2)
        uid = m.group(1)
        if uid not in cache:
            try:
                u = slack.call('users.info', user=uid)['user']
                cache[uid] = u.get('profile', {}).get('display_name') or u.get('real_name') or 'someone'
            except Exception:
                cache[uid] = 'someone'
        return '@' + cache[uid]
    t = re.sub(r'<@([A-Z0-9]+)(?:\|([^>]+))?>', user, text or '')
    t = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', t)
    t = re.sub(r'<(?:https?:[^|>]+)\|([^>]+)>', r'\1', t)
    t = re.sub(r'<https?:[^>]+>', '', t)
    t = t.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\s+', ' ', t).strip()


def best_comment(slack, oldest, skip_ts=()):
    """The most reacted-to message in the public channels since `oldest`: most reactions, then most different people reacting, then the longer message.
    Returns {n, people, channel, who, text, reactions: [{name, count}], link} or None."""
    best, uc = None, {}
    for ch in slack.pages('conversations.list', 'channels', types='public_channel', exclude_archived='true', limit=200):
        if ch.get('name') in ('voting', 'slackmojis', 'trade-voting'):
            continue
        try:
            msgs = list(slack.pages('conversations.history', 'messages', channel=ch['id'], oldest='%.6f' % oldest, limit=200))
        except RuntimeError:
            continue
        for m in msgs:
            rx = m.get('reactions', [])
            n = sum(r.get('count', 0) for r in rx)
            raw = (m.get('text') or '').strip()
            if not n or m.get('subtype') in SKIP_SUBTYPES or m.get('bot_id') or not m.get('user') or m['ts'] in skip_ts or len(raw) < 15 or 'namkurd.github.io' in raw:
                continue   # a bare link, a one-word reply or the weekly standings post is not a comment
            people = len({u for r in rx for u in r.get('users', [])})
            key = (n, people, len(raw))
            if best is None or key > best[0]:
                best = (key, ch, m, n, people)
    if not best:
        return None
    _, ch, m, n, people = best
    who = slack.call('users.info', user=m['user'])['user']
    link = slack.call('chat.getPermalink', channel=ch['id'], message_ts=m['ts'])['permalink']
    text = clean_text(slack, m['text'], uc)
    return {'n': n, 'people': people, 'channel': ch['name'], 'who': who.get('profile', {}).get('display_name') or who.get('real_name'),
            'text': text if len(text) <= 300 else text[:297] + '\u2026', 'reactions': [{'name': r['name'], 'count': r['count']} for r in m['reactions']], 'link': link}


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
        msg += '\n\n*Comment of the week* (%d reactions) \u2014 %s in #%s: \u201c%s\u201d <%s|link>' % (c['n'], c['who'], c['channel'], c['text'], c['link'])
    if args.dry_run:
        print(msg); return
    ch = next(x for x in slack.pages('conversations.list', 'channels', types='public_channel', exclude_archived='true', limit=200) if x['name'] == args.channel)
    slack.call('chat.postMessage', channel=ch['id'], text=msg, unfurl_links='false')
    print('posted to #%s' % args.channel)


if __name__ == '__main__':
    main()
