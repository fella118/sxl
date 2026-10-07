# Project log — Gzenaya Optique / Reel 02 (Q&A)

## Session 1 — 2026-10-06

**Brief (approved "go"):** playful Q&A session, same house style as the
comment-hook reel v3. Defaults taken for the open questions: Q2 card shows
"moins dix" (-10), lens spelled "MASTERY Luxe", no index number on the A1
warranty card, order Q1 > A1 > Q3 > A3 > Q2 > A2 > teaser > CTA, teaser kept.
Music: the client will send a track (do not use the Mixkit candidates).

**Intake:** six clips, Sony 4K vertical 50 fps, lav on the left channel.
Transcribed with darija_transcribe.py (MoulSot + MMS). Hook wording corrected
by the client (خويا kept, زاج). A1 opening (C2419 50.2-56.8) was lost by
MoulSot and aligned by hand; 37.5-50 is crew banter.

**Cut (cut.py):** pauses are cut on the lav energy (quiet > 0.24 s cut to
0.05 + 0.09 s), not on word gaps, because MMS squashes some numbers (1.60,
1.67, 1.74) to near-zero words. Dropped: "وهو", "هادشي اللي كاين", the
0.25-steps aside and "des indices ولا des corrections" in A3, "par rapport
لهذا" before the teaser, crew tails. The pause where he holds up the two
frames (C2423 8.4-10.1) is kept. 52 ranges, 103.4 s.

**Picture (render_base.py):** follow-cam + zoom; every cut changes the framing
(auto levels at least 0.08 apart); push-in on each question; eye line lowered
to 50% while the table, the lens card and the frame-arm diagram sit above his
head. 4K close-ups: green INDO warranty card (+ face), white card on "فهاد la
carte de garantie", frame 1, frame 2.

**Graphics (animations/overlay, index.tmpl.html + build_html.py):** quiz card
"سؤال #N" docking into a corner chip, "جواب" wall behind him on each answer,
phrase typography, Q1 price tag 2500 DH, optician speech bubble, "L'INDICE"
pointer on the white card, index table revealed row by row, MASTERY Luxe card
(1.74 organique = plastique, thinner than a normal 1.74), frame-arm diagram
(48 max -> 46), next-video card (cas réel, old -> new prescription), save
button. Grey background on the three punchlines.

**Audio (build_audio.py):** voice chain as reel 1, quiz-show SFX set, no music
yet. Mix -14.0 LUFS, -1.5 dBTP. To add the client's track: put it at
source/music/track.<ext>, set MUSIC_START, re-run build_audio.py and
composite.py.

**Pipeline:** cut.py -> track_subject.py -> render_base.py -> safe_zones.py
zones -> overlay events.py + build_html.py -> capture_html.py (back, front) ->
safe_zones.py check -> build_audio.py -> composite.py

**Preview v1 (edit/preview_v1.mp4, review copy reel-02_preview_v1_review.mp4 720p 28 MB):**
103.42 s (= cut list), 1080x1920 50 fps, -14.0 LUFS, -1.4 dBTP, 51 cuts with a
framing change on each, no black or frozen frames. Head check: 0 frames over
0.5% of the head except 19.00-19.14 (white-card close-up: the pointer is over
his hand, his head is not in the shot). Fixes before sending: table delayed
0.3 s (it clipped his head during the camera tilt), CTA save button moved under
the chin (C2428 is a tight shot, no room above), white-card pointer re-aimed.
Not yet in v1: music (client track to come).
Lessons: never pgrep/pkill -f a pattern that also matches the waiting shell
(it kills or blocks itself); still frames: seek with -ss, not select=eq(n).

## Session 2 — 2026-10-07 (client notes on preview v1)

Notes: split into three separate question reels, each with the same CTA
ending; remove every "ah/ehm", empty voice and breathing; use the logo navy
instead of the sky blue; no misspellings.

**Changes:**
- Three reels (cut.py REELS): q1 = Q1+A1+CTA (33.4 s), q2 = 1.74 question +
  table/lens answer + CTA (38.0 s), q3 = -10 question + frames answer + teaser
  + CTA (34.9 s). Each script runs per reel (REEL=q1|q2|q3), outputs in edit/<reel>/.
- Breaths and dead air: speech = lav > -31 dB and (Silero VAD or voiced);
  everything else inside a passage is cut to 0.10 s of air (vad_probs.py,
  fillers.py). Ranges under 0.4 s are joined to a neighbour (no framing flicker).
  Filler scan: no free-standing "euh/aah"; the long "words" were pauses inside
  the aligned span (now cut). The frame-1 hold in A3 is kept at 0.55 s.
- Brand: Gzenaya navy #01115f (sampled from the logo, brand/go_logo_navy.png)
  replaces the cyan: navy words with white outline, white panels with navy type,
  navy chips and "جواب" wall, navy SAVE.
- Spelling: "100%" (the word lookup picked "ب"; it now takes the nearest word),
  غليظ (was غليض), "ف Gzenaya" (transcript had فݣزلنا), full CTA line
  "غتحتاجو نهار اللي غتبغي دير نضاضر". Question card and chips no longer
  numbered (each reel stands alone).

**Disk (2026-10-07):** the raw 4K clips (reel-02/source/C24*.MP4, 12 GB) were
deleted locally to make room for the next project. Bases, masks, mixes and the
full-quality composites (q1-q3/preview_v2.mp4) are kept, so overlay changes and
final exports need no source. For a re-cut, re-download the Drive folder
https://drive.google.com/drive/folders/1bLTrtH8HF8nUfKkYshsD304ALbobKhbS
(new_project.py client reel-02 <link>) and re-run analysis_audio (fillers.py,
vad_probs.py) if needed.

## Session (cont.), client fixes, 2026-10-07 (Q2 v3, Q3 v3)

- **Q2:** the lens is "Master Luxe", not "MASTERY Luxe" (transcript spelling).
  - Fixed on the lens card ("MASTER" + script "Luxe") and the comparison label
    ("MASTER LUXE").
  - Fixed in Part 2 post caption 3 ("Master Luxe", #MasterLuxe).
- **Q3:** in the teaser he says "le client جا عندنا ب la monture القديمة ديالو
  والجديدة". MoulSot heard "la mention", so the next-video card read
  "LA MENTION". Both chips now read "LA MONTURE".
- **Re-render:** overlay + composite only (base renders and mattes kept). The
  raw clips are still off disk (Drive folder 1bLTrtH8HF8nUfKkYshsD304ALbobKhbS).
- **QC:**
  - Q2 v3: 38.00 s, -14.0 LUFS, -1.5 dBTP, head check clean.
  - Q3 v3: 34.94 s, -14.0 LUFS, -1.5 dBTP, head check clean.
- **Sent:** q2/reel-02_q2_preview_v3_review.mp4,
  q3/reel-02_q3_preview_v3_review.mp4.
