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
