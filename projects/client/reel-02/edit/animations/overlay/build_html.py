"""index.tmpl.html + the shared phrase engine (comment-hook reel v3) -> index.html."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parents[3] / "comment-hook-reel" / "edit" / "animations" / "overlay" / "index.html"
src = REF.read_text()
engine = src[src.index("const tl = gsap.timeline"):src.index("// ---------- hook: IG comment card ----------")]
fitplace = src[src.index("// Shrink a phrase line"):src.index("function placeAll()")]
html = (HERE / "index.tmpl.html").read_text().replace("/*ENGINE*/", engine).replace("/*FITPLACE*/", fitplace)
(HERE / "index.html").write_text(html)
print(f"index.html: {len(html)} chars")
