# Project log: Gzenaya Optique / Presbyopia reel (presbyopia-reel)

## Session 1, 2026-10-07

**Brief (approved):** silent hook showing the scroller's pain (he holds the
phone farther and farther to read), then his advice and CTA; smooth, built to
loop. Hook text "حتى نتا كتباعد التيليفون باش تقرا؟", no "presbytie" on screen,
CTA = his share ask + a save button. Music: Dj Zeka "Am I Dreaming" (client
upload).

**Cut (cut.py, 22.16 s):**
- HOOK = C2439 0.5-10.7 s, muted, speed-ramped in 5 segments: 1.0x, 4.0x
  through the squint, 1.5x, 0.6x slow motion on the stretched arm, 2.0x into
  the look to camera.
- ADVICE = C2449 take 3 (27.27-33.52). Take 1 ends in "نعاودو نعاودو", take 2
  is followed by "لا لا", and "زيانة ديما مخايل" is off-script.
- SOL + CTA = C2452 take 2 (14.16-23.96). Take 1 stumbles on "عندو عندو";
  the trailing "صافو" is cut.
- Non-speech is cut with the Silero VAD + level + voicing mask.
- Loop: the last words "الناس اللي كتباعد التيليفون باش تشوف" cut straight
  into the hook.

**Look (third style, different from Reel 02 and the vision test):**
- Karaoke captions: one line, the active word in a navy box, key words in
  yellow.
- Zoom-through transitions between beats (9 frames, blur).
- Continuous push through the hook; slow auto push-ins elsewhere.
- Selective grayscale on "مشكل فالقرب".
- Brand navy #01115f, white, yellow #ffc93c.

**Graphics:**
- Hook headline under his chin (the close-up has no room above the head).
- Distance ruler at the top once the camera pulls back, counting up to 70 cm
  as the arm stretches.
- Near/far chips beside his head: the near phone is blurry ❌, the far phone
  sharp ✓. They shake on "مشكل فالقرب". A card above the head did not fit:
  the head top is at 322 px at zoom 1.0.
- "النصيحة" panel with numbered placeholders 1·2·3 that fill in on his words
  (لأقرب وقت / SPÉCIALISTE / دوز على عينيك).
- CTA: share (paper plane) and save (bookmark) buttons with taps on
  "تبارطاجي" and after "la vidéo".

**Audio:**
- Music from 17.35 s in the track, so the 21.11 s kick lands on the arm
  reveal at 3.76 s. Full level in the silent hook, 10 LU under the voice and
  ducked 9 dB while he talks.
- SFX: headline pops, ramp whoosh, riser + impact on the reveal, ruler ticks +
  ding, zoom whooshes, chip pops, card pops, CTA taps.
- Mix -13.8 LUFS, -1.5 dBTP.

**QC v1:**
- Duration 22.16 s, equal to the timeline; 9 cuts; no black or frozen frames.
- Head check clean (0 frames).
- Fixes before sending:
  - Headline and near card overlapped the head. The headline moved under the
    chin and the card became side chips.
  - The empty tip panel got numbered placeholders.

**Delivered:**
- edit/presbyopia_preview_v1_review.mp4
- 3 post captions in social_captions.md

**Open:** client feedback on v1, then final render + export.py reels with poster
frame.

**Pipeline:** cut.py -> vad_probs.py/fillers.py -> darija_transcribe.py ->
track_subject.py -> render_base.py -> safe_zones.py zones -> overlay events.py
+ build_html.py -> capture_html.py -> safe_zones.py check -> build_audio.py ->
composite.py
