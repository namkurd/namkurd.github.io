#!/usr/bin/env python3
"""Reads the latest podcast episode's captions FROM YOUR OWN COMPUTER (YouTube blocks GitHub's servers, but not a home connection) and adds the
"From the pod" quote to the weekly recap.

    pip install youtube-transcript-api
    python3 tools/pod_local.py            # fetch, rebuild the recap, show the quote
    python3 tools/pod_local.py --push     # ...and commit + push data/recap*.json so the Hub picks it up (run from a clone of this repo)
    python3 tools/pod_local.py --force    # redo it even if this episode already has a quote
    python3 tools/pod_local.py --transcript-file captions.json   # use a saved transcript ([{"text": ..., "start": seconds}, ...]) instead of fetching

Only the short quote and its timestamp reach the repo (data/recap_pod.json); the transcript itself goes to a temporary file that is deleted.
The hourly feed job keeps the quote for as long as the episode is the latest one, so this is a once-a-week step: run it after the episode is posted.
"""
import argparse, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HUB = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def sh(*cmd):
    return subprocess.run(cmd, cwd=HUB, check=True, capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--push', action='store_true')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--transcript-file')
    args = ap.parse_args()
    if args.push:
        sh('git', 'pull', '--ff-only', '--quiet')   # start from the latest data
    pod = json.load(open(os.path.join(HUB, 'podcast.json'), encoding='utf-8'))
    vid = pod.get('videoId')
    if not vid:
        sys.exit('podcast.json has no videoId yet')
    have = {}
    try:
        have = json.load(open(os.path.join(HUB, 'data', 'recap_pod.json'), encoding='utf-8'))
    except Exception:
        pass
    if have.get('videoId') == vid and have.get('card') and not args.force:
        print('episode %s already has a quote: "%s" (use --force to redo)' % (pod.get('episode'), have['card']['quote']))
        return
    if args.transcript_file:
        cues = json.load(open(args.transcript_file, encoding='utf-8'))
    else:
        import build_recap
        cues = build_recap.fetch_transcript(vid)
        if not cues:
            sys.exit('could not read the captions for %s. If YouTube asked you to confirm you are not a bot, open the video in a browser on this computer, then try again.' % pod.get('url'))
    print('%d caption lines read' % len(cues))
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(cues, f)
        tmp = f.name
    try:
        env = dict(os.environ, RECAP_TRANSCRIPT=tmp)
        r = subprocess.run([sys.executable, os.path.join(HERE, 'build_recap.py')], cwd=HUB, env=env, capture_output=True, text=True)
        print(r.stdout.strip()); 
        if r.returncode:
            sys.exit(r.stderr.strip() or 'the recap build failed')
    finally:
        os.unlink(tmp)
    got = json.load(open(os.path.join(HUB, 'data', 'recap_pod.json'), encoding='utf-8'))
    card = got.get('card')
    if not card:
        sys.exit('the captions do not talk about this week\'s managers and plays (no stretch names two of them), so the recap has no pod card')
    print('quote at %d:%02d  "%s"\n%s' % (card['at'] // 60, card['at'] % 60, card['quote'], card['url']))
    if args.push:
        sh('git', 'add', 'data/recap.json', 'data/recap_pod.json', *[os.path.join('data', n) for n in os.listdir(os.path.join(HUB, 'data')) if n.startswith('recap_') and n.endswith('.json') and n != 'recap_pod.json'])
        if sh('git', 'status', '--porcelain', '--untracked-files=no'):
            sh('git', 'commit', '-m', 'Podcast quote from the captions (fetched locally)')
            sh('git', 'pull', '--rebase', '--autostash', '--quiet')
            sh('git', 'push', '--quiet')
            print('pushed')
        else:
            print('nothing changed')


if __name__ == '__main__':
    main()
