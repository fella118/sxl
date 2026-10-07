"""index.tmpl.html + the shared placement helpers (comment-hook reel v3) -> index.html.

This reel does not use the phrase engine: captions are karaoke lines driven in seek().
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parents[3] / "comment-hook-reel" / "edit" / "animations" / "overlay" / "index.html"
src = REF.read_text()
fitplace = src[src.index("// Shrink a phrase line"):src.index("function placeAll()")]
html = (HERE / "index.tmpl.html").read_text().replace("/*FITPLACE*/", fitplace)
(HERE / "index.html").write_text(html)
print(f"index.html: {len(html)} chars")
