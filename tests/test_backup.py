#!/usr/bin/env python3
"""The weekly backup builder:  python3 tests/test_backup.py   (no network; SMTP is replaced by a recorder)"""
import json, os, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build_backup as B

with tempfile.TemporaryDirectory() as d:
    def w(path, text='x'):
        p = os.path.join(d, path); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(text)
    w('A/data/one.json'); w('A/data/two.csv'); w('A/code/skip.py'); w('A/.git/config'); w('B/seasons/2025/h.json'); w('B/seasons/2025/clips/skip.json')
    manifest = {'repos': {'A': ['data/*.json'], 'B': ['seasons/*/h.json'], 'Missing': ['*.json']}}
    out = os.path.join(d, 'out.zip')
    files, per = B.build_zip(d, out, manifest)
    names = sorted(zipfile.ZipFile(out).namelist())
    assert names == ['A/data/one.json', 'B/seasons/2025/h.json', 'MANIFEST.txt'], names
    assert per == {'A': 1, 'B': 1}, per
    # the real manifest names every repo of the hub's tools
    real = json.load(open(os.path.join(B.HUB, 'tools', 'backup_manifest.json')))
    assert {'Recordbook', 'SleeperLiveRumbles', 'FAB-Management', 'SleeperTradeNodes', 'SleeperAuction', 'Rulebook', 'sleepersheet', 'Sleeper-Head-to-Head', 'namkurd.github.io'} <= set(real['repos'])
    # without credentials nothing is sent; with them one message carries the zip
    assert B.send(out, per, env={}) is False
    sent = []
    class FakeSSL:
        def __init__(self, host, port, context=None, timeout=None): sent.append(('connect', host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, p): sent.append(('login', u))
        def send_message(self, m): sent.append(('msg', m))
    B.smtplib.SMTP_SSL = FakeSSL
    assert B.send(out, per, env={'SMTP_HOST': 'smtp.example.com', 'SMTP_USER': 'me@example.com', 'SMTP_PASSWORD': 'pw', 'BACKUP_EMAIL_TO': 'you@example.com'}) is True
    msg = [x[1] for x in sent if x[0] == 'msg'][0]
    assert msg['To'] == 'you@example.com' and msg['From'] == 'me@example.com' and 'weekly data backup' in msg['Subject'], dict(msg)
    atts = list(msg.iter_attachments())
    assert len(atts) == 1 and atts[0].get_filename().endswith('.zip') and atts[0].get_content()[:2] == b'PK', 'the zip is attached'
    assert ('connect', 'smtp.example.com', 465) in sent and ('login', 'me@example.com') in sent
    # an oversized zip is not attached
    B.MAX_ATTACH = 10
    sent.clear()
    B.send(out, per, env={'SMTP_HOST': 'h', 'SMTP_USER': 'u', 'SMTP_PASSWORD': 'p', 'BACKUP_EMAIL_TO': 't'})
    assert list([x[1] for x in sent if x[0] == 'msg'][0].iter_attachments()) == [] and 'Too big' in [x[1] for x in sent if x[0] == 'msg'][0].get_content()
print('PASS: backup zip and e-mail')
