import {Runner} from '@vysmo/transitions';
import React, {useEffect, useRef, useState} from 'react';
import {
  continueRender,
  delayRender,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {PageCurlEvent} from '../types';
import {EventImage} from './shared';
import {pageCurlTransition} from './PageCurlShader';

const PADDING_RATIO = 0.18;
const START_PROGRESS = 0.985;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const easeInOutCubic = (value: number) => {
  const progress = clamp01(value);
  return progress < 0.5
    ? 4 * progress * progress * progress
    : 1 - Math.pow(-2 * progress + 2, 3) / 2;
};

const loadImage = (src: string) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.decoding = 'sync';
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Unable to load page-curl image: ${src}`));
    image.src = src;
  });

const roundedRect = (
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  radius: number,
) => {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  context.beginPath();
  context.moveTo(r, 0);
  context.lineTo(width - r, 0);
  context.quadraticCurveTo(width, 0, width, r);
  context.lineTo(width, height - r);
  context.quadraticCurveTo(width, height, width - r, height);
  context.lineTo(r, height);
  context.quadraticCurveTo(0, height, 0, height - r);
  context.lineTo(0, r);
  context.quadraticCurveTo(0, 0, r, 0);
  context.closePath();
};

const PageCurlCanvas: React.FC<{
  event: PageCurlEvent;
  progress: number;
}> = ({event, progress}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const runnerRef = useRef<Runner | null>(null);
  const [handle] = useState(() => delayRender('Rendering WebGL2 page curl'));
  const paddingX = event.layout.width * PADDING_RATIO;
  const paddingY = event.layout.height * PADDING_RATIO;
  const canvasWidth = Math.max(1, Math.ceil(event.layout.width + paddingX * 2));
  const canvasHeight = Math.max(1, Math.ceil(event.layout.height + paddingY * 2));
  const canvasLeft = event.layout.x - (canvasWidth - event.layout.width) / 2;
  const canvasTop = event.layout.y - (canvasHeight - event.layout.height) / 2;

  useEffect(() => {
    let active = true;
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      continueRender(handle);
    };

    const render = async () => {
      try {
        const image = await loadImage(staticFile(event.src));
        if (!active || !canvasRef.current) return;

        const pageWidth = Math.max(1, Math.round(event.layout.width));
        const pageHeight = Math.max(1, Math.round(event.layout.height));
        const pageCanvas = document.createElement('canvas');
        pageCanvas.width = pageWidth;
        pageCanvas.height = pageHeight;
        const pageContext = pageCanvas.getContext('2d');
        if (!pageContext) throw new Error('Unable to create page-curl source canvas');
        pageContext.imageSmoothingEnabled = true;
        pageContext.imageSmoothingQuality = 'high';
        roundedRect(
          pageContext,
          pageWidth,
          pageHeight,
          event.layout.borderRadius,
        );
        pageContext.clip();
        pageContext.drawImage(image, 0, 0, pageWidth, pageHeight);

        const transparentDestination = document.createElement('canvas');
        transparentDestination.width = canvasWidth;
        transparentDestination.height = canvasHeight;

        const runner = new Runner({
          canvas: canvasRef.current,
          contextAttributes: {
            alpha: true,
            antialias: true,
            premultipliedAlpha: false,
            preserveDrawingBuffer: true,
          },
        });
        runnerRef.current = runner;

        runner.render(pageCurlTransition, {
          from: pageCanvas,
          to: transparentDestination,
          progress,
          params: {
            tilt: 0.1,
            backColor: [1, 0.995, 0.975],
            backTextureStrength: event.effect.backTextureStrength,
            pageScale: [pageWidth / canvasWidth, pageHeight / canvasHeight],
            pageOffset: [0, 0],
            shadowStrength: 0.34,
          },
        });
        runner.gl.finish();
      } finally {
        finish();
      }
    };

    void render();

    return () => {
      active = false;
      runnerRef.current?.dispose();
      runnerRef.current = null;
      finish();
    };
  }, [canvasHeight, canvasWidth, event, handle, progress]);

  return (
    <canvas
      ref={canvasRef}
      width={canvasWidth}
      height={canvasHeight}
      style={{
        position: 'absolute',
        left: canvasLeft,
        top: canvasTop,
        width: canvasWidth,
        height: canvasHeight,
        display: 'block',
        pointerEvents: 'none',
      }}
    />
  );
};

export const PageCurl: React.FC<{event: PageCurlEvent}> = ({event}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const effectFrames = Math.max(1, Math.round(event.effect.duration * fps));

  if (frame >= effectFrames) {
    return (
      <EventImage
        event={event}
        left={event.layout.x}
        top={event.layout.y}
        width={event.layout.width}
        height={event.layout.height}
      />
    );
  }

  const reveal = easeInOutCubic(frame / effectFrames);
  const progress = START_PROGRESS * (1 - reveal);

  return (
    <PageCurlCanvas
      key={`webgl-page-curl-${frame}`}
      event={event}
      progress={progress}
    />
  );
};
