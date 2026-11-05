#!/usr/bin/env python3
"""Ranking checks for tools/build_slack.py (no network): python3 tests/test_slack_topics.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build_slack as b

H = 3600
def burst(t0, n, users, step=90):
    return [{'ts': t0 + i * step, 'user': users[i % len(users)], 'text': 'message %d about the IR rule and what to do about it' % i} for i in range(n)]

by = {
    # one saga: a small evening thread, the big burst next day, a follow-up the day after (all one topic)
    'C1': {'name': 'general', 'messages': burst(0, 9, ['a', 'b']) + burst(16 * H, 80, ['a', 'b', 'c', 'd']) + burst(40 * H, 10, ['a', 'c'])},
    # a second, real topic elsewhere, plus a separate burst of the same channel a week-ish away
    'C2': {'name': 'trade-discussion', 'messages': burst(100 * H, 25, ['b', 'e'])},
    'C3': {'name': 'gameday', 'messages': burst(120 * H, 12, ['a', 'b', 'c'])},
    # noise: too short, and one person talking to himself
    'C4': {'name': 'random', 'messages': burst(50 * H, 4, ['a', 'b']) + burst(60 * H, 40, ['solo'])},
}
top = b.rank(by)
names = [(t['channel'], t['messages']) for t in top]
print(names)
assert [t['channel'] for t in top] == ['general', 'trade-discussion', 'gameday'], names
assert top[0]['messages'] == 80, 'the saga is one topic, counted from its big burst'
assert all(t['people'] >= 2 for t in top), 'a monologue is not a conversation'
assert b.fallback_title({'run': [{'text': '<@U1> :fire: ok'}, {'text': 'Joe, Aidan, and Ben are walking around removing people from rosters'}], 'channel': 'x'}).endswith('…')
assert b.clean('<https://x.com|link> <@U1|Ben> :joy: hi  there') == 'hi there'
print('ok')
