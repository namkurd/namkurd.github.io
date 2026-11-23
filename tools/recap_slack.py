#!/usr/bin/env python3
"""Reads the comment of the week (the message with the most reactions in the public channels) for the recap. Read-only: nothing is ever posted to
Slack from this repo. Needs channels:read and channels:history. Used by build_recap.py."""
import os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build_slack import Slack, SKIP_SUBTYPES, HUB


IGNORE = {'book'}   # reactions that do not count towards the comment of the week


def clean_text(slack, text, cache):
    """Slack markup to plain text: <@U123|name> and <@U123> become the person's name, <#C1|chan> the channel, <url|label> the label."""
    def user(m):
        if m.group(2):
            return '@' + m.group(2).split(' (')[0].split()[0]
        uid = m.group(1)
        if uid not in cache:
            try:
                u = slack.call('users.info', user=uid)['user']
                cache[uid] = ((u.get('profile', {}).get('display_name') or u.get('real_name') or 'someone').split(' (')[0].split() or ['someone'])[0]
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
            rx = [r for r in m.get('reactions', []) if r.get('name') not in IGNORE]   # a :book: is a bookmark, not a vote
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
            'text': text if len(text) <= 300 else text[:297] + '\u2026', 'reactions': [{'name': r['name'], 'count': r['count']} for r in m['reactions'] if r['name'] not in IGNORE], 'link': link}
