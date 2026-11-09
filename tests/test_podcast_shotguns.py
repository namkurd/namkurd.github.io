#!/usr/bin/env python3
"""Home's podcast and Shotgun builders:  python3 tests/test_podcast_shotguns.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build_podcast as P
import build_shotguns as S

# ---- the latest YouTube link in the podcast channel (newest message first)
msgs = [{'ts': '3', 'text': 'Friday gift above'},
        {'ts': '2', 'text': 'Ladies and Boys. Enjoy!', 'attachments': [{'from_url': 'https://youtu.be/zzzzzzzzzzz?t=4'}]},
        {'ts': '1', 'text': '*CONTENT BOYS EPISODE #51: THE ICHIRO EPISODE* :baseball:\n<https://www.youtube.com/watch?v=pp6XZLvJ8QE|youtube.com/watch?v=…>'}]
vid, m = P.latest_video(msgs)
assert (vid, m['ts']) == ('zzzzzzzzzzz', '2'), 'a link preview counts, and the newest link wins'
assert P.latest_video(msgs[:1]) is None, 'no link, no episode'
assert P.video_id('<https://www.youtube.com/watch?feature=share&v=AbCdEfGhIjK|x>') == 'AbCdEfGhIjK'
assert P.video_id('https://www.youtube.com/live/AbCdEfGhIjK') == 'AbCdEfGhIjK'
t = P.tidy_title('Content Boys Episode 51  The Ichiro Episode   2026 10 29 20 58 EDT   Recording', '')
assert t == ('Episode 51 · The Ichiro Episode', '51', 'The Ichiro Episode'), t
assert P.tidy_title(None, msgs[2]['text'])[0] == 'Episode 51 · The Ichiro Episode', 'the Slack post names the episode when oEmbed is unavailable'
assert P.tidy_title('Something else', 'hi') == ('Something else', None, None)
out = P.build('pp6XZLvJ8QE', {'ts': '1793362779', 'text': ''}, {'title': 'Content Boys Episode 51  The Ichiro Episode   2026 10 29 20 58 EDT', 'author_name': 'DTF Club Podcast'})
assert out['videoId'] == 'pp6XZLvJ8QE' and out['episode'] == 51 and out['postedAt'].startswith('2026-10-30'), out

# ---- Shotguns: defenses and empty slots never count; other seasons are ignored; done comes from the list
facts = {'weeks': {'2026-1': {'teams': {'1': {'shot': [['100', 0], ['0', 0], ['NYG', -1.0]]}, '2': {'shot': []}}},
                   '2026-2': {'teams': {'1': {'shot': [['101', -0.5]]}, '2': {'shot': [['102', 0]]}}},
                   '2025-9': {'teams': {'1': {'shot': [['103', 0]]}}}}}
names = {'100': ['Kyle Pitts Sr.', 'TE'], '101': ['Lamar Jackson', 'QB'], '102': ['Zay Flowers', 'WR']}
mgrs = [{'id': 'a', 'name': 'Aidan', 'roster_id': 1}, {'id': 'b', 'name': 'Ben', 'roster_id': 2}, {'id': 'c', 'name': 'Cal', 'roster_id': 3}]
res = S.build(facts, names, mgrs, 2026, {'2026-2-102-2'})
assert res['total'] == 3 and res['throughWeek'] == 2, res
assert [(x['name'], x['count']) for x in res['managers']] == [('Aidan', 2), ('Ben', 1), ('Cal', 0)], 'most first, then by name'
assert [s['player'] for s in res['managers'][0]['shots']] == ['K. Pitts Sr.', 'L. Jackson']
assert res['managers'][1]['shots'][0]['done'] is True and res['managers'][0]['shots'][0]['done'] is False
# a starting QB ruled out in his game is not a Shotgun (a 'possible' adjustment is not enough)
hist = {'qb_adjustments': [{'week': 2, 'roster_id': 1, 'injured_qb': {'player_id': '101'}, 'confidence': 'confirmed'},
                           {'week': 2, 'roster_id': 2, 'injured_qb': {'player_id': '102'}, 'confidence': 'possible'}]}
res = S.build(facts, names, mgrs, 2026, set(), S.ruled_out(hist))
assert res['total'] == 2 and [(x['name'], x['count']) for x in res['managers']][:2] == [('Aidan', 1), ('Ben', 1)], res
print('PASS: podcast and Shotgun builders')
