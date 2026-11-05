#!/usr/bin/env python3
"""Builds slack.json: the three busiest conversations in the league Slack over the past week.

    SLACK_BOT_TOKEN=xoxb-...  [ANTHROPIC_API_KEY=...]  python3 tools/build_slack.py

A "conversation" is a run of messages in one public channel with no gap longer than `gapMinutes` (threads included),
so a long unthreaded argument counts as one topic. Topics are ranked by messages x sqrt(people) and must have at least
`minMessages` messages from 2+ people. Public channels only; private channels and DMs are never read.

What is published (the repo and site are public): a short neutral title, the channel name, message and people counts and
a link into Slack (which needs a Slack login). No message text and no names. With ANTHROPIC_API_KEY set, the title is
written by Claude from the conversation (that text is sent to Anthropic); without it the title is the first message,
cut short, so set the key only if you are comfortable with that.

Without SLACK_BOT_TOKEN this does nothing and keeps the last slack.json. Settings: tools/slack_config.json.
"""
import datetime as dt, json, math, os, re, sys, time, urllib.parse, urllib.request

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = {'windowDays': 7, 'gapMinutes': 180, 'minMessages': 8, 'topN': 3, 'autoJoin': False, 'exclude': []}
SKIP_SUBTYPES = {'channel_join', 'channel_leave', 'channel_topic', 'channel_purpose', 'channel_name', 'channel_archive', 'bot_message', 'pinned_item'}


# ---------------------------------------------------------------- ranking (pure: no network)
def conversations(messages, gap_s):
    """messages: [{'ts': float, 'user': str, 'text': str}] for one channel -> list of runs separated by gaps > gap_s"""
    runs, cur = [], []
    for m in sorted(messages, key=lambda m: m['ts']):
        if cur and m['ts'] - cur[-1]['ts'] > gap_s:
            runs.append(cur); cur = []
        cur.append(m)
    if cur:
        runs.append(cur)
    return runs


def rank(by_channel, cfg=CFG):
    """by_channel: {channel_id: {'name': str, 'messages': [...]}} -> top conversations, best first"""
    out = []
    for cid, ch in by_channel.items():
        for run in conversations(ch['messages'], cfg['gapMinutes'] * 60):
            people = {m['user'] for m in run if m.get('user')}
            if len(run) < cfg['minMessages'] or len(people) < 2:
                continue
            out.append({'channel_id': cid, 'channel': ch['name'], 'messages': len(run), 'people': len(people), 'first': run[0], 'run': run,
                        'score': len(run) * math.sqrt(len(people))})
    out.sort(key=lambda c: -c['score'])
    picked = []
    near = cfg.get('dedupeHours', 36) * 3600
    for c in out:   # one saga = one topic: skip a lower-ranked conversation in the same channel right before/after a chosen one
        s0, s1 = c['run'][0]['ts'], c['run'][-1]['ts']
        if any(p['channel_id'] == c['channel_id'] and s0 < p['run'][-1]['ts'] + near and s1 > p['run'][0]['ts'] - near for p in picked):
            continue
        picked.append(c)
        if len(picked) == cfg['topN']:
            break
    return picked


def clean(text):
    text = re.sub(r'<(https?://[^|>]+)(\|[^>]*)?>', '', text or '')           # links
    text = re.sub(r'<@[A-Z0-9]+(\|[^>]*)?>', '', text)                        # mentions
    text = re.sub(r':[a-z0-9_+\-]+:', '', text)                              # emoji codes
    return re.sub(r'\s+', ' ', text).strip()


def fallback_title(conv):
    for m in conv['run']:
        t = clean(m['text'])
        if len(t) >= 20:
            return (t[:60].rsplit(' ', 1)[0] + '…') if len(t) > 60 else t
    return 'Busy chat in #%s' % conv['channel']


def summary_prompt(conv):
    lines = [clean(m['text'])[:300] for m in conv['run'][:80] if clean(m['text'])]
    return ('Below is a fantasy football league chat (oldest first). Summarize what the conversation is about in ONE sentence of at most 80 characters, '
            'like a headline: the actual question or dispute and, if there is one, where it landed. Neutral and family-friendly: do not quote insults or swearing, '
            'no quotation marks, no emoji. Reply with only the sentence.\n\n' + '\n'.join(lines))


def tidy(t):
    t = (t or '').strip().strip('"\'').rstrip('.')
    return t[:90] if t else None


def claude_title(conv, key):
    """One neutral sentence (about 80 characters) saying what the conversation is about, with an Anthropic API key."""
    body = {'model': os.environ.get('SLACK_TOPIC_MODEL', 'claude-haiku-5-5'), 'max_tokens': 60, 'messages': [{'role': 'user', 'content': summary_prompt(conv)}]}
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=json.dumps(body).encode(),
                                 headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    return tidy(json.load(urllib.request.urlopen(req, timeout=60))['content'][0]['text'])


def models_title(conv, token):
    """The same, through GitHub Models with the workflow's own GITHUB_TOKEN (needs `models: read`): no key to create."""
    body = {'model': os.environ.get('GITHUB_MODELS_MODEL', 'openai/gpt-4.1-mini'), 'max_tokens': 60, 'temperature': 0.2,
            'messages': [{'role': 'user', 'content': summary_prompt(conv)}]}
    req = urllib.request.Request('https://models.github.ai/inference/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    return tidy(json.load(urllib.request.urlopen(req, timeout=60))['choices'][0]['message']['content'])


# ---------------------------------------------------------------- Slack API
class Slack:
    def __init__(self, token):
        self.token = token

    def call(self, method, **params):
        for attempt in range(5):
            req = urllib.request.Request('https://slack.com/api/%s?%s' % (method, urllib.parse.urlencode(params)), headers={'Authorization': 'Bearer ' + self.token})
            try:
                data = json.load(urllib.request.urlopen(req, timeout=60))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(int(e.headers.get('Retry-After', '5')) + 1); continue
                raise
            if not data.get('ok'):
                raise RuntimeError('%s: %s' % (method, data.get('error')))
            return data
        raise RuntimeError('%s: rate limited' % method)

    def pages(self, method, key, **params):
        cursor = None
        while True:
            data = self.call(method, **params, **({'cursor': cursor} if cursor else {}))
            yield from data.get(key, [])
            cursor = (data.get('response_metadata') or {}).get('next_cursor')
            if not cursor:
                return


def collect(slack, cfg, oldest):
    by = {}
    n_listed = 0
    for ch in slack.pages('conversations.list', 'channels', types='public_channel', exclude_archived='true', limit=200):
        n_listed += 1
        if ch['name'] in cfg['exclude']:
            continue
        try:
            raw = list(slack.pages('conversations.history', 'messages', channel=ch['id'], oldest='%.6f' % oldest, limit=200))
        except RuntimeError as e:
            if 'not_in_channel' in str(e) and cfg['autoJoin']:
                slack.call('conversations.join', channel=ch['id']); raw = list(slack.pages('conversations.history', 'messages', channel=ch['id'], oldest='%.6f' % oldest, limit=200))
            else:
                print('skip #%s (%s)' % (ch['name'], e), file=sys.stderr); continue
        msgs = {}
        def add(m):
            if m.get('subtype') in SKIP_SUBTYPES or m.get('bot_id') or not m.get('user'):
                return
            msgs[m['ts']] = {'ts': float(m['ts']), 'user': m['user'], 'text': m.get('text', '')}
        for m in raw:
            add(m)
            if m.get('reply_count', 0) >= 2 and m.get('thread_ts') == m['ts']:   # a thread: its replies are part of the conversation
                for r in slack.pages('conversations.replies', 'messages', channel=ch['id'], ts=m['ts'], oldest='%.6f' % oldest, limit=200):
                    add(r)
        print('read #%s: %d raw, %d counted in the last %d days (member=%s)' % (ch['name'], len(raw), len(msgs), cfg['windowDays'], ch.get('is_member')))
        if msgs:
            by[ch['id']] = {'name': ch['name'], 'messages': list(msgs.values())}
    print('%d public channels listed, %d with messages' % (n_listed, len(by)))
    return by


def main():
    token = os.environ.get('SLACK_BOT_TOKEN')
    if not token:
        print('SLACK_BOT_TOKEN not set: keeping slack.json'); return
    cfg = dict(CFG); cfg.update(json.load(open(os.path.join(HUB, 'tools', 'slack_config.json'))) if os.path.exists(os.path.join(HUB, 'tools', 'slack_config.json')) else {})
    slack = Slack(token)
    auth = slack.call('auth.test'); team_url = auth['url']
    print('bot: %s in %s; window starts %s UTC' % (auth.get('user'), auth.get('team'), dt.datetime.fromtimestamp(time.time() - cfg['windowDays'] * 86400, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')))
    oldest = time.time() - cfg['windowDays'] * 86400
    print('workspace:', team_url)
    if os.environ.get('SLACK_PROBE', '0') == '1':   # one-off diagnostics: what does Slack really return for the first joined channel?
        try:
            first = next(c for c in slack.pages('conversations.list', 'channels', types='public_channel', exclude_archived='true', limit=200) if c.get('is_member'))
            for label, extra in (('latest 5, no date filter', {}), ('since the window start', {'oldest': '%.6f' % oldest})):
                d = slack.call('conversations.history', channel=first['id'], limit=5, **extra)
                ts = [m.get('ts') for m in d.get('messages', [])]
                print('probe #%s (%s): %d messages, newest ts %s, has_more=%s, warning=%s, meta=%s, keys=%s' % (first['name'], label, len(ts), ts[:1], d.get('has_more'), d.get('warning'), d.get('response_metadata'), sorted(d)))
            print('now = %.0f' % time.time())
        except Exception as e:
            print('probe failed: %s' % e)
    top = rank(collect(slack, cfg, oldest), cfg)
    key = os.environ.get('ANTHROPIC_API_KEY')
    try:
        kept = {t['href']: t['title'] for t in json.load(open(os.path.join(HUB, 'slack.json'))).get('topics', [])}   # without a key, a conversation keeps the summary it already has
    except Exception:
        kept = {}
    topics = []
    for c in top:
        title = None
        for name, fn, cred in (('anthropic', claude_title, key), ('github-models', models_title, os.environ.get('GITHUB_TOKEN'))):
            if title or not cred:
                continue
            try:
                title = fn(c, cred)
                print('summary via %s: %s' % (name, title))
            except Exception as e:
                print('%s summary failed: %s' % (name, e), file=sys.stderr)
        href = '%sarchives/%s/p%s' % (team_url, c['channel_id'], c['first']['ts'] and ('%.6f' % c['first']['ts']).replace('.', ''))
        title = title or kept.get(href)
        topics.append({'title': title or fallback_title(c), 'channel': c['channel'], 'messages': c['messages'], 'people': c['people'],
                       'href': '%sarchives/%s/p%s' % (team_url, c['channel_id'], c['first']['ts'] and ('%.6f' % c['first']['ts']).replace('.', ''))})
    out = {'schema': 1, 'windowDays': cfg['windowDays'], 'topics': topics, 'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    path = os.path.join(HUB, 'slack.json')
    try:
        old = json.load(open(path))
        if not topics and old.get('topics') and (dt.datetime.now(dt.timezone.utc) - dt.datetime.strptime(old['generatedAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)).days < 14:
            print('no conversation qualified: keeping the last slack.json'); return
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.strptime(old['generatedAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)).days
        if old.get('topics') == topics and age < 3:
            print('slack.json unchanged'); return
    except Exception:
        pass
    json.dump(out, open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); open(path, 'a').write('\n'); print('slack.json written:', [t['title'] for t in topics])


if __name__ == '__main__':
    main()
