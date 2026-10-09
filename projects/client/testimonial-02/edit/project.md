# Project log: SOGIXEL / Client testimonial 02 (cover)

## Session 1, 2026-10-09: reel cover

- **Source:** source/screenshot.png. The black bars are cut (rows 226-2305), giving
  edit/frame.png (1170x2080).
- **Framing:** a 90% window, 1053x1872 at (94,79). Her face is centred with the
  eyes at 38%, and the face comes out about 11% larger than in the full frame.
- **Enhance (studio/bin/enhance_photo.py):**
  - Real-ESRGAN x4 (4212x7488; 5 min on CPU) gives crisper eyes, lashes and lips
    than Lanczos. Then a resize to 2160x3840.
  - HDR look: `--hdr 1.5 --lift 0 --clarity 1.8`. The shot is bright and high-key,
    and the default shadow lift brightened and flattened her face (face L 166 to
    184). With no lift and more clarity, her face keeps its brightness while the
    car interior, the shirt and the lips gain contrast and colour. 1:1 checks
    found no halos on the sunglasses or the window.
- **Teeth (studio/bin/retouch_teeth.py, now a studio tool):**
  - Settings: `--roi 840,1800,1180,1925 --core-l 128 --max-chroma 14 --min-area
    120 --gaps 7 --row "<polygon>"`. The polygon is in the command below.
  - Her teeth are grey-white (L 140-235, near-neutral), and her skin is light and
    warm. The chroma rule keeps the skin out of the mask.
  - The dark holes between her teeth (upper left, and the right end of the row)
    are inpainted with the tooth around them. The drawn row polygon keeps both
    mouth corners and the shadow under the upper lip dark.
  - Hairlines between the teeth are softened to a shade, and the teeth are
    whitened. It reads as natural at cover size.
- **Cover (edit/animations/cover/cover.html, rendered by studio/bin/render_cover.py
  at 2x):**
  - Same series look as the first testimonial cover: SXL logo, blue "AVIS CLIENT"
    pill, navy shade over the bottom.
  - Quotes in the house style: small words in Cairo 800, keywords in yellow Anton
    ("LE RETOUR", "HOMA LI JAW…"), curly quote marks in Great Vibes. Five yellow
    stars separate the two quotes.
  - The text keeps her spelling. "Li" becomes "LI" in the uppercase keyword.
  - The pill, face and both quotes fit Instagram's 3:4 grid crop (y 240-1680; the
    quotes end at about 1665).
- **Delivered:** deliver/testimonial-02_cover_v1.jpg (2160x3840),
  testimonial-02_cover_v1_1080.jpg (Instagram), .png master.

**Rebuild** (from the repo root, C=projects/client/testimonial-02/edit/animations/cover):
```
studio/.venv/bin/python -c "import cv2; cv2.imwrite('$C/crop.png', cv2.imread('projects/client/testimonial-02/edit/frame.png')[79:1951, 94:1147])"
studio/.venv-darija/bin/python studio/bin/enhance_photo.py upscale $C/crop.png $C/crop_x4.png
studio/.venv/bin/python studio/bin/enhance_photo.py hdr $C/crop_x4.png $C/her4k_hdr.png --hdr 1.5 --lift 0 --clarity 1.8
studio/.venv/bin/python studio/bin/retouch_teeth.py $C/her4k_hdr.png $C/her4k.png \
  --roi 840,1800,1180,1925 --core-l 128 --max-chroma 14 --min-area 120 --gaps 7 \
  --row "895,1836 915,1834 950,1837 985,1843 1040,1851 1092,1858 1112,1863 1112,1882 1125,1886 1125,1903 1080,1907 1040,1909 990,1907 960,1893 930,1880 905,1872 895,1860"
studio/.venv/bin/python studio/bin/render_cover.py $C/cover.html projects/client/testimonial-02/deliver/testimonial-02_cover_v1 --scale 2
```

**Open:** client feedback. Her name and business could go on the cover if wanted.
