# Project log — Gzenaya Optique / Vision test reel (astigmatism-test)

## Session 1 — 2026-10-07

**Brief (approved: option A + defaults):** the E-direction test as filmed
(his script describes the tumbling E, not the astigmatism dial), 3 m distance,
answers in a pinned comment, disclaimer on the chart. Music chosen by the
client: Mixkit "Trap Electro Vibes" (free licence), from the 12.17 s drop.
Client notes: keep only the right words (no slips/corrections), remove
uh/ehm/breaths/empty voice, keep it smooth, and change the editing style
slightly so it does not feel like Reel 02.

**Cut (cut.py, 31.36 s):** HOOK = C2430 take 1 (take 2 stumbles, "نعوضوها"
retake chatter cut) > HOW = C2437 (repeat "هادوك les E" cut, crew "C'est
bon? لا" cut) > TEST = 8.5 s silent pad (held, blurred frame under the
full-screen chart) > CTA = C2438 + 0.6 s loop tail. Non-speech cut on lav
level + Silero VAD + voicing; filler scan found no free-standing euh/aah.

**Look (different from Reel 02 on purpose):** sticker captions (word boxes
with an offset shadow, bouncy pop), white flashes on the big moments, warmer
grade + vignette, slow push-in through every range, 4-frame whip blur on cuts.
Brand navy #01115f + white + yellow.

**Graphics:** frame 1 = STOP sign + "TEST ديال النظر · 10s" card with a turning
E (same state on the last frame, so the reel loops); six step pictograms on
his words (picture below, 3 m, E, directions ليمن/ليسر/لفوق/لتحت, close one
eye, 4 E); full-screen chart: right eye then left eye, 4 E sized for ~3 m on a
phone, countdown bar + ticking; CTA comment bar types "ليمن 4/4 · ليسر 3/4".
Pinned-comment answers: right eye ➡️ ⬇️ ⬅️ ⬆️, left eye ⬆️ ⬅️ ➡️ ⬇️.

**Audio:** voice chain as Reel 02, music 9 LU under the voice, ducked 8 dB
while he talks, full level in the test; SFX: STOP hit, steps pops, direction
ticks, test whoosh, countdown ticks, switch ding, comment typing.
Mix -14.0 LUFS, -1.4 dBTP.

**QC v1:** 31.36 s = timeline, 15 cuts, no black frames; freezes only in the
held test chart (by design); head check clean except the three white flashes.
Fixes before sending: frame 1 rendered blank (seek at t=0), eye pictogram
redrawn, steps panel compacted (head sits higher in C2437; it was scaled to
~60%), composite handles fully opaque overlay frames.

**Pipeline:** cut.py -> vad_probs.py/fillers.py -> track_subject.py ->
render_base.py -> safe_zones.py zones -> overlay events.py + build_html.py ->
capture_html.py -> safe_zones.py check -> build_audio.py -> composite.py
