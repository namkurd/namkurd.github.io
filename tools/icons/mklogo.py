# Rebuilds shell/icons/logo.svg and favicon.svg: the Rumble Central split-flap "R".
# Usage (repo root): pip install fonttools && python3 tools/icons/mklogo.py shell/icons && node tools/icons/render.js
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
import sys
f=TTFont('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'); gs=f.getGlyphSet(); g=gs['R']
b=BoundsPen(gs); g.draw(b); x0,y0,x1,y1=b.bounds
p=SVGPathPen(gs); g.draw(p); d=p.getCommands()
# target bbox 182..349 x 163..349 (512 canvas); flip y
sx=(349-182)/(x1-x0); sy=(349-163)/(y1-y0)
tr=f"matrix({sx:.5f} 0 0 {-sy:.5f} {182-x0*sx:.3f} {349+y0*sy:.3f})"
def svg(bg=True):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
{'<rect width="512" height="512" fill="#0f1115"/>' if bg else ''}
<rect x="116" y="95" width="280" height="321" rx="28" fill="#1f2430" stroke="#ff8a3d" stroke-width="6"/>
<path transform="{tr}" fill="#ff8a3d" d="{d}"/>
<rect x="111" y="254" width="291" height="5" fill="#0f1115"/>
</svg>
'''
open(sys.argv[1]+'/logo.svg','w').write(svg(True))
# favicon: tight crop on the card, transparent outside
fav=svg(False).replace('viewBox="0 0 512 512"','viewBox="96 88 320 336"')
open(sys.argv[1]+'/favicon.svg','w').write(fav)
