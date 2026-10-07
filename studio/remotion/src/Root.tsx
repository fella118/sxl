import React from "react";
import { AbsoluteFill, Composition, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const NAVY = "#01115f";

// Smoke test: a navy title card that springs in (1080x1920, 50 fps, transparent background).
const Smoke: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 12 } });
  const opacity = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div style={{ transform: `scale(${s})`, opacity, background: "#fff", color: NAVY, border: `8px solid ${NAVY}`,
                    borderRadius: 40, padding: "30px 60px", fontFamily: "sans-serif", fontWeight: 900, fontSize: 120 }}>
        {text}
      </div>
    </AbsoluteFill>
  );
};

export const Root: React.FC = () => (
  <Composition id="Smoke" component={Smoke} durationInFrames={50} fps={50} width={1080} height={1920}
               defaultProps={{ text: "Remotion OK" }} />
);
