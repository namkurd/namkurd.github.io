#!/usr/bin/env python3
"""Builds the weekly backup zip of the league tools' data and (optionally) e-mails it.

    python3 tools/build_backup.py --src /path --out backup.zip [--send]

--src is the folder holding a checkout of every repository in tools/backup_manifest.json, each under its own name (the weekly workflow lays them
out that way). The zip holds the data files only (no code, no win-probability timelines or highlight clips, which can be rebuilt) plus a
MANIFEST.txt with the counts and when it was made.

--send e-mails it with Python's standard smtplib, using these environment variables (repository secrets in the workflow):
    SMTP_HOST  SMTP_USER  SMTP_PASSWORD  BACKUP_EMAIL_TO       required
    SMTP_PORT (default 465, SSL; 587 uses STARTTLS)  SMTP_FROM (default SMTP_USER)
Without them nothing is sent (the zip is still written). A zip over 20 MB is not attached; the e-mail says so.
"""
import argparse, datetime as dt, glob, json, os, smtplib, ssl, sys, zipfile
from email.message import EmailMessage

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_ATTACH = 20 * 1024 * 1024


def collect(src, manifest):
    """-> sorted [(repo, relative path)] of every file the manifest's patterns match under src/<repo>/"""
    found = []
    for repo, patterns in manifest['repos'].items():
        base = os.path.join(src, repo)
        if not os.path.isdir(base):
            print('backup: %s is not checked out under %s; skipped' % (repo, src), file=sys.stderr); continue
        seen = set()
        for pat in patterns:
            for path in glob.glob(os.path.join(base, pat), recursive=True):
                rel = os.path.relpath(path, base)
                if os.path.isfile(path) and rel not in seen and '.git' + os.sep not in rel:
                    seen.add(rel); found.append((repo, rel))
    return sorted(found)


def build_zip(src, out, manifest, now=None):
    files = collect(src, manifest)
    now = now or dt.datetime.now(dt.timezone.utc)
    per = {}
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for repo, rel in files:
            z.write(os.path.join(src, repo, rel), '%s/%s' % (repo, rel)); per[repo] = per.get(repo, 0) + 1
        lines = ['DTF Club data backup', 'made %s' % now.strftime('%Y-%m-%d %H:%M UTC'), '']
        lines += ['%-24s %4d files' % (r, n) for r, n in sorted(per.items())] + ['', 'total %d files' % len(files)]
        z.writestr('MANIFEST.txt', '\n'.join(lines) + '\n')
    return files, per


def send(zip_path, per, now=None, env=None):
    env = os.environ if env is None else env
    need = ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'BACKUP_EMAIL_TO')
    missing = [k for k in need if not env.get(k)]
    if missing:
        print('backup: not e-mailed, missing %s (the zip is still saved)' % ', '.join(missing)); return False
    now = now or dt.datetime.now(dt.timezone.utc)
    size = os.path.getsize(zip_path)
    msg = EmailMessage()
    msg['Subject'] = 'DTF Club weekly data backup (%s)' % now.strftime('%Y-%m-%d')
    msg['From'] = env.get('SMTP_FROM') or env['SMTP_USER']; msg['To'] = env['BACKUP_EMAIL_TO']
    body = ['Weekly backup of the league tools\' data, %s.' % now.strftime('%Y-%m-%d'), '',
            'Files per repository:'] + ['  %s: %d' % (r, n) for r, n in sorted(per.items())] + ['', 'Zip size: %.1f MB.' % (size / 1048576)]
    if size > MAX_ATTACH:
        body += ['', 'Too big to attach: download it from this week\'s run in the repository\'s Actions tab (Weekly data backup, artifact "backup").']
    msg.set_content('\n'.join(body))            # the text first: set_content is not allowed once an attachment makes it multipart
    if size <= MAX_ATTACH:
        with open(zip_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='application', subtype='zip', filename='dtf-club-backup-%s.zip' % now.strftime('%Y-%m-%d'))
    port = int(env.get('SMTP_PORT') or 465)
    if port == 465:
        with smtplib.SMTP_SSL(env['SMTP_HOST'], port, context=ssl.create_default_context(), timeout=60) as s:
            s.login(env['SMTP_USER'], env['SMTP_PASSWORD']); s.send_message(msg)
    else:
        with smtplib.SMTP(env['SMTP_HOST'], port, timeout=60) as s:
            s.starttls(context=ssl.create_default_context()); s.login(env['SMTP_USER'], env['SMTP_PASSWORD']); s.send_message(msg)
    print('backup: e-mailed %.1f MB to the configured address' % (size / 1048576)); return True


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--src', required=True); ap.add_argument('--out', default='backup.zip'); ap.add_argument('--send', action='store_true')
    a = ap.parse_args()
    manifest = json.load(open(os.path.join(HUB, 'tools', 'backup_manifest.json'), encoding='utf-8'))
    files, per = build_zip(a.src, a.out, manifest)
    print('backup: %d files, %.1f MB -> %s' % (len(files), os.path.getsize(a.out) / 1048576, a.out))
    if a.send:
        send(a.out, per)


if __name__ == '__main__':
    main()
