# Remotion in the studio

Remotion ([remotion-dev/remotion](https://github.com/remotion-dev/remotion)) renders React components to video.
Use it for animated overlays that are easier to write as components than as GSAP pages
(data-driven charts, counters, test cards); the HTML/GSAP overlays and `capture_html.py` stay
the default for word-timed typography.

    cd studio/remotion && npm install          # once per container (node_modules is not committed)
    npx remotion render src/index.ts Smoke out/smoke.mp4
    npx remotion render src/index.ts <Comp> out/frames --sequence --image-format=png   # transparent PNG frames
    npx remotion studio src/index.ts           # live preview (needs a browser on your side)

- `remotion.config.ts` points Remotion at the container's headless Chromium
  (`/opt/pw-browsers/chromium_headless_shell-1194`), so nothing is downloaded at render time.
- Compositions live in `src/Root.tsx`; keep them 1080x1920 at 50 fps to match the footage.
- PNG sequences drop straight into `composite.py` as an overlay layer.
- Agent skills for Remotion are in the marketplace (`remotion-skills`, from remotion-dev/skills).

License: Remotion is free for individuals and for companies with up to 3 employees;
larger companies need a Remotion company license (remotion.pro/license).
