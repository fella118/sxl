# Opus 5.5 video repos

Reference list for making and editing video with Claude Opus 5.5 / Claude Code.
Star counts were read from GitHub pages on 2026-10-06 and are approximate.

## Base repo: yihui-dev/awesome-opus5-5-videos (~2.2k ★)

https://github.com/yihui-dev/awesome-opus5-5-videos

A prompt library, not software: there is nothing to build or install. It has
475 prompts (`prompts/*.md`, `data/videos.json`) for videos Opus 5.5 wrote as
code (HTML, Canvas, SVG, Three.js, GSAP): 288 motion graphics, 70 interactive,
62 explainers and 55 3D scenes.

```bash
git clone --depth 1 https://github.com/yihui-dev/awesome-opus5-5-videos
```

To use it, copy a prompt into Claude Code, ask for a single HTML file, then
render it to MP4. HyperFrames (below) handles that render step.

## Prompt libraries and showcases like it

| Repo | ★ | What it is |
|---|---|---|
| [JohnHeibel/PDoomVideo](https://github.com/JohnHeibel/PDoomVideo) | ~1.9k | Full Opus 5.5 music video in p5.js. Renders with headless Chrome and ffmpeg |
| [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) | ~1.3k | Claude Code skill: 43 film styles, each with a demo film coded by Opus 5.5 |
| [JohnHeibel/ClaudeAnimationBase](https://github.com/JohnHeibel/ClaudeAnimationBase) | ~0.9k | Starter kit for hand-painted cartoon animation with Claude |
| [zhuyansen/awesome-claude-video-skills](https://github.com/zhuyansen/awesome-claude-video-skills) | ~430 | 180+ Claude/Codex video skills by category, each security-graded |
| [Li-Evan/awesome-opus-5.5-video-prompts](https://github.com/Li-Evan/awesome-opus-5.5-video-prompts) | small | 334 verbatim Opus 5.5 video prompts |
| [X-RayLuan/awesome-opus-5-5-video-prompts](https://github.com/X-RayLuan/awesome-opus-5-5-video-prompts) | small | 83 demos with EN + 中文 prompts, including Blender and pixel art |

## Engines and skills that make or edit the video

| Repo | ★ | Use it for | Install in Claude Code |
|---|---|---|---|
| [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) | ~64k | Full agentic production: research, script, real footage, Remotion and FFmpeg | `git clone` then `make setup`, open the folder in Claude Code |
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | ~58k | Turns HTML/GSAP into a deterministic MP4, the same format as the prompts above | `claude plugin marketplace add heygen-com/hyperframes` |
| [browser-use/video-use](https://github.com/browser-use/video-use) | ~28k | Editing real footage: filler-word cuts, grading, subtitles | Ask Claude to set it up from its `install.md` (needs an ElevenLabs key) |
| [hypit-ai/hypit](https://github.com/hypit-ai/hypit) | ~20k | Remixes viral videos: swap faces, words, B-roll | see repo |
| [diffusionstudio/lottie](https://github.com/diffusionstudio/lottie) | ~5.5k | Agent-generated Lottie animations | see repo |
| [remotion-dev/skills](https://github.com/remotion-dev/skills) | ~4.9k | Official Remotion (React video) agent skills | `npx skills add remotion-dev/skills` |
| [FireRedTeam/FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) | ~3.5k | Editing agent you direct in natural language | see repo |
| [Agentchengfeng/chengfeng-videocut-skills](https://github.com/Agentchengfeng/chengfeng-videocut-skills) | ~3.0k | Claude Code skills for cutting video | see repo |
| [0xsline/OpenChatCut](https://github.com/0xsline/OpenChatCut) | ~2.1k | Local, chat-driven timeline editor | see repo |
| [adithya-s-k/manim_skill](https://github.com/adithya-s-k/manim_skill) | ~1.1k | 3Blue1Brown-style explainers made with Manim | see repo |

## Installing the skills

`.claude-plugin/marketplace.json` in this repo is a marketplace
(`sxl-video-skills`) that loads skills straight from their upstream repos, so
nothing is copied in here. HyperFrames and lemo-opuscar have their own
marketplaces.

| Plugin | Skills |
|---|---|
| `hyperframes@hyperframes` | 21 |
| `remotion-skills@sxl-video-skills` | 12 |
| `video-use@sxl-video-skills` | 2 |
| `manim-skills@sxl-video-skills` | 3 |
| `text-to-lottie@sxl-video-skills` | 1 |
| `hypit@sxl-video-skills` | 1 |
| `chengfeng-videocut@sxl-video-skills` | 7 |
| `openmontage@sxl-video-skills` | 49, most of which expect an OpenMontage checkout |
| `lemo-opuscar@lemolab` | 1 |

Add the marketplaces and plugins to `.claude/settings.json`:

```json
"extraKnownMarketplaces": {
  "sxl-video-skills": { "source": { "source": "github", "repo": "fella118/sxl" } },
  "hyperframes": { "source": { "source": "github", "repo": "heygen-com/hyperframes" } },
  "lemolab": { "source": { "source": "github", "repo": "lemomo-ai/lemo-opuscar" } }
},
"enabledPlugins": {
  "hyperframes@hyperframes": true,
  "remotion-skills@sxl-video-skills": true,
  "video-use@sxl-video-skills": true,
  "manim-skills@sxl-video-skills": true,
  "text-to-lottie@sxl-video-skills": true,
  "hypit@sxl-video-skills": true,
  "chengfeng-videocut@sxl-video-skills": true,
  "openmontage@sxl-video-skills": true,
  "lemo-opuscar@lemolab": true
}
```

Or install them from the CLI:

```bash
claude plugin marketplace add fella118/sxl --scope project
claude plugin marketplace add heygen-com/hyperframes --scope project
claude plugin marketplace add lemomo-ai/lemo-opuscar --scope project
for p in remotion-skills video-use manim-skills text-to-lottie hypit chengfeng-videocut openmontage; do
  claude plugin install "$p@sxl-video-skills" --scope project
done
claude plugin install hyperframes@hyperframes --scope project
claude plugin install lemo-opuscar@lemolab --scope project
```

The `fella118/sxl` marketplace source reads the default branch, so merge this
branch first.

Together these add about 11k tokens of skill descriptions to every session.
OpenMontage costs about 5.4k and HyperFrames about 4k. Disable OpenMontage if
you don't use its project. Several skills need extra tools at run time:
ffmpeg, Python, Node, an ElevenLabs key for video-use, and Hypit's runtime.

## Suggested stack

1. Pick a prompt from `awesome-opus5-5-videos`.
2. Generate it with HyperFrames (HTML to MP4) or Remotion skills (React to MP4).
3. Edit real footage with `video-use`. For end-to-end projects, use OpenMontage.
