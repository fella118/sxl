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
