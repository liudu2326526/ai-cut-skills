import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {DynamicShrinkEvent} from '../types';

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

const V1_FRAMES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const V1_SCALE = [2.01, 1.88, 1.67, 1.5, 1.37, 1.27, 1.16, 1.09, 1.04, 1.01, 1];
const V1_OFFSET_Y = [-125, -72, -52, -35, -23, -14, -8, -4, 0, 0, 0];
const V1_BLUR = [2.8, 2.7, 2.5, 2.2, 1.8, 1.3, 0.8, 0.45, 0.18, 0.05, 0];
const V1_TRAIL = [1, 1, 1, 0.97, 0.9, 0.76, 0.56, 0.34, 0.15, 0.04, 0];
const V1_SHUTTER = [4.2, 4.1, 3.9, 3.6, 3.2, 2.6, 1.9, 1.25, 0.65, 0.25, 0];

// V2 保留 0..10 帧参考轨迹，只补入用于快门采样的 -4..-1 帧连续预滚。
const V2_FRAMES = [-4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const V2_SCALE = [
  2.2, 2.15, 2.1, 2.055, 2.01, 1.88, 1.67, 1.5, 1.37, 1.27, 1.16, 1.09,
  1.04, 1.01, 1,
];
const V2_OFFSET_Y = [
  -165, -155, -145, -135, -125, -72, -52, -35, -23, -14, -8, -4, 0, 0, 0,
];
const V2_BLUR = [
  3.6, 3.4, 3.2, 3, 2.8, 2.7, 2.5, 2.2, 1.8, 1.3, 0.8, 0.45, 0.18, 0.05, 0,
];
const V2_TRAIL = [
  1.16, 1.12, 1.08, 1.04, 1, 1, 1, 0.97, 0.9, 0.76, 0.56, 0.34, 0.15, 0.04, 0,
];
const V2_SHUTTER = [
  5.2, 5, 4.7, 4.45, 4.2, 4.1, 3.9, 3.6, 3.2, 2.6, 1.9, 1.25, 0.65, 0.25, 0,
];

type MotionState = {
  scale: number;
  offsetY: number;
  blur: number;
  trail: number;
  shutter: number;
};

const stateAt = (
  frame: number,
  frames: number[],
  scale: number[],
  offsetY: number[],
  blur: number[],
  trail: number[],
  shutter: number[],
): MotionState => ({
  scale: interpolate(frame, frames, scale, clamp),
  offsetY: interpolate(frame, frames, offsetY, clamp),
  blur: interpolate(frame, frames, blur, clamp),
  trail: interpolate(frame, frames, trail, clamp),
  shutter: interpolate(frame, frames, shutter, clamp),
});

const v1StateAt = (frame: number) =>
  stateAt(frame, V1_FRAMES, V1_SCALE, V1_OFFSET_Y, V1_BLUR, V1_TRAIL, V1_SHUTTER);

const v2StateAt = (frame: number) =>
  stateAt(frame, V2_FRAMES, V2_SCALE, V2_OFFSET_Y, V2_BLUR, V2_TRAIL, V2_SHUTTER);

const Layer: React.FC<{
  event: DynamicShrinkEvent;
  scale: number;
  offsetY: number;
  opacity?: number;
  blur?: number;
}> = ({event, scale, offsetY, opacity = 1, blur = 0}) => {
  const {layout} = event;
  return (
    <div
      style={{
        position: 'absolute',
        left: layout.x,
        top: layout.y + offsetY,
        width: layout.width,
        height: layout.height,
        borderRadius: layout.borderRadius,
        overflow: 'hidden',
        transformOrigin: `${layout.originX}px ${layout.originY}px`,
        transform: `scale(${scale})`,
        opacity,
        filter: blur > 0 ? `blur(${blur}px)` : undefined,
        willChange: 'transform, filter, opacity',
      }}
    >
      <Img
        src={staticFile(event.src)}
        style={{display: 'block', width: '100%', height: '100%', objectFit: 'contain'}}
      />
    </div>
  );
};

const DynamicShrinkV1: React.FC<{
  event: DynamicShrinkEvent;
  referenceFrame: number;
  spatialScale: number;
  blurScale: number;
}> = ({event, referenceFrame, spatialScale, blurScale}) => {
  const current = v1StateAt(referenceFrame);
  const main = (
    <Layer
      event={event}
      scale={current.scale}
      offsetY={current.offsetY * spatialScale}
      blur={current.blur * blurScale}
    />
  );
  if (current.trail <= 0) return main;

  const samples = event.effect.samples;
  const ghosts = Array.from({length: samples}, (_, index) => {
    const normalized = samples === 1 ? 0.5 : index / (samples - 1);
    const sample = v1StateAt(referenceFrame + (normalized - 0.5) * current.shutter);
    const distance = Math.abs(normalized - 0.5) * 2;
    const weight = Math.pow(1 - distance * 0.62, 1.7);
    return {
      sample,
      opacity: (current.trail * weight * 1.25) / samples,
    };
  });

  return (
    <>
      {main}
      {ghosts.map(({sample, opacity}, index) => (
        <Layer
          key={index}
          event={event}
          scale={sample.scale}
          offsetY={sample.offsetY * spatialScale}
          opacity={opacity}
          blur={Math.max(0.2, current.blur * blurScale * 0.12)}
        />
      ))}
    </>
  );
};

const DynamicShrinkV2: React.FC<{
  event: DynamicShrinkEvent;
  referenceFrame: number;
  spatialScale: number;
  blurScale: number;
}> = ({event, referenceFrame, spatialScale, blurScale}) => {
  const current = v2StateAt(referenceFrame);
  const main = (
    <Layer
      event={event}
      scale={current.scale}
      offsetY={current.offsetY * spatialScale}
      blur={current.blur * blurScale}
    />
  );
  if (current.trail <= 0) return main;

  const samples = event.effect.samples;
  const ghosts = Array.from({length: samples}, (_, index) => {
    const normalized = (index + 0.5) / samples;
    const sample = v2StateAt(referenceFrame + (normalized - 0.54) * current.shutter);
    const weight = Math.pow(Math.sin(Math.PI * normalized), 1.35);
    return {sample, weight};
  });
  const weightTotal = ghosts.reduce((total, item) => total + item.weight, 0) || 1;
  const trailOpacity = 0.82 * current.trail;

  return (
    <>
      {/* 主图保持完全不透明，避免背景穿过白色卡片。 */}
      {main}
      {/* 归一化的 Hann 快门采样只负责径向拖影。 */}
      {ghosts.map(({sample, weight}, index) => (
        <Layer
          key={index}
          event={event}
          scale={sample.scale}
          offsetY={sample.offsetY * spatialScale}
          opacity={(trailOpacity * weight) / weightTotal}
          blur={Math.max(
            0.18 * blurScale,
            (sample.blur * 0.1 + current.blur * 0.035) * blurScale,
          )}
        />
      ))}
    </>
  );
};

export const DynamicShrink: React.FC<{event: DynamicShrinkEvent}> = ({event}) => {
  const frame = useCurrentFrame();
  const {fps, width: canvasWidth} = useVideoConfig();
  const effectFrames = Math.max(1, Math.round(event.effect.duration * fps));
  const referenceFrame = interpolate(frame, [0, effectFrames], [0, 10], clamp);
  const spatialScale = event.layout.height / 838;
  const blurScale = canvasWidth / 720;

  if (event.effect.preset === 'reference_first_v1') {
    return (
      <DynamicShrinkV1
        event={event}
        referenceFrame={referenceFrame}
        spatialScale={spatialScale}
        blurScale={blurScale}
      />
    );
  }
  return (
    <DynamicShrinkV2
      event={event}
      referenceFrame={referenceFrame}
      spatialScale={spatialScale}
      blurScale={blurScale}
    />
  );
};
