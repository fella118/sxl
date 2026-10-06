# Project log

## Session 1 — 2026-10-06

**Strategy:** 47.7s vertical reel. Hook = he reads the comment while an IG
comment card types it in sync; "bien sûr" answer from the hook take; then the
C2416 explanation tightened (fillers, retake calls, dead air removed); ends on
his CTA. Graphics show everything he names: addition +1/+2, vision de loin /
de près separately (X), addition gauge to +3 (hard), criteria checklist
(centrage, hauteur, mesures, correction), 3 days, come back -> centrage ->
professional, comment bar + "gzenaya optique a répondu" notification.

**Decisions:**
- Transcription: MoulSot v0.3 + MMS alignment (Whisper mistranslated Darija).
- Audio: left channel only (lav); right channel is a -40 dB camera mic.
- Picture: 4K source -> 1440x2560 lanczos -> float zoom (warpAffine) anchored
  on the face, light grade (contrast 1.045, sat 1.06), mild unsharp. 50 fps.
- Zoom plan in cut.py: punch-ins on cuts (jump cuts read as intentional),
  zoom in on "plus 3", zoom out for the checklist, push in on the CTA.
- SFX synthesized (studio/bin/sfx.py), each tied to a visible event.
- Captions: 9 bold key-phrase captions only, Cairo 900, lavender highlight
  from the neon logo.

**Pipeline:** cut.py -> animations/overlay/events.py -> capture_html.py ->
render_base.py -> build_audio.py -> composite.py

**Outstanding:** music file (YouTube blocked from the server).

**Preview v1 (edit/preview_v1.mp4):** 47.72s, 1080x1920 50 fps, H.264 ~12 Mbps,
AAC 256k. Mix -14.0 LUFS, -1.5 dBTP, no clipping, 8 cuts click-free.
QC fixes before sending: checklist panel grows row by row (was covering his
forehead), "l'addition" panel enters just before "plus 1", loin/près cards
widened and moved up.
Not yet in v1: music (waiting for the file from the client).

## Session 1, v2 — 2026-10-06 (client notes on v1)

Notes: "feel it more, keep me engaged every 3-5 s, cut the breathing, cut the
misleading word before ماولفتيهمش, smooth direct clear", music attached.

**Changes:**
- Breaths/pauses cut: cut.py splits every gap > 0.14s between kept words,
  keeps 50ms before / 90ms after, edges refined on lav energy. 47.72s -> 43.68s,
  20 ranges, no overlaps, no breath-like lead-ins.
- False start removed: MoulSot heard "يلا ما ولفتي… ما ولفتيهمش"; MMS put the
  slip at 40.96-41.45 and the right word at 41.52-42.62. Kept يلا + the right
  word; also cut the "داكشي مثلا" filler after it.
- Engagement: framing change on almost every cut, word-anchored zoom moves
  (plus 3 in, critères out, le professionnel in, CTA push). Audit: 55 cues,
  longest gap 2.9s. Music is 136 BPM, 2 bars = 3.53s.
- Music: Dj Zeka "Am I Dreaming" from 0:07, ducked 9 dB under speech, level set
  by measurement to 11 LU under the voice (stems: voice -19.9, music -30.9 LUFS).
- Caption added: "كانصح الناس"; "ماولفتيهمش؟" ends before the calendar.

**QC v2:** 43.68s, -14.0 LUFS, -1.5 dBTP, 19 cuts click-free, no clipping.
Review copy (<30 MB) sent; master edit/preview_v2.mp4 (~66 MB).
