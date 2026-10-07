"""index.tmpl.html + the shared phrase engine (comment-hook reel v3) -> index_<reel>.html for q1, q2, q3.

The engine is spliced in from the comment-hook reel and re-coloured for the
Gzenaya navy: navy words get white colour trails (navy trails vanish on the
dark shirt), plain white words get yellow ones.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parents[3] / "comment-hook-reel" / "edit" / "animations" / "overlay" / "index.html"
src = REF.read_text()
engine = src[src.index("const tl = gsap.timeline"):src.index("// ---------- hook: IG comment card ----------")]
fitplace = src[src.index("// Shrink a phrase line"):src.index("function placeAll()")]
for a, b in [('const ACCENT = { cyan: "#3be3ff", yellow: "#ffc93c", red: "#ff4d5e" };',
              'const ACCENT = { navy: "#ffffff", yellow: "#ffc93c", red: "#ff4d5e" };'),
             ("ACCENT[wd.color] || ACCENT.cyan", 'ACCENT[wd.color] || "#ffc93c"')]:
    assert a in engine, a
    engine = engine.replace(a, b)
tmpl = (HERE / "index.tmpl.html").read_text().replace("/*ENGINE*/", engine).replace("/*FITPLACE*/", fitplace)
for reel in ("q1", "q2", "q3"):
    html = tmpl.replace("events_REEL.js", f"events_{reel}.js").replace("facepos_REEL.js", f"facepos_{reel}.js")
    (HERE / f"index_{reel}.html").write_text(html)
    print(f"index_{reel}.html: {len(html)} chars")
