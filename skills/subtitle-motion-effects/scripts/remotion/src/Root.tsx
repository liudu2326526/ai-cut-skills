import React from 'react';
import {Composition, type CalculateMetadataFunction} from 'remotion';
import {SubtitleComposition} from './Composition';
import type {SubtitleCompositionProps} from './types';

const defaultProps: SubtitleCompositionProps = {
  mode: 'alpha',
  canvas: {
    width: 720,
    height: 1280,
    fps: 30,
    backgroundColor: '#000000',
    baseFit: 'cover',
  },
  durationInSeconds: 2,
  base: null,
  fonts: [],
  subtitles: [],
};

const calculateMetadata: CalculateMetadataFunction<SubtitleCompositionProps> = ({props}) => ({
  width: props.canvas.width,
  height: props.canvas.height,
  fps: props.canvas.fps,
  durationInFrames: Math.max(1, Math.ceil(props.durationInSeconds * props.canvas.fps)),
  props,
});

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="SubtitleMotionComposite"
      component={SubtitleComposition}
      width={720}
      height={1280}
      fps={30}
      durationInFrames={60}
      defaultProps={{...defaultProps, mode: 'composite'}}
      calculateMetadata={calculateMetadata}
    />
    <Composition
      id="SubtitleMotionAlpha"
      component={SubtitleComposition}
      width={720}
      height={1280}
      fps={30}
      durationInFrames={60}
      defaultProps={defaultProps}
      calculateMetadata={calculateMetadata}
    />
  </>
);
