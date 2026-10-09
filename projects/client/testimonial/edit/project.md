# Project log: SOGIXEL / Client testimonial (Dnanou Atae, Gzenaya Optique)

## Session 1, 2026-10-07

**Brief (approved):** testimonial for ads + the SXL portfolio, "not too much
edited but engaging". Hook = the host's smile, then C2408 from its start as one
continuous track, through the founder's story, ending on the CTA. No music.
One 9:16 video. SXL logo small, top centre, no background, slightly
see-through. Founder's name: Dnanou Atae (Whisper confirms "monsieur Dnanou
Atae" in the intro).

**Logo:** the client's logo came as an image in chat (not a file; the Drive
copy is private), so it is rebuilt as SVG in the overlay (blue gradient
circle, white Anton "SXL", soft shadow), 108 px at the top centre, 90%
opacity. Swap in the original PNG if the client sends the file.

**Cut (cut.py, 64.96 s, 26 ranges):**
- HOOK: C2406 0.0-0.6 smile at 0.6x (1.0 s). Its sound is C2408 running
  (J-cut, range["audio"]), so C2408 is continuous from frame 1.
- INTRO: C2408 2.84-14.48 ("اليوم معانا monsieur Dnanou Atae ... سي Atae،
  نخلي ليك الكلمة").
- STORY: C2410, 6.5-63.0.
  - Cut: the off-topic banter, "متفقين", the doubled "نفس", "هادشي اللي كاين"
    and the trailing "avec... صافي".
  - Drawn-out "euhhh" removed at exact word edges, read from the spectrograms
    (flat harmonics in analysis_audio/C2410_*.png): before les agences,
    d'autres, الماگازان, العام, الماركوتينغ; inside وعيط, الأمر, وتفاهمنا, السي.
- PROOF: C2411 close-up: "دابا ça fait واحد العام / grosso modo كانريكومندي
  ... satisfait إن شاء الله". The off-camera question and the "و euh" are cut.
- CTA: IMG_6057 (iPhone selfie, conformed to a 50 fps proxy in
  edit/proxy/), + 0.5 s tail.
- Pauses tightened, not removed: cut only when the cut saves at least 0.2 s;
  0.07 s + 0.11 s of air kept at each join.

**Look:**
- Hard cuts.
- Framing:
  - Every jump cut changes the framing.
  - The founder opens on a medium shot (name card on the plain wall), then
    alternates with the full wide, where the Gzenaya neon sits under the logo.
    The medium is framed under the neon so the sign is never sliced.
  - The CTA selfie has the eyes on the top third.
- Calm follow-cam.
- Light grade per setup.
- Captions: karaoke, Cairo 800 / Anton, the active word in SXL blue, key lines
  in yellow (le retour sur investissement, ناعسة, des points, satisfait,
  sans résultat).
- Same-script runs keep their reading order in mixed Darija/French lines.
- Graphics:
  - "AVIS CLIENT" pill (0-3.4 s).
  - Name card "DNANOU ATAE / Fondateur · Gzenaya Optique".
  - CTA button "FORMULAIRE 30 S ↓" on "le lien".

**Caption fixes:** monsieur Dnanou Atae, l'avis, SOGIXEL (MoulSot split it as
"Sojic" + "زاد"), سي Atae، نخلي ليك الكلمة, حتى جا, سي سعد (not "ساد"),
نعاونوك (not "نعاودوك"), ڭ written گ (Cairo has no ڭ).

**Audio:** lav left channel (iPhone: dual mono), each source levelled to the
same speech loudness, voice chain, two soft UI pops (name card, CTA button), no
music. Mix -14.0 LUFS, -1.5 dBTP.

**Tool fix:** studio/bin/track_subject.py now reads clip paths from edl.json
"sources" (the proxy), falling back to source/<clip>.MP4.

**QC v1:**
- Duration 64.96 s, equal to the timeline.
- Head check:
  - Clean on all the camera shots.
  - The CTA selfie flags (max 1.2%): the small logo over his hair, because
    the selfie is framed tight. Intended.
  - One frame at 32.0 s (caption crossfade at a cut).

**Open:** client feedback on v1; final render + export (reels preset) + poster
frame. Original SXL logo file to replace the rebuilt one, if wanted.

**Pipeline:** new_project.py > analyze.py > darija_transcribe.py >
vad_probs.py / fillers.py > cut.py > (proxy) > track_subject.py >
render_base.py > safe_zones.py zones > overlay events.py + build_html.py >
capture_html.py > safe_zones.py check > build_audio.py > composite.py

## Session 1 (cont.), v2 final, 2026-10-07

**Client notes on v1:**
- The hook starts with the host's voice directly: the slowed smile (C2406) is
  out. The video opens on C2408 at 2.08 s, so the voice is on frame 1.
- The host's question must be heard: C2411 3.46-9.05 is now one take. The
  off-camera question "وبالنسبة لla durée، شحال نتا معانا أسي Atae؟" (onset
  3.52 s from the lav energy) runs into his answer "دابا ça fait واحد العام".
  - The question is +4 dB (timeline "gain": it was recorded off-mic on the
    founder's lav, -24 vs -20 LUFS). It now measures -12.9 LUFS against the
    answer's -13.4.
  - It is captioned with a small yellow "سؤال" tag and a white highlight.
  - The name was checked with MMS forced alignment: "asi atae" scores -1.6 per
    token against -3.7 for "abdellah" (MoulSot's guess).
  - Gentle push-in as he starts answering.
- "ولكن عطيتو des points اللي خصو يخدم عليهم" removed. His words join
  directly: "…الناس ديال الماركوتينغ كاملين، وحتى هو فهمني فهاد الأمر، تفاهمنا
  على le retour…" (cuts at 44.74 / 48.46 on the lav energy).

**Fixes:**
- A caption faded in at a negative timeline position (first word at 0.02 s),
  which shifted the whole GSAP timeline 3 frames late and hid the logo on
  frames 0-2. Fade-ins are now clamped to t ≥ 0.
- "Atae" lost its Arabic punctuation ("،"/"؟"), so it renders in Anton like
  "Dnanou Atae".

**QC final:**
- 64.70 s, equal to the timeline; 24 cuts; no black or frozen frames;
  -14.0 LUFS, -1.4 dBTP.
- Head check:
  - Clean except the intended logo-on-hair in the tight selfie.
  - One frame at 31.76 s: a caption fading in, at ~15% opacity, across a cut.

**Delivered (deliver/, media not in git):**
- testimonial_reels_v2.mp4: master, H.264 High 1080x1920 50 fps, AAC 192k,
  15 Mbps, 122 MB.
- testimonial_reels_v2_upload.mp4: 2-pass 3.25 Mbps, 28.7 MB, sent in chat.
- testimonial_reels_v2.jpg: cover at 12.8 s, the name card on the medium shot.

**Open:** swap in the original SXL logo PNG if the client sends the file.

## Session 2, 2026-10-08: cover

- **Request:** a cover showing "avis clients" and, in bold, 12 years of trust
  in French.
- **Background:** the founder's listening close-up at 46.8 s of base.mp4. He
  looks straight into the lens, mouth closed; eyes checked on 46.3-47.1.
- **Layout (animations/cover/cover.html -> render_cover.py):**
  - SXL logo at the top.
  - "AVIS CLIENTS" pill (SXL blue) above his head.
  - Over the navy shirt: "12 ANS" in yellow Anton 300 px and "DE CONFIANCE" in
    white Anton 132 px.
  - "Dnanou Atae · Fondateur, Gzenaya Optique".
  - The pill, face and text all fit Instagram's 3:4 grid crop
    (y 240-1680).
- **Note to client:** in the video he says "ça fait واحد العام" (1 year with
  SXL). "12 ANS DE CONFIANCE" reads as the agency's track record.
- **Delivered:** deliver/testimonial_cover_v1.jpg (+ .png).

## Session 2 (cont.), 2026-10-08: cover v2 (the host)

- **Client:** the cover should show him (the host, black shirt), not the
  founder, as a photo from the video, enhanced, with an HDR look, upscaled.
- **Frame:** C2406 frame 0 (0.00 s), the big smile looking into the lens.
  From 0.08 s he blinks.
- **Source:** the original 4K file, not the 1080 render. The frame is cropped
  to the 9:16 window 1814x3226 at (281,120), so the face is centred with the
  eyes at 40% and the same face size as cover v1, then resized to 2160x3840.
  That is true 4K detail, better than AI-upscaling the compressed video.
  Real-ESRGAN x4 is in studio/bin/enhance_photo.py for low-res inputs, but
  isn't needed here.
- **Enhance:**
  - Chroma denoise, a light unsharp mask on luma.
  - The HDR look (enhance_photo.py hdr), retuned: shadows and dark midtones
    open up, highlights are held, moderate clarity, vibrance outside the skin
    hues. The first tuning darkened his face and pushed the skin orange.
- **Cover:** animations/cover/cover_host.html. Same layout as v1, but the
  founder's name line is dropped (it would label the host as Dnanou Atae) and
  "12 ANS DE CONFIANCE" sits 50 px lower to clear the chin. Rendered at 2x by
  render_cover.py.
- **Delivered:** deliver/testimonial_cover_v2.jpg (2160x3840),
  testimonial_cover_v2_1080.jpg (Instagram), .png master.

## Session 2 (cont.), 2026-10-08: cover v3 (teeth)

- **Client:** "whiten and fix my teeth a bit".
- **Retouch (retouch_teeth.py, now studio/bin/retouch_teeth.py; Lab, mouth ROI only):**
  - The mask starts from the clean enamel (L > 172, a* < 150). It grows up to
    24 px into stained or shaded enamel that is yellow-orange rather than pink,
    so the brown bands between the lower teeth join the mask while the gums and
    lips stay out. The dark bite line and mouth corners stop the growth.
  - Stains: their extra darkness is lifted 65% toward the tooth around them, and
    the yellow is compressed with a soft knee. A faint warm shade stays between
    the teeth so they don't merge into one white block.
  - Whitening: a capped low-frequency lift toward L 234, and b* from +21 toward
    +7. Small mid-dark gaps are softened.
  - Strength 0.85: at cover size, 1.0 read as veneers.
  - Pixels outside the mask are bit-exact (blended in BGR), and only the mouth
    differs from v2.
  - The tooth shape is untouched: straightening the lower teeth would look
    fake.
- **Cover:** cover_host.html now uses host4k_teeth.png (gitignored, regenerate
  with `studio/bin/retouch_teeth.py host4k.png host4k_teeth.png --roi 880,1855,1290,2010`).
- **Delivered:** deliver/testimonial_cover_v3.jpg (2160x3840),
  testimonial_cover_v3_1080.jpg (Instagram), .png master.

## Session 2 (cont.), 2026-10-08: cover v4 (12 MOIS)

- **Client:** "12 MOIS", not "12 ANS". This now matches the testimonial: he
  says "ça fait واحد العام" (one year with SXL).
- **cover_host.html:** "12 MOIS DE CONFIANCE".
  - "12 MOIS" is wider than "12 ANS", so it is set at 270 px instead of 300
    (832 px wide, 124 px margins).
  - Same top, so it still clears the chin. The block ends at y 1603, inside
    Instagram's 3:4 grid crop.
- **Delivered:** deliver/testimonial_cover_v4.jpg (2160x3840),
  testimonial_cover_v4_1080.jpg (Instagram), .png master.
