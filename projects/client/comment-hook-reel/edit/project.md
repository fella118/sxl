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
