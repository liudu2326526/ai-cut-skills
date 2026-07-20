import React from 'react';
import {Img, staticFile} from 'remotion';
import type {EventLayout, MotionEvent} from '../types';

export const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

export const atFrame = (frame: number, values: readonly number[]) => {
  if (frame <= 0) return values[0];
  if (frame >= values.length - 1) return values[values.length - 1];
  const left = Math.floor(frame);
  const progress = frame - left;
  return values[left] + (values[left + 1] - values[left]) * progress;
};

export const lerp = (from: number, to: number, progress: number) =>
  from + (to - from) * progress;

export const mapReferenceX = (value: number, layout: EventLayout) =>
  layout.x + ((value - 107) * layout.width) / 506;

export const mapReferenceY = (value: number, layout: EventLayout) =>
  layout.y + ((value - 215) * layout.height) / 838;

export const mapReferenceWidth = (value: number, layout: EventLayout) =>
  (value * layout.width) / 506;

export const mapReferenceHeight = (value: number, layout: EventLayout) =>
  (value * layout.height) / 838;

export const EventImage: React.FC<{
  event: MotionEvent;
  left: number;
  top: number;
  width: number;
  height: number;
  opacity?: number;
  filter?: string;
  borderRadius?: number;
  boxShadow?: string;
}> = ({
  event,
  left,
  top,
  width,
  height,
  opacity = 1,
  filter,
  borderRadius = event.layout.borderRadius,
  boxShadow,
}) => (
  <div
    style={{
      position: 'absolute',
      left,
      top,
      width,
      height,
      overflow: 'hidden',
      borderRadius,
      opacity,
      filter,
      boxShadow,
      willChange: 'left, top, width, height, filter, opacity',
    }}
  >
    <Img
      src={staticFile(event.src)}
      style={{display: 'block', width: '100%', height: '100%', objectFit: 'fill'}}
    />
  </div>
);
