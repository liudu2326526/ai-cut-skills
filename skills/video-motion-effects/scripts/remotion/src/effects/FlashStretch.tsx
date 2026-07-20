import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {FlashStretchEvent} from '../types';
import {
  atFrame,
  clamp01,
  EventImage,
  mapReferenceHeight,
  mapReferenceWidth,
  mapReferenceX,
  mapReferenceY,
} from './shared';

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

const LEFT = [127, 110, 106, 104, 104, 104, 104, 105, 105, 105, 106, 106, 106, 107] as const;
const TOP = [144, 144, 160, 198, 221, 225, 218, 212, 208, 208, 209, 211, 213, 215] as const;
const RIGHT = [588, 599, 606, 608, 609, 610, 611, 611, 611, 611, 611, 611, 611, 612] as const;
const BOTTOM = [1073, 1083, 1087, 1087, 1075, 1064, 1057, 1051, 1048, 1047, 1048, 1049, 1051, 1052] as const;
const BLUR = [30, 25, 20, 13, 8, 4, 2.5, 1.7, 1.2, 0.8, 0.5, 0.25, 0.1, 0] as const;
const BRIGHTNESS = [2.3, 2.25, 2.2, 2.1, 1.85, 1.55, 1.46, 1.37, 1.29, 1.2, 1.14, 1.09, 1.04, 1] as const;
const CONTRAST = [0, 0, 0.015, 0.1, 0.34, 0.68, 0.77, 0.84, 0.89, 0.93, 0.96, 0.98, 0.995, 1] as const;

const Streak: React.FC<{
  event: FlashStretchEvent;
  left: number;
  width: number;
  height: number;
  opacity: number;
  blurScale: number;
}> = ({event, left, width, height, opacity, blurScale}) => (
  <div
    style={{
      position: 'absolute',
      left: mapReferenceX(left, event.layout),
      top: mapReferenceY(144, event.layout),
      width: mapReferenceWidth(width, event.layout),
      height: mapReferenceHeight(height, event.layout),
      backgroundColor: '#fffef5',
      opacity,
      filter: `blur(${11 * blurScale}px) brightness(1.45)`,
      boxShadow: `0 0 ${18 * blurScale}px rgba(255,255,235,.95)`,
    }}
  />
);

export const FlashStretch: React.FC<{event: FlashStretchEvent}> = ({event}) => {
  const frame = useCurrentFrame();
  const {fps, width: canvasWidth} = useVideoConfig();
  const effectFrames = Math.max(1, Math.round(event.effect.duration * fps));
  const referenceFrame = interpolate(frame, [0, effectFrames], [0, 13], clamp);
  const leftReference = atFrame(referenceFrame, LEFT);
  const topReference = atFrame(referenceFrame, TOP);
  const rightReference = atFrame(referenceFrame, RIGHT);
  const bottomReference = atFrame(referenceFrame, BOTTOM);
  const blurScale = canvasWidth / 720;
  const blur = atFrame(referenceFrame, BLUR) * blurScale;
  const brightness = atFrame(referenceFrame, BRIGHTNESS);
  const contrast = atFrame(referenceFrame, CONTRAST);
  const firstFrameTrail = clamp01(1 - referenceFrame);

  return (
    <>
      {firstFrameTrail > 0 ? (
        <>
          <Streak
            event={event}
            left={48}
            width={34}
            height={923}
            opacity={firstFrameTrail}
            blurScale={blurScale}
          />
          <Streak
            event={event}
            left={623}
            width={49}
            height={920}
            opacity={firstFrameTrail}
            blurScale={blurScale}
          />
        </>
      ) : null}

      <EventImage
        event={event}
        left={mapReferenceX(leftReference, event.layout)}
        top={mapReferenceY(topReference, event.layout)}
        width={mapReferenceWidth(rightReference - leftReference + 1, event.layout)}
        height={mapReferenceHeight(bottomReference - topReference + 1, event.layout)}
        filter={`blur(${blur}px) contrast(${contrast}) brightness(${brightness})`}
        boxShadow={
          referenceFrame < 6
            ? `0 0 ${Math.max(4, blur * 0.85)}px rgba(255,255,230,.95)`
            : undefined
        }
      />
    </>
  );
};
