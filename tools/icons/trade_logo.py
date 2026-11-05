#!/usr/bin/env python3
"""Draws the Trade Network tile logo from the tool's own data: one node per manager (same colours as the tool),
one link per pair that has traded (thicker = more trades), laid out by a small force simulation like the tool's graph.

    python3 tools/icons/trade_logo.py /path/to/SleeperTradeNodes/data.json shell/icons/tools/trades.svg

(or pass an https URL for data.json). Deterministic: the same data always gives the same picture."""
import json, math, sys, urllib.request

COLORS = ['#3b8ff4', '#f64063', '#e85d25', '#c27e26', '#a68e26', '#6ea127', '#2ca95e', '#2ba1a7', '#2b9dc2', '#877bf4', '#b959f4', '#e630cc']  # the tool's dark palette
src, out = sys.argv[1], sys.argv[2]
raw = urllib.request.urlopen(src).read() if src.startswith('http') else open(src, 'rb').read()
data = json.loads(raw)
managers = sorted(data['managers'], key=str.lower)
color = {m: COLORS[i % len(COLORS)] for i, m in enumerate(managers)}   # the tool: ordinal scale over the alphabetical list
pairs, deg = {}, {m: 0 for m in managers}
for t in data['trades']:
    a, b = sorted((t['a'], t['b']))
    pairs[(a, b)] = pairs.get((a, b), 0) + 1
    deg[a] += 1; deg[b] += 1
nodes = [m for m in managers if deg[m] > 0]

# deterministic start on a circle, then spring/charge relaxation
pos = {m: [math.cos(2 * math.pi * i / len(nodes)) * 40, math.sin(2 * math.pi * i / len(nodes)) * 40] for i, m in enumerate(nodes)}
for step in range(600):
    cool = 1 - step / 600
    force = {m: [0.0, 0.0] for m in nodes}
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d2 = dx * dx + dy * dy + 0.01; d = math.sqrt(d2)
            f = 900 / d2
            force[a][0] += f * dx / d; force[a][1] += f * dy / d
            force[b][0] -= f * dx / d; force[b][1] -= f * dy / d
    for (a, b), n in pairs.items():
        dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
        d = math.sqrt(dx * dx + dy * dy) + 0.01
        f = (d - (46 - 5 * min(n, 5))) * 0.06
        force[a][0] += f * dx / d; force[a][1] += f * dy / d
        force[b][0] -= f * dx / d; force[b][1] -= f * dy / d
    for m in nodes:
        force[m][0] -= pos[m][0] * 0.02; force[m][1] -= pos[m][1] * 0.02
        pos[m][0] += max(-6, min(6, force[m][0])) * cool; pos[m][1] += max(-6, min(6, force[m][1])) * cool

# fit into the 96x96 box with a margin
xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
w, h = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1
sc = 74 / max(w, h)
cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
P = {m: (48 + (pos[m][0] - cx) * sc, 48 + (pos[m][1] - cy) * sc) for m in nodes}
maxn = max(pairs.values())
svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-label="Trade Network">']
svg.append('<defs>' + ''.join(f'<linearGradient id="g{i}" gradientUnits="userSpaceOnUse" x1="{P[a][0]:.1f}" y1="{P[a][1]:.1f}" x2="{P[b][0]:.1f}" y2="{P[b][1]:.1f}"><stop offset="0" stop-color="{color[a]}"/><stop offset="1" stop-color="{color[b]}"/></linearGradient>'
                                  for i, (a, b) in enumerate(sorted(pairs))) + '</defs>')
for i, ((a, b), n) in enumerate(sorted(pairs.items())):
    svg.append(f'<line x1="{P[a][0]:.1f}" y1="{P[a][1]:.1f}" x2="{P[b][0]:.1f}" y2="{P[b][1]:.1f}" stroke="url(#g{i})" stroke-opacity=".75" stroke-width="{0.7 + 2.4 * n / maxn:.2f}" stroke-linecap="round"/>')
for m in nodes:
    r = 2.6 + 4.4 * deg[m] / max(deg.values())
    svg.append(f'<circle cx="{P[m][0]:.1f}" cy="{P[m][1]:.1f}" r="{r:.1f}" fill="{color[m]}" stroke="#0f1115" stroke-width="1.2"/>')
svg.append('</svg>')
open(out, 'w').write('\n'.join(svg) + '\n')
print(f'{len(nodes)} managers, {len(pairs)} trading pairs, {sum(pairs.values())} trades -> {out}')
