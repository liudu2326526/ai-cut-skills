import React from 'react';
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  staticFile,
  useVideoConfig,
} from 'remotion';
import {DynamicShrink} from './effects/DynamicShrink';
import {BottomRise} from './effects/BottomRise';
import {FlashStretch} from './effects/FlashStretch';
import {PageCurl} from './effects/PageCurl';
import {PerspectiveSettle} from './effects/PerspectiveSettle';
import type {
  BottomRiseEvent,
  DynamicShrinkEvent,
  FlashStretchEvent,
  MotionCompositionProps,
  MotionEvent,
  PageCurlEvent,
  PerspectiveSettleEvent,
} from './types';

const RenderEvent: React.FC<{event: MotionEvent}> = ({event}) => {
  switch (event.effect.type) {
    case 'dynamic_shrink':
      return <DynamicShrink event={event as DynamicShrinkEvent} />;
    case 'bottom_rise':
      return <BottomRise event={event as BottomRiseEvent} />;
    case 'perspective_settle':
      return <PerspectiveSettle event={event as PerspectiveSettleEvent} />;
    case 'flash_stretch':
      return <FlashStretch event={event as FlashStretchEvent} />;
    case 'page_curl':
      return <PageCurl event={event as PageCurlEvent} />;
    default:
      return null;
  }
};

const EventSequence: React.FC<{event: MotionEvent}> = ({event}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(event.start * fps);
  const durationInFrames = Math.max(1, Math.round((event.end - event.start) * fps));
  return (
    <Sequence from={from} durationInFrames={durationInFrames} premountFor={Math.min(fps, from)}>
      <RenderEvent event={event} />
    </Sequence>
  );
};

export const MotionComposition: React.FC<MotionCompositionProps> = ({
  mode,
  canvas,
  base,
  events,
}) => {
  const baseStyle: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    objectFit: canvas.baseFit === 'stretch' ? 'fill' : canvas.baseFit,
  };

  return (
    <AbsoluteFill
      style={{
        backgroundColor: mode === 'alpha' ? 'transparent' : canvas.backgroundColor,
        overflow: 'hidden',
      }}
    >
      {mode === 'composite' && base ? (
        <OffthreadVideo src={staticFile(base.src)} style={baseStyle} />
      ) : null}
      {events.map((event, index) => (
        <EventSequence key={`${event.name}-${index}`} event={event} />
      ))}
    </AbsoluteFill>
  );
};
