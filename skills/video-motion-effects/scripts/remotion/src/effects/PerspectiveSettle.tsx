import React from 'react';
import {
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {PerspectiveSettleEvent} from '../types';
import {clamp01, lerp, mapReferenceWidth, mapReferenceX, mapReferenceY} from './shared';

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

const PRE_ROLL_START = -4;
const START_SCALE = 1.52;
const START_ROTATE_X = -18;
const START_ROTATE_Y = 36;
const START_OFFSET_X = 66;

type TransformState = {
  scale: number;
  rotateX: number;
  rotateY: number;
  offsetX: number;
  blur: number;
  shutter: number;
  trail: number;
};

const smoothstep = (value: number) => value * value * (3 - 2 * value);
const easeOutQuad = (value: number) => 1 - Math.pow(1 - value, 2);

const transformAt = (frame: number): TransformState => {
  if (frame < 0) {
    const progress = smoothstep(clamp01((frame - PRE_ROLL_START) / -PRE_ROLL_START));
    return {
      scale: lerp(1, START_SCALE, progress),
      rotateX: lerp(0, START_ROTATE_X, progress),
      rotateY: lerp(0, START_ROTATE_Y, progress),
      offsetX: lerp(0, START_OFFSET_X, progress),
      blur: lerp(0, 30, progress),
      shutter: lerp(0, 7.5, progress),
      trail: lerp(0, 1, progress),
    };
  }

  const progress = easeOutQuad(clamp01(frame / 16));
  const remaining = 1 - progress;
  return {
    scale: lerp(1, START_SCALE, remaining),
    rotateX: START_ROTATE_X * remaining,
    rotateY: START_ROTATE_Y * remaining,
    offsetX: START_OFFSET_X * remaining,
    blur: 30 * Math.pow(remaining, 1.85),
    shutter: 7.5 * Math.pow(remaining, 1.35),
    trail: Math.pow(remaining, 0.82),
  };
};

const CardLayer: React.FC<{
  event: PerspectiveSettleEvent;
  state: TransformState;
  opacity?: number;
  blur?: number;
  blurScale: number;
}> = ({event, state, opacity = 1, blur = 0, blurScale}) => {
  const {layout} = event;
  return (
    <div
      style={{
        position: 'absolute',
        left: layout.x + mapReferenceWidth(state.offsetX, layout),
        top: layout.y,
        width: layout.width,
        height: layout.height,
        borderRadius: layout.borderRadius,
        overflow: 'hidden',
        transformOrigin: `${layout.originX}px ${layout.originY}px`,
        transform: `perspective(${mapReferenceWidth(880, layout)}px) rotateX(${state.rotateX}deg) rotateY(${state.rotateY}deg) scale(${state.scale})`,
        transformStyle: 'preserve-3d',
        backfaceVisibility: 'hidden',
        opacity,
        filter: blur > 0 ? `blur(${blur * blurScale}px)` : undefined,
        willChange: 'transform, filter, opacity',
      }}
    >
      <Img
        src={staticFile(event.src)}
        style={{display: 'block', width: '100%', height: '100%', objectFit: 'fill'}}
      />
    </div>
  );
};

export const PerspectiveSettle: React.FC<{event: PerspectiveSettleEvent}> = ({event}) => {
  const frame = useCurrentFrame();
  const {fps, width: canvasWidth} = useVideoConfig();
  const effectFrames = Math.max(1, Math.round(event.effect.duration * fps));
  const referenceFrame = interpolate(frame, [0, effectFrames], [0, 16], clamp);
  const current = transformAt(referenceFrame);
  const rightBoundaryReference = interpolate(
    referenceFrame,
    [0, 1, 2, 7, 8, 9, 10, 12, 16],
    [623, 661, 671, 671, 664, 654, 644, 628, 623],
    clamp,
  );
  const clipLeft = mapReferenceX(48, event.layout);
  const clipTop = mapReferenceY(144, event.layout);
  const clipRight = mapReferenceX(rightBoundaryReference, event.layout);
  const clipBottom = mapReferenceY(1254, event.layout);
  const blurScale = canvasWidth / 720;

  const samples = Array.from({length: event.effect.samples}, (_, index) => {
    const normalized = index / (event.effect.samples - 1);
    const sampleFrame = referenceFrame + (normalized - 0.5) * current.shutter;
    const sample = transformAt(sampleFrame);
    const distance = Math.abs(normalized - 0.5) * 2;
    const weight = Math.pow(Math.max(0, 1 - distance * 0.68), 1.55);
    return {sample, weight};
  });
  const weightTotal = samples.reduce((total, item) => total + item.weight, 0) || 1;
  const ghostOpacity = 1.3 * current.trail;

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        clipPath: `polygon(${clipLeft}px ${clipTop}px, ${clipRight}px ${clipTop}px, ${clipRight}px ${clipBottom}px, ${clipLeft}px ${clipBottom}px)`,
      }}
    >
      {samples.map(({sample, weight}, index) => (
        <CardLayer
          key={index}
          event={event}
          state={sample}
          opacity={(ghostOpacity * weight) / weightTotal}
          blur={Math.max(0.8, sample.blur * 0.18)}
          blurScale={blurScale}
        />
      ))}
      <CardLayer
        event={event}
        state={current}
        blur={current.blur}
        blurScale={blurScale}
      />
    </div>
  );
};
