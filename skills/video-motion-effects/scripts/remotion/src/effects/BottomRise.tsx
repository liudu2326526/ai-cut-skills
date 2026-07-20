import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {BottomRiseEvent} from '../types';
import {atFrame, EventImage, mapReferenceHeight} from './shared';

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

// 原片 F58..F73：等尺寸卡片从画面底部上冲，前两帧同步显形。
const OFFSET_Y = [
  645, 575, 510, 444, 377, 312, 251, 182, 117, 102, 67, 41, 21, 8, 1, 0,
] as const;
const OPACITY = [
  0, 0.332, 0.664, 0.996, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
] as const;

export const BottomRise: React.FC<{event: BottomRiseEvent}> = ({event}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const effectFrames = Math.max(1, Math.round(event.effect.duration * fps));
  const referenceFrame = interpolate(frame, [0, effectFrames], [0, 15], clamp);
  const opacity = atFrame(referenceFrame, OPACITY);
  const offsetY = mapReferenceHeight(atFrame(referenceFrame, OFFSET_Y), event.layout);

  if (opacity <= 0.001) return null;
  return (
    <EventImage
      event={event}
      left={event.layout.x}
      top={event.layout.y + offsetY}
      width={event.layout.width}
      height={event.layout.height}
      opacity={opacity}
    />
  );
};
