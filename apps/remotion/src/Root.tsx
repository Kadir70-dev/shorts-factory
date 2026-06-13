import { Composition } from "remotion";
import { Short } from "./compositions/Short";
import { SceneGraph } from "./schemas/scene";

// Default props: parse a minimal object through the schema so every defaulted
// field is filled (keeps defaultProps in lockstep with the Zod contract).
const EMPTY = SceneGraph.parse({
  meta: { video_id: "preview", channel_id: "usa_finance", niche: "usa_finance",
          title: "Preview", hook: "Preview" },
  scenes: [{ id: "s1", narration: "preview", duration_sec: 3 }],
});

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Short"
      component={Short}
      durationInFrames={900}      // overridden per-render via calculateMetadata
      fps={30}
      width={1080}
      height={1920}
      schema={SceneGraph}
      defaultProps={EMPTY}
      // duration/fps are DERIVED from the SceneGraph props at render time
      calculateMetadata={({ props }) => {
        const total = props.scenes.reduce((a, s) => a + s.duration_sec, 0);
        return {
          durationInFrames: Math.ceil(total * props.fps),
          fps: props.fps,
          width: props.width,
          height: props.height,
        };
      }}
    />
  );
};
