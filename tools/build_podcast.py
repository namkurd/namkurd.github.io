#!/usr/bin/env python3
"""Builds podcast.json: the latest YouTube link posted in the league Slack's podcast channel, for the Home screen's player.

    SLACK_BOT_TOKEN=... python3 tools/build_podcast.py

Reads #podcast (name in tools/podcast_config.json) newest first with the same bot as build_slack.py (public channels only; it joins the
channel if needed) and takes the first youtube.com / youtu.be link in a message or its link preview. The title comes from YouTube's oEmbed
(no key needed) and is tidied into "Episode 51 · The Ichiro Episode" where it can be; the Slack post's first line is the fallback.
If anything fails the previous podcast.json is kept, so a bad run never blanks the player.
"""
import datetime as dt, json, os, re, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HUB, 'podcast.json')
YT = re.compile(r'(?:youtube\.com/(?:watch\?(?:[^\s>|]*&)?v=|live/|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})')


def video_id(text):
    m = YT.search(text or '')
    return m.group(1) if m else None


def message_video(m):
    """The video id in a Slack message: its text first, then the link previews Slack attached."""
    vid = video_id(m.get('text'))
    if vid:
        return vid
    for a in m.get('attachments') or []:
        for k in ('from_url', 'original_url', 'title_link', 'video_html'):
            vid = video_id(a.get(k))
            if vid:
                return vid
    return None


def latest_video(messages):
    """messages newest first -> (video id, message) of the most recent one carrying a YouTube link, else None"""
    for m in messages:
        vid = message_video(m)
        if vid:
            return vid, m
    return None


def tidy_title(yt_title, slack_text):
    """-> (display title, episode number or None, episode name or None)"""
    m = re.search(r'Episode\s+#?(\d+)\s*[:\-]?\s+(.*?)\s+\d{4}\s\d{2}\s\d{2}\b', yt_title or '', re.I)
    if m:
        return 'Episode %s · %s' % (m.group(1), m.group(2).strip()), m.group(1), m.group(2).strip()
    first = re.sub(r'[*_]', '', re.sub(r':[a-z0-9_+-]+:', '', (slack_text or '').strip().split('\n')[0])).strip()
    m = re.search(r'EPISODE\s*#?(\d+)\s*[:\-]?\s*(.+)', first, re.I)
    if m:
        name = m.group(2).strip().title()
        return 'Episode %s · %s' % (m.group(1), name), m.group(1), name
    return (yt_title or '').strip() or 'Latest episode', None, None


def oembed(vid):
    url = 'https://www.youtube.com/oembed?format=json&url=' + urllib.parse.quote('https://www.youtube.com/watch?v=' + vid)
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'dtf-club-hub'}), timeout=30))


def build(vid, msg, info):
    title, ep, name = tidy_title((info or {}).get('title'), msg.get('text'))
    posted = dt.datetime.fromtimestamp(float(msg['ts']), dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    out = {'schema': 1, 'videoId': vid, 'url': 'https://www.youtube.com/watch?v=' + vid, 'title': title, 'postedAt': posted,
           'generatedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    if ep:
        out['episode'] = int(ep)
    if name:
        out['name'] = name
    if info and info.get('author_name'):
        out['channel'] = info['author_name']
    return out


def main():
    token = os.environ.get('SLACK_BOT_TOKEN')
    if not token:
        print('SLACK_BOT_TOKEN not set: keeping podcast.json'); return
    from build_slack import Slack
    cfg = {'channel': 'podcast', 'scan': 400}
    try:
        cfg.update(json.load(open(os.path.join(HUB, 'tools', 'podcast_config.json'))))
    except Exception:
        pass
    slack = Slack(token)
    try:
        ch = next(c for c in slack.pages('conversations.list', 'channels', types='public_channel', exclude_archived='true', limit=200) if c['name'] == cfg['channel'])
        if not ch.get('is_member'):
            slack.call('conversations.join', channel=ch['id'])
        found, n = None, 0
        for m in slack.pages('conversations.history', 'messages', channel=ch['id'], limit=100):
            n += 1
            vid = message_video(m)
            if vid:
                found = (vid, m); break
            if n >= cfg['scan']:
                break
        if not found:
            print('no YouTube link in the last %d messages of #%s: keeping podcast.json' % (n, cfg['channel'])); return
        vid, msg = found
        try:
            info = oembed(vid)
        except Exception as e:
            print('oEmbed failed (%s); using the Slack post for the title' % e, file=sys.stderr); info = None
        out = build(vid, msg, info)
    except Exception as e:
        print('podcast: %s; keeping podcast.json' % e, file=sys.stderr); return
    json.dump(out, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); open(OUT, 'a').write('\n')
    print('podcast: %s (%s)' % (out['title'], out['videoId']))


if __name__ == '__main__':
    main()
