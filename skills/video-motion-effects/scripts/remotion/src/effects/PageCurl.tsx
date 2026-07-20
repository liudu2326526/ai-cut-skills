import React, {useEffect, useRef, useState} from 'react';
import {
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {PageCurlEvent} from '../types';
import {
  atFrame,
  clamp01,
  EventImage,
  lerp,
  mapReferenceHeight,
  mapReferenceWidth,
  mapReferenceX,
  mapReferenceY,
} from './shared';

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

const LEFT = [48, 48, 48, 117, 157, 157, 156, 156, 155, 154, 153, 152, 150, 148, 144, 140, 133, 126, 120, 116, 113, 111, 110, 109, 108, 107, 107] as const;
const RIGHT = [85, 178, 240, 293, 343, 395, 453, 506, 538, 554, 561, 566, 568, 571, 574, 579, 585, 592, 599, 603, 606, 607, 609, 610, 611, 612, 612] as const;
const BASE_TOP = [313, 307, 288, 317, 312, 311, 310, 309, 307, 306, 303, 300, 297, 292, 286, 277, 266, 252, 240, 232, 227, 223, 220, 218, 217, 216, 215] as const;
const FULL_BOTTOM = [981, 981, 981, 982, 982, 983, 983, 984, 985, 986, 987, 989, 992, 995, 1000, 1006, 1015, 1025, 1034, 1040, 1044, 1047, 1049, 1051, 1052, 1052, 1053] as const;
const CURL_AMOUNT = [0, 0, 0.05, 0.98, 0.985, 0.988, 0.988, 0.988, 0.986, 0.984, 0.98, 0.97, 0.95, 0.92, 0.88, 0.8, 0.68, 0.52, 0.35, 0.2, 0.1, 0.055, 0.03, 0.018, 0.008, 0, 0] as const;
const TIP_LIFT = [0, 5, 16, 54, 69, 77, 66, 44, 22, 10, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] as const;
const SKEW = [0, 5, 16, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] as const;
const BACKFACE_CUT = [0, 0, 0, 0, 0.62, 0.58, 0.88, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1] as const;

const sampleCurve = (points: readonly number[], progress: number) => {
  const position = clamp01(progress) * (points.length - 1);
  const index = Math.min(points.length - 2, Math.floor(position));
  const remainder = position - index;
  return points[index] + (points[index + 1] - points[index]) * remainder;
};

const SPECIAL_GEOMETRY: Record<number, {top: readonly number[]; bottom: readonly number[]}> = {
  3: {
    top: [904, 687, 317, 269, 282, 291, 302],
    bottom: [914, 927, 977, 981, 978, 732, 304],
  },
  4: {
    top: [312, 312, 312, 312, 251, 269, 289],
    bottom: [982, 982, 982, 980, 881, 535, 300],
  },
  5: {
    top: [324, 311, 311, 311, 309, 235, 272],
    bottom: [983, 983, 982, 975, 710, 454, 278],
  },
  6: {
    top: [310, 310, 310, 310, 307, 297, 244],
    bottom: [983, 983, 981, 951, 610, 401, 258],
  },
};

const referenceSliceGeometry = (frame: number, u: number) => {
  const baseTop = atFrame(frame, BASE_TOP);
  const fullBottom = atFrame(frame, FULL_BOTTOM);
  const curl = atFrame(frame, CURL_AMOUNT);
  const tipLift = atFrame(frame, TIP_LIFT);
  const skew = atFrame(frame, SKEW);
  const special = SPECIAL_GEOMETRY[Math.round(frame)];
  if (special && Math.abs(frame - Math.round(frame)) < 1e-6) {
    return {
      top: sampleCurve(special.top, u),
      bottom: sampleCurve(special.bottom, u),
    };
  }
  const curlU = clamp01((u - 0.45) / 0.55);
  const curlEase = curlU * curlU * (3 - 2 * curlU);
  const top = baseTop + skew * u - tipLift * Math.pow(curlU, 8);
  const heightFraction = Math.max(0.012, 1 - curl * curlEase);
  return {top, bottom: top + (fullBottom - baseTop) * heightFraction};
};

const continuousSliceGeometry = (frame: number, u: number) => {
  const lower = Math.floor(frame);
  const upper = Math.ceil(frame);
  if (lower === upper) return referenceSliceGeometry(frame, u);
  const progress = frame - lower;
  const from = referenceSliceGeometry(lower, u);
  const to = referenceSliceGeometry(upper, u);
  return {
    top: lerp(from.top, to.top, progress),
    bottom: lerp(from.bottom, to.bottom, progress),
  };
};

const PageCurlCanvas: React.FC<{
  event: PageCurlEvent;
  referenceFrame: number;
  canvasWidth: number;
  canvasHeight: number;
}> = ({event, referenceFrame, canvasWidth, canvasHeight}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [handle] = useState(() => delayRender('Drawing page curl mesh'));
  const left = mapReferenceX(atFrame(referenceFrame, LEFT), event.layout);
  const right = mapReferenceX(atFrame(referenceFrame, RIGHT), event.layout);
  const fullWidth = Math.max(mapReferenceWidth(1, event.layout), right - left + mapReferenceWidth(1, event.layout));
  const backfaceCut = atFrame(referenceFrame, BACKFACE_CUT);

  useEffect(() => {
    let active = true;
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      continueRender(handle);
    };
    const image = new Image();
    image.src = staticFile(event.src);

    const draw = () => {
      if (!active) return;
      const canvas = canvasRef.current;
      const context = canvas?.getContext('2d');
      if (!canvas || !context) {
        finish();
        return;
      }
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      const sourceWidth = image.naturalWidth || event.layout.width;
      const sourceHeight = image.naturalHeight || event.layout.height;
      const overlap = mapReferenceWidth(0.35, event.layout);

      for (let index = 0; index < event.effect.slices; index++) {
        const u0 = index / event.effect.slices;
        const u1 = (index + 1) / event.effect.slices;
        const u = (u0 + u1) / 2;
        const geometry = continuousSliceGeometry(referenceFrame, u);
        const top = mapReferenceY(geometry.top, event.layout);
        const bottom = mapReferenceY(geometry.bottom, event.layout);
        const x0 = left + fullWidth * u0;
        const x1 = left + fullWidth * u1;
        const reverse = u >= backfaceCut;
        const sourceIndex = reverse ? event.effect.slices - 1 - index : index;
        context.drawImage(
          image,
          (sourceIndex * sourceWidth) / event.effect.slices,
          0,
          sourceWidth / event.effect.slices + sourceWidth / event.effect.slices / 8,
          sourceHeight,
          x0,
          top,
          Math.max(mapReferenceWidth(0.75, event.layout), x1 - x0 + overlap),
          Math.max(mapReferenceHeight(2, event.layout), bottom - top),
        );
      }
      finish();
    };

    image.decode().then(draw).catch(() => {
      if (image.complete) draw();
      else image.onload = draw;
    });

    return () => {
      active = false;
      finish();
    };
  }, [backfaceCut, event, fullWidth, handle, left, referenceFrame]);

  return (
    <canvas
      ref={canvasRef}
      width={canvasWidth}
      height={canvasHeight}
      style={{position: 'absolute', inset: 0, width: canvasWidth, height: canvasHeight}}
    />
  );
};

export const PageCurl: React.FC<{event: PageCurlEvent}> = ({event}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const effectFrames = Math.max(1, Math.round(event.effect.duration * fps));
  const referenceFrame = interpolate(frame, [0, effectFrames], [0, 26], clamp);

  if (referenceFrame >= 20) {
    const leftReference = atFrame(referenceFrame, LEFT);
    const rightReference = atFrame(referenceFrame, RIGHT);
    const topReference = atFrame(referenceFrame, BASE_TOP);
    const bottomReference = atFrame(referenceFrame, FULL_BOTTOM);
    return (
      <EventImage
        event={event}
        left={mapReferenceX(leftReference, event.layout)}
        top={mapReferenceY(topReference, event.layout)}
        width={mapReferenceWidth(rightReference - leftReference + 1, event.layout)}
        height={mapReferenceHeight(bottomReference - topReference + 1, event.layout)}
      />
    );
  }

  return (
    <PageCurlCanvas
      key={`${Math.round(referenceFrame * 1000)}`}
      event={event}
      referenceFrame={referenceFrame}
      canvasWidth={width}
      canvasHeight={height}
    />
  );
};
