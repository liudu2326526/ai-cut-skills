import React from 'react';
import {Composition, type CalculateMetadataFunction} from 'remotion';
import {MotionComposition} from './Composition';
import type {MotionCompositionProps} from './types';

const defaultProps: MotionCompositionProps = {
  mode: 'composite',
  canvas: {
    width: 720,
    height: 1280,
    fps: 30,
    backgroundColor: '#000000',
    baseFit: 'cover',
  },
  durationInSeconds: 2,
  base: null,
  events: [],
};

const calculateMetadata: CalculateMetadataFunction<MotionCompositionProps> = ({props}) => ({
  width: props.canvas.width,
  height: props.canvas.height,
  fps: props.canvas.fps,
  durationInFrames: Math.max(1, Math.ceil(props.durationInSeconds * props.canvas.fps)),
  props,
});

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="MotionEffectsComposite"
      component={MotionComposition}
      width={720}
      height={1280}
      fps={30}
      durationInFrames={60}
      defaultProps={defaultProps}
      calculateMetadata={calculateMetadata}
    />
    <Composition
      id="MotionEffectsAlpha"
      component={MotionComposition}
      width={720}
      height={1280}
      fps={30}
      durationInFrames={60}
      defaultProps={{...defaultProps, mode: 'alpha'}}
      calculateMetadata={calculateMetadata}
    />
  </>
);
