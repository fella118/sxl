#!/usr/bin/env bash
# Rebuild the split-screen reel: B-roll/captions (top) + face cam (bottom).
# usage: ./build.sh <source.mov> <work_dir>
# Edit scenes or captions in broll.html (CAPS array), then re-run.
set -euo pipefail
SRC=$1; WORK=$2; HERE=$(cd "$(dirname "$0")" && pwd); DUR=53.4
mkdir -p "$WORK/frames"

# 1) top half + captions -> transparent PNG frames
NODE_PATH=$(npm root -g) node "$HERE/render.cjs" "$HERE/broll.html" "$WORK/frames" $DUR 30 4

# 2) soft whooshes on scene changes, pops on key moments
ffmpeg -v error -y -f lavfi -i "anoisesrc=d=0.5:c=pink:a=0.6:r=48000" \
  -af "highpass=f=300,lowpass=f=4500,afade=t=in:d=0.22:curve=qsin,afade=t=out:st=0.22:d=0.28:curve=qsin,pan=stereo|c0=c0|c1=c0" "$WORK/whoosh.wav"
ffmpeg -v error -y -f lavfi -i "aevalsrc='0.6*sin(2*PI*(650+1100*t)*t)*exp(-26*t)':d=0.2:s=48000" -af "pan=stereo|c0=c0|c1=c0" "$WORK/pop.wav"
inputs=(); chains=""; n=0
for t in 3.82 12.12 13.42 17.02 20.12 23.02 27.32 33.32 42.22 48.82; do
  ms=$(awk "BEGIN{print int($t*1000)}"); inputs+=(-i "$WORK/whoosh.wav"); chains+="[$n:a]volume=0.16,adelay=$ms|$ms[a$n];"; n=$((n+1)); done
for t in 18.1 31.7 42.75 51.15; do
  ms=$(awk "BEGIN{print int($t*1000)}"); inputs+=(-i "$WORK/pop.wav"); chains+="[$n:a]volume=0.22,adelay=$ms|$ms[a$n];"; n=$((n+1)); done
mix=""; for i in $(seq 0 $((n-1))); do mix+="[a$i]"; done
ffmpeg -v error -y "${inputs[@]}" -filter_complex "${chains}${mix}amix=inputs=$n:normalize=0:duration=longest,apad=whole_dur=$DUR,atrim=0:$DUR[o]" \
  -map "[o]" -ar 48000 "$WORK/sfx.wav"

# 3) composite: face crop (y=370) in the bottom half with punch-in zooms, overlay frames, loudness-normalised voice + SFX
Z="between(t,11.36,13.40)+between(t,17.98,19.80)+between(t,42.76,47.10)+between(t,51.00,53.40)"
ffmpeg -v error -stats -y -i "$SRC" -framerate 30 -i "$WORK/frames/f_%05d.png" -i "$WORK/sfx.wav" -filter_complex "\
[0:v]trim=0:$DUR,setpts=PTS-STARTPTS,fps=30,crop=1080:960:0:370,split[f1][f2];\
[f2]scale=1156:1028:flags=lanczos,crop=1080:960:38:20[fz];\
[f1][fz]overlay=0:0:enable='$Z'[face];\
color=c=black:s=1080x1920:r=30:d=$DUR[bg];[bg][face]overlay=0:960:shortest=1[base];\
[base][1:v]overlay=0:0:format=auto,format=yuv420p[v];\
[0:a]atrim=0:$DUR,asetpts=PTS-STARTPTS,aresample=48000,highpass=f=80,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[voice];\
[voice][2:a]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.89[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 18 -maxrate 12M -bufsize 24M -profile:v high -level 4.2 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart -t $DUR "$HERE/reel_claude_prospection.mp4"
