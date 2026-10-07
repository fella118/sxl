import { Config } from "@remotion/cli/config";

// Use the container's pre-installed headless Chromium instead of downloading one.
Config.setBrowserExecutable("/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell");
Config.setVideoImageFormat("png");
Config.setChromiumOpenGlRenderer("swangle");
