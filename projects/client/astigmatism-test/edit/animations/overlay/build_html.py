"""index.tmpl.html + the shared phrase engine (comment-hook reel v3) -> index.html.

This reel has its own caption look: sticker word boxes that pop in. The engine's
key/num entrance (blur slam + colour trails) is swapped for a bouncy pop.
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

POP = (
    "    } else {\n"
    "      const num = wd.role === \"num\";\n"
    "      tl.fromTo(el, { autoAlpha: 0, scale: 0.2, rotation: num ? 12 : sign * 8, y: 30 },\n"
    "                    { autoAlpha: 1, scale: 1, rotation: num ? -3 : sign * -2, y: 0, duration: 0.3, ease: \"back.out(2.8)\" }, at);\n"
    "      tl.to(el, { rotation: 0, duration: 0.25, ease: \"sine.out\" }, at + 0.3);\n"
    "    }\n"
    "  });\n"
)
a = engine.index("    } else {\n      const blur = motionBlur(el);")
b = engine.index("  tl.to(words.map(w => w.el), { autoAlpha: 0, y: -26")
engine = engine[:a] + POP + engine[b:]

html = (HERE / "index.tmpl.html").read_text().replace("/*ENGINE*/", engine).replace("/*FITPLACE*/", fitplace)
(HERE / "index.html").write_text(html)
print(f"index.html: {len(html)} chars")
