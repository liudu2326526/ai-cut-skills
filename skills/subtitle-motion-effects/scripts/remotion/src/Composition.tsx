import React, {useEffect, useMemo, useState} from 'react';
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {
  FontAsset,
  SubtitleCompositionProps,
  SubtitleCue,
  SubtitleSpan,
  SubtitleTokenTiming,
  TextStyle,
} from './types';

type Token = {
  text: string;
  style: TextStyle;
  start?: number;
  end?: number;
};

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const FontLoader: React.FC<{fonts: FontAsset[]}> = ({fonts}) => {
  const [handle] = useState(() => delayRender('Loading subtitle fonts'));

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const withFiles = fonts.filter((font) => font.src);
      await Promise.all(
        withFiles.map(async (font) => {
          const face = new FontFace(
            font.family,
            `url("${staticFile(font.src as string)}")`,
            {
              weight: font.weight ?? 'normal',
              style: font.style ?? 'normal',
            },
          );
          const loaded = await face.load();
          (document.fonts as FontFaceSet & {add: (font: FontFace) => void}).add(loaded);
        }),
      );
    };

    load()
      .catch((error) => {
        console.warn('Failed to load subtitle fonts', error);
      })
      .finally(() => {
        if (!cancelled) continueRender(handle);
      });

    return () => {
      cancelled = true;
    };
  }, [fonts, handle]);

  return null;
};

const splitText = (text: string, granularity: 'char' | 'word') => {
  if (granularity === 'word' && /\s/.test(text)) {
    return text.split(/(\s+)/).filter((item) => item.length > 0);
  }
  return Array.from(text);
};

const buildTokens = (cue: SubtitleCue): Token[] => {
  const sourceSpans: SubtitleSpan[] = cue.spans.length > 0
    ? cue.spans
    : [{text: cue.text, style: {}}];

  const visualTokens = sourceSpans.flatMap((span) =>
    splitText(span.text, cue.effect.granularity).map((text) => ({
      text,
      style: {...cue.style, ...(span.style ?? {})},
    })),
  );

  return attachTimings(visualTokens, cue.tokens, cue.end - cue.start, cue.effect.granularity);
};

const expandTimingsToVisualTokens = (
  timings: SubtitleTokenTiming[],
  targetCount: number,
  granularity: 'char' | 'word',
) => {
  if (timings.length === targetCount) return timings;
  if (granularity !== 'char') return timings;

  const expanded: SubtitleTokenTiming[] = [];
  timings.forEach((timing) => {
    const chars = Array.from(timing.text);
    if (chars.length <= 1) {
      expanded.push(timing);
      return;
    }
    const duration = Math.max(0.001, timing.end - timing.start);
    chars.forEach((char, index) => {
      const start = timing.start + duration * index / chars.length;
      const end = timing.start + duration * (index + 1) / chars.length;
      expanded.push({text: char, start, end, style: timing.style});
    });
  });
  return expanded;
};

const attachTimings = (
  visualTokens: Token[],
  timings: SubtitleTokenTiming[],
  cueDuration: number,
  granularity: 'char' | 'word',
) => {
  if (!timings.length) return visualTokens;
  const expanded = expandTimingsToVisualTokens(timings, visualTokens.length, granularity);
  if (!expanded.length) return visualTokens;

  return visualTokens.map((token, index) => {
    const timing = expanded[index];
    if (!timing) {
      const fallbackStart = cueDuration * index / Math.max(1, visualTokens.length);
      const fallbackEnd = cueDuration * (index + 1) / Math.max(1, visualTokens.length);
      return {...token, start: fallbackStart, end: fallbackEnd};
    }
    return {
      ...token,
      start: timing.start,
      end: timing.end,
      style: {
        ...token.style,
        ...(timing.style ?? {}),
        // 字幕时间戳只负责“什么时候动”，不能把品牌词 span 已经确定好的字体冲掉。
        fontFamily: token.style.fontFamily ?? timing.style?.fontFamily,
      },
    };
  });
};

const positionStyle = (cue: SubtitleCue, canvas: {width: number; height: number}): React.CSSProperties => {
  const safeX = Math.round(canvas.width * 0.07);
  const safeBottom = Math.round(canvas.height * 0.2);
  const maxWidth = cue.maxWidth;
  if (cue.position === 'custom') {
    return {
      left: cue.x ?? safeX,
      top: cue.y ?? Math.round(canvas.height * 0.62),
      width: maxWidth,
    };
  }
  const centered: React.CSSProperties = {
    left: '50%',
    width: maxWidth,
    transform: 'translateX(-50%)',
  };
  if (cue.position === 'top_center') return {...centered, top: Math.round(canvas.height * 0.16)};
  if (cue.position === 'center') {
    return {
      ...centered,
      top: '50%',
      transform: 'translate(-50%, -50%)',
    };
  }
  if (cue.position === 'middle_lower') {
    return {
      ...centered,
      top: Math.round(canvas.height * 0.62),
      transform: 'translate(-50%, -50%)',
    };
  }
  if (cue.position === 'bottom_center') return {...centered, bottom: Math.round(canvas.height * 0.1)};
  return {...centered, bottom: safeBottom};
};

const textStyle = (style: TextStyle, align: SubtitleCue['align']): React.CSSProperties => ({
  color: style.color ?? '#FFFFFF',
  fontFamily: style.fontFamily ?? 'Arial, sans-serif',
  fontSize: style.fontSize ?? 64,
  fontWeight: style.fontWeight ?? 700,
  lineHeight: style.lineHeight ?? 1.12,
  letterSpacing: style.letterSpacing ?? 0,
  textAlign: align,
  WebkitTextStroke: `${style.strokeWidth ?? 3}px ${style.strokeColor ?? '#000000'}`,
  paintOrder: 'stroke fill',
  textShadow: style.shadowBlur
    ? `0 0 ${style.shadowBlur}px ${style.shadowColor ?? 'rgba(0,0,0,0.55)'}`
    : 'none',
  whiteSpace: 'normal',
  wordBreak: 'break-word',
});

const boxStyle = (style: TextStyle): React.CSSProperties => ({
  backgroundColor: style.backgroundColor ?? 'transparent',
  borderRadius: style.borderRadius ?? 0,
  padding: `${style.paddingY ?? 0}px ${style.paddingX ?? 0}px`,
});

const tokenTransform = (
  cue: SubtitleCue,
  index: number,
  count: number,
  localFrame: number,
  fps: number,
  token?: Token,
) => {
  const staggerFrames = Math.max(1, Math.round(cue.effect.stagger * fps));
  const tokenStartFrame = token?.start == null
    ? index * staggerFrames
    : Math.round(token.start * fps);
  const tokenFrame = localFrame - tokenStartFrame;
  if (cue.effect.type === 'bounce_badge' && (cue.effect.badgeShape ?? cue.effect.preset) === 'heart') {
    return {opacity: 1, transform: 'translateY(0) scale(1)'};
  }
  if (cue.effect.type === 'drop_word') {
    const durationFrames = Math.max(1, Math.round(cue.effect.duration * fps));
    const springValue = spring({
      frame: Math.max(0, tokenFrame),
      fps,
      config: cue.effect.preset === 'bounce_drop'
        ? {damping: 7, stiffness: 190, mass: 0.52}
        : {damping: 10, stiffness: 155, mass: 0.62},
      durationInFrames: durationFrames,
    });
    const progress = clamp01(tokenFrame / durationFrames);
    const fontSize = Number(token?.style.fontSize ?? cue.style.fontSize ?? 64);
    const dropDistance = Math.max(38, fontSize * (cue.effect.preset === 'bounce_drop' ? 1.75 : 1.35));
    const y = interpolate(springValue, [0, 1], [-dropDistance, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const rotation = interpolate(springValue, [0, 0.72, 1], [-11, 3, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const scaleValue = interpolate(springValue, [0, 0.78, 1], [0.86, 1.05, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const opacity = tokenFrame < -2
      ? 0
      : interpolate(progress, [0, 0.12, 1], [0, 1, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const blur = progress < 0.22 ? interpolate(progress, [0, 0.22], [2, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 0;
    return {
      opacity,
      filter: blur > 0 ? `blur(${blur}px)` : 'none',
      transform: `translateY(${y}px) rotate(${rotation}deg) scale(${scaleValue})`,
    };
  }
  if (cue.effect.type === 'pop_word' || cue.effect.type === 'bounce_badge' || cue.effect.type === 'stack_pop') {
    const isStackPop = cue.effect.type === 'stack_pop';
    const scale = spring({
      frame: tokenFrame,
      fps,
      config: isStackPop
        ? {damping: 7, stiffness: 260, mass: 0.42}
        : {damping: 9, stiffness: 210, mass: 0.45},
      durationInFrames: Math.round(cue.effect.duration * fps),
    });
    const eased = interpolate(scale, [0, 1], [isStackPop ? 0.62 : 0.72, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const lift = interpolate(scale, [0, 0.65, 1], [isStackPop ? 18 : 12, isStackPop ? -12 : -8, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    return {
      opacity: tokenFrame < -2 ? 0 : 1,
      transform: `translateY(${lift}px) scale(${eased})`,
    };
  }
  if (cue.effect.type === 'fade_slide') {
    const progress = clamp01(tokenFrame / Math.max(1, cue.effect.duration * fps));
    const opacity = interpolate(progress, [0, 1], [0, 1]);
    const y = interpolate(progress, [0, 1], [14, 0]);
    return {opacity, transform: `translateY(${y}px)`};
  }
  if (cue.effect.type === 'typewriter') {
    const visible = cue.syncMode === 'timed_tokens'
      ? count
      : Math.ceil(clamp01(localFrame / Math.max(1, cue.effect.duration * fps)) * count);
    if (cue.syncMode === 'timed_tokens') {
      return {opacity: tokenStartFrame <= localFrame ? 1 : 0, transform: 'translateY(0) scale(1)'};
    }
    return {opacity: index < visible ? 1 : 0, transform: 'translateY(0) scale(1)'};
  }
  return {opacity: 1, transform: 'translateY(0) scale(1)'};
};

const activeIndex = (cue: SubtitleCue, tokens: Token[], localFrame: number, fps: number) => {
  const count = tokens.length;
  const localSeconds = localFrame / fps;
  if (cue.syncMode === 'timed_tokens') {
    const exact = tokens.findIndex((token) =>
      token.start != null
      && token.end != null
      && localSeconds >= token.start
      && localSeconds < token.end
    );
    if (exact >= 0) return exact;

    for (let index = count - 1; index >= 0; index -= 1) {
      const token = tokens[index];
      if (token.start != null && localSeconds >= token.start) return index;
    }
    return 0;
  }
  const total = Math.max(1, Math.round((cue.end - cue.start) * fps));
  return Math.min(count - 1, Math.max(0, Math.floor((localFrame / total) * count)));
};

const estimateTokenWidth = (cue: SubtitleCue, token: Token) => {
  const fontSize = Number(token.style.fontSize ?? cue.style.fontSize ?? 64);
  const text = token.text || '';
  if (!text.trim()) return Math.max(4, fontSize * 0.32);
  const hasAscii = /[A-Za-z0-9￥¥.,!?]/.test(text);
  const charCount = Math.max(1, Array.from(text).length);
  const glyphWidth = hasAscii ? fontSize * 0.58 : fontSize * 0.9;
  return Math.max(fontSize * 0.42, charCount * glyphWidth + fontSize * 0.08);
};

const travellingBadgeState = (
  cue: SubtitleCue,
  tokens: Token[],
  localFrame: number,
  fps: number,
) => {
  const visibleTokens = tokens.length ? tokens : [{text: cue.text, style: cue.style}];
  const count = visibleTokens.length;
  const active = activeIndex(cue, visibleTokens, localFrame, fps);
  const widths = visibleTokens.map((token) => estimateTokenWidth(cue, token));
  const rawLineWidth = widths.reduce((sum, width) => sum + width, 0);
  const lineWidth = Math.max(1, Number(cue.maxWidth ?? rawLineWidth));
  const scale = rawLineWidth > lineWidth * 0.94 ? (lineWidth * 0.94) / rawLineWidth : 1;
  const scaledWidths = widths.map((width) => width * scale);
  let cursor = lineWidth / 2 - scaledWidths.reduce((sum, width) => sum + width, 0) / 2;
  const centers = scaledWidths.map((width) => {
    const center = cursor + width / 2;
    cursor += width;
    return center;
  });

  const currentToken = visibleTokens[active];
  const nextIndex = Math.min(count - 1, active + 1);
  const localSeconds = localFrame / fps;
  const fallbackStart = (cue.end - cue.start) * active / Math.max(1, count);
  const fallbackEnd = (cue.end - cue.start) * (active + 1) / Math.max(1, count);
  const tokenStart = currentToken.start ?? fallbackStart;
  const tokenEnd = currentToken.end ?? fallbackEnd;
  const tokenDuration = Math.max(0.001, tokenEnd - tokenStart);
  const progress = clamp01((localSeconds - tokenStart) / tokenDuration);
  const smoothProgress = 0.5 - Math.cos(progress * Math.PI) * 0.5;
  const currentX = centers[active] ?? lineWidth / 2;
  const nextX = centers[nextIndex] ?? currentX;
  const x = currentX + (nextX - currentX) * smoothProgress;
  const fontSize = Number(currentToken.style.fontSize ?? cue.style.fontSize ?? 64);
  const travelHeight = cue.effect.badgeTravelHeight ?? Math.max(12, fontSize * 0.28);
  const y = -Math.sin(progress * Math.PI) * travelHeight;
  const tokenFrame = localFrame - Math.round(tokenStart * fps);
  return {x, y, tokenFrame};
};

const SubtitleBadge: React.FC<{
  shape?: string;
  color?: string;
  background?: string;
  size: number;
  text?: string;
  frame: number;
  fps: number;
  tokenFrame: number;
  spinDegrees?: number;
  spinDuration?: number;
  spinWobble?: number;
}> = ({shape = 'dot', color, background, size, text, frame, fps, tokenFrame, spinDegrees, spinDuration, spinWobble}) => {
  const badgeFrame = Math.max(0, tokenFrame);
  const pop = spring({
    frame: badgeFrame,
    fps,
    config: shape === 'heart'
      ? {damping: 6, stiffness: 230, mass: 0.45}
      : {damping: 8, stiffness: 210, mass: 0.48},
    durationInFrames: Math.round(0.38 * fps),
  });
  const containerSize = Math.round(size * (shape === 'coin' ? 1.22 : 1.72));
  const lift = interpolate(pop, [0, 1], [20, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const floatY = Math.sin(frame * 0.56) * -7;
  const driftX = Math.sin(frame * 0.38) * (shape === 'heart' ? 6 : 3);
  const spinDurationFrames = Math.max(1, Math.round((spinDuration ?? 0.95) * fps));
  const spinProgress = clamp01(badgeFrame / spinDurationFrames);
  const spinEase = 1 - Math.pow(1 - spinProgress, 3);
  const heartSpinStart = -38;
  const heartSpinEnd = spinDegrees ?? 420;
  const heartWobble = Math.sin((badgeFrame + frame * 0.2) * 0.46) * (spinWobble ?? 12);
  const rotate = shape === 'heart'
    ? heartSpinStart + (heartSpinEnd - heartSpinStart) * spinEase + heartWobble
    : shape === 'coin'
      ? frame * 9
      : Math.sin(frame * 0.28) * 12;
  const scaleValue = interpolate(pop, [0, 0.7, 1], [0.48, 1.18, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const effectiveColor = color ?? (shape === 'heart' ? '#FF4D8D' : '#FFE456');

  const containerStyle: React.CSSProperties = {
    position: 'absolute',
    left: '50%',
    top: `-${containerSize + 6}px`,
    width: containerSize,
    height: containerSize,
    transform: `translateX(-50%) translate(${driftX}px, ${lift + floatY}px) rotate(${rotate}deg) scale(${scaleValue})`,
    transformOrigin: '50% 58%',
    WebkitTextStroke: '0px transparent',
    pointerEvents: 'none',
    zIndex: 10,
  };

  if (shape === 'heart') {
    const renderHeart = (opacity: number, transform: string, blur = 0) => (
      <svg
        viewBox="0 0 64 58"
        style={{
          width: size,
          height: Math.round(size * 0.92),
          opacity,
          transform,
          filter: blur ? `blur(${blur}px)` : undefined,
          overflow: 'visible',
        }}
      >
        <path
          d="M32 54C17.2 42.1 4 31 4 17.2C4 8.9 10.4 3 18.1 3C23.1 3 28 5.7 32 10.5C36 5.7 40.9 3 45.9 3C53.6 3 60 8.9 60 17.2C60 31 46.8 42.1 32 54Z"
          fill={effectiveColor}
          stroke="rgba(255,255,255,0.72)"
          strokeWidth="2.6"
          strokeLinejoin="round"
        />
        <ellipse
          cx="21"
          cy="15"
          rx="6.8"
          ry="4.3"
          fill="rgba(255,255,255,0.38)"
          transform="rotate(-28 21 15)"
        />
        <path
          d="M47 12C51.4 14.1 53.7 18.2 52.8 23.3"
          fill="none"
          stroke="rgba(140,0,48,0.22)"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
      </svg>
    );
    return (
      <span style={containerStyle} aria-hidden="true">
        {[3, 2, 1].map((trailIndex) => (
          <span
            key={`heart-trail-${trailIndex}`}
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              opacity: 0.11 + trailIndex * 0.055,
            }}
          >
            {renderHeart(1, `translate(${trailIndex * -4}px, ${trailIndex * 5}px) rotate(${-trailIndex * 13}deg) scale(${1 - trailIndex * 0.045})`, 0.8)}
          </span>
        ))}
        <span
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            filter: `drop-shadow(0 3px 0 rgba(0,0,0,0.24)) drop-shadow(0 0 ${Math.round(size * 0.22)}px ${effectiveColor})`,
          }}
        >
          {renderHeart(1, 'translate(0, 0)')}
        </span>
      </span>
    );
  }

  if (shape === 'coin') {
    const coinSize = size;
    return (
      <span style={containerStyle} aria-hidden="true">
        <span
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: coinSize,
            height: coinSize,
            transform: 'translate(-50%, -50%)',
            borderRadius: '999px',
            background: background ?? 'radial-gradient(circle at 30% 24%, #FFF8CC 0%, #FFE066 30%, #E9A900 68%, #9B6100 100%)',
            border: '1px solid rgba(255,255,255,0.62)',
            boxShadow: '0 4px 0 rgba(0,0,0,0.24), 0 0 12px rgba(255,210,64,0.44), inset 0 2px 0 rgba(255,255,255,0.55)',
            overflow: 'hidden',
          }}
        >
          <span
            style={{
              position: 'absolute',
              inset: '18%',
              borderRadius: '999px',
              border: '2px solid rgba(255,255,255,0.45)',
              boxShadow: 'inset 0 0 4px rgba(146,85,0,0.28)',
            }}
          />
          <span
            style={{
              position: 'absolute',
              left: '18%',
              top: '17%',
              width: '42%',
              height: '17%',
              borderRadius: '999px',
              background: 'rgba(255,255,255,0.58)',
              transform: 'rotate(-21deg)',
              filter: 'blur(0.8px)',
            }}
          />
          <span
            style={{
              position: 'absolute',
              right: '18%',
              bottom: '18%',
              width: '12%',
              height: '12%',
              borderRadius: '999px',
              background: 'rgba(255,255,255,0.42)',
            }}
          />
        </span>
      </span>
    );
  }

  const glyph = text || (shape === 'spark' ? '✦' : '');
  return (
    <span style={containerStyle} aria-hidden="true">
      <span
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: shape === 'dot' ? size : '100%',
          height: shape === 'dot' ? size : '100%',
          left: shape === 'dot' ? '50%' : 0,
          top: shape === 'dot' ? '50%' : 0,
          transform: shape === 'dot' ? 'translate(-50%, -50%)' : undefined,
          borderRadius: '999px',
          background: shape === 'dot' ? (background ?? effectiveColor) : 'transparent',
          color: effectiveColor,
          fontSize: shape === 'spark' ? size : Math.round(size * 0.56),
          fontWeight: 900,
          lineHeight: `${size}px`,
          boxShadow: shape === 'dot' ? '0 3px 0 rgba(0,0,0,0.25)' : 'none',
          filter: shape === 'spark' ? `drop-shadow(0 0 ${Math.round(size * 0.32)}px ${effectiveColor})` : 'none',
        }}
      >
        {glyph}
      </span>
    </span>
  );
};

const TravellingSubtitleBadge: React.FC<{
  cue: SubtitleCue;
  tokens: Token[];
  localFrame: number;
  fps: number;
}> = ({cue, tokens, localFrame, fps}) => {
  const badgeShape = cue.effect.badgeShape ?? cue.effect.preset;
  const badgeSize = cue.effect.badgeSize ?? 34;
  const badgeText = cue.effect.badgeText ?? '♥';
  const state = travellingBadgeState(cue, tokens, localFrame, fps);
  return (
    <span
      aria-hidden="true"
      style={{
        position: 'absolute',
        left: state.x,
        top: 0,
        width: 1,
        height: 1,
        transform: `translateY(${state.y}px)`,
        pointerEvents: 'none',
        zIndex: 30,
      }}
    >
      <SubtitleBadge
        shape={badgeShape}
        color={cue.effect.badgeColor ?? '#FF4D8D'}
        background={cue.effect.badgeBackground}
        size={badgeSize}
        text={badgeText}
        frame={localFrame}
        fps={fps}
        tokenFrame={state.tokenFrame}
        spinDegrees={cue.effect.badgeSpinDegrees}
        spinDuration={cue.effect.badgeSpinDuration}
        spinWobble={cue.effect.badgeSpinWobble}
      />
    </span>
  );
};

const SubtitleCueView: React.FC<{cue: SubtitleCue}> = ({cue}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const localFrame = Math.max(0, frame);
  const tokens = useMemo(() => buildTokens(cue), [cue]);
  const active = activeIndex(cue, tokens, localFrame, fps);
  const wholeShake = cue.effect.type === 'shake_emphasis'
    ? Math.sin(localFrame * 1.7) * (cue.effect.amplitude ?? 2)
    : 0;
  const placement = positionStyle(cue, {width, height});
  const placementTransform = String(placement.transform ?? '');
  const activeBadgeShape = cue.effect.badgeShape ?? cue.effect.preset;
  const useTravellingHeartBadge = cue.effect.type === 'bounce_badge' && activeBadgeShape === 'heart';

  if (cue.effect.type === 'stack_pop') {
    const motion = tokenTransform(cue, 0, 1, localFrame, fps);
    const stackColors = cue.effect.stackColors?.length
      ? cue.effect.stackColors
      : ['#00E5FF', '#FF4D8D'];
    const stackOffset = cue.effect.stackOffset ?? 5;
    const stackOpacity = cue.effect.stackOpacity ?? 0.78;
    const renderTextLine = (layerColor?: string) => tokens.map((token, index) => {
      const color = layerColor ?? token.style.color ?? cue.style.color ?? '#FFFFFF';
      const layerStyle = textStyle({...cue.style, ...token.style, color}, cue.align);
      return (
        <span
          key={`${cue.id}-stack-block-${layerColor ?? 'main'}-${index}-${token.text}`}
          style={{
            ...layerStyle,
            display: token.text.trim() ? 'inline-block' : 'inline',
            margin: token.text.trim() ? '0 0.02em' : undefined,
            WebkitTextStroke: layerColor
              ? '0px transparent'
              : layerStyle.WebkitTextStroke,
          }}
        >
          {token.text}
        </span>
      );
    });

    return (
      <div
        style={{
          position: 'absolute',
          ...placement,
          ...textStyle(cue.style, cue.align),
          ...boxStyle(cue.style),
          transform: `${placementTransform} translateX(${wholeShake}px)`,
        }}
      >
        <span
          style={{
            position: 'relative',
            display: 'inline-block',
            ...motion,
          }}
        >
          {stackColors.slice(0, 3).map((stackColor, layerIndex) => {
            const direction = layerIndex % 2 === 0 ? -1 : 1;
            const layerOffset = stackOffset * (layerIndex + 1);
            return (
              <span
                key={`${cue.id}-stack-layer-${layerIndex}`}
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  opacity: Math.max(0, stackOpacity - layerIndex * 0.2),
                  transform: `translate(${direction * layerOffset}px, ${layerOffset}px)`,
                  pointerEvents: 'none',
                  zIndex: layerIndex,
                  filter: 'drop-shadow(0 2px 0 rgba(0,0,0,0.18))',
                }}
              >
                {renderTextLine(stackColor)}
              </span>
            );
          })}
          <span style={{position: 'relative', zIndex: 8}}>
            {renderTextLine()}
          </span>
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'absolute',
        ...placement,
        ...textStyle(cue.style, cue.align),
        ...boxStyle(cue.style),
        transform: `${placementTransform} translateX(${wholeShake}px)`,
      }}
    >
      {useTravellingHeartBadge ? (
        <TravellingSubtitleBadge cue={cue} tokens={tokens} localFrame={localFrame} fps={fps} />
      ) : null}
      {tokens.map((token, index) => {
        const motion = tokenTransform(cue, index, tokens.length, localFrame, fps, token);
        const highlighted = cue.effect.type === 'karaoke_highlight' && index <= active;
        const color = token.style.brandWord
          ? token.style.color ?? '#3BFD42'
          : highlighted
          ? cue.effect.activeColor ?? cue.style.activeColor ?? '#FFE456'
          : cue.effect.inactiveColor ?? token.style.inactiveColor ?? token.style.color ?? cue.style.color ?? '#FFFFFF';
        const showBadge = cue.effect.type === 'bounce_badge' && !useTravellingHeartBadge && index === active;
        const badgeShape = cue.effect.badgeShape ?? cue.effect.preset;
        const badgeSize = cue.effect.badgeSize ?? (badgeShape === 'heart' ? 30 : 24);
        const badgeIsGlyph = badgeShape === 'heart' || badgeShape === 'spark';
        const badgeText = cue.effect.badgeText ?? (badgeShape === 'heart' ? '♥' : badgeShape === 'spark' ? '✦' : '');
        const totalFrames = Math.max(1, Math.round((cue.end - cue.start) * fps));
        const badgeTokenStartFrame = token.start == null
          ? Math.floor((index / Math.max(1, tokens.length)) * totalFrames)
          : Math.round(token.start * fps);
        return (
          <span
            key={`${cue.id}-${index}-${token.text}`}
            style={{
              position: 'relative',
              display: token.text.trim() ? 'inline-block' : 'inline',
              margin: token.text.trim() ? '0 0.04em' : undefined,
              ...textStyle({...cue.style, ...token.style, color}, cue.align),
              ...motion,
            }}
          >
            {showBadge ? (
              <SubtitleBadge
                shape={badgeShape}
                color={badgeIsGlyph ? cue.effect.badgeColor ?? '#FF4D8D' : cue.effect.badgeColor ?? '#FFE456'}
                background={cue.effect.badgeBackground}
                size={badgeSize}
                text={badgeText}
                frame={localFrame}
                fps={fps}
                tokenFrame={localFrame - badgeTokenStartFrame}
                spinDegrees={cue.effect.badgeSpinDegrees}
                spinDuration={cue.effect.badgeSpinDuration}
                spinWobble={cue.effect.badgeSpinWobble}
              />
            ) : null}
            <span style={{position: 'relative', zIndex: 5}}>{token.text}</span>
          </span>
        );
      })}
    </div>
  );
};

const CueSequence: React.FC<{cue: SubtitleCue}> = ({cue}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(cue.start * fps);
  const durationInFrames = Math.max(1, Math.round((cue.end - cue.start) * fps));
  return (
    <Sequence from={from} durationInFrames={durationInFrames} premountFor={Math.min(fps, from)}>
      <SubtitleCueView cue={cue} />
    </Sequence>
  );
};

export const SubtitleComposition: React.FC<SubtitleCompositionProps> = ({
  mode,
  canvas,
  base,
  fonts,
  subtitles,
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
      <FontLoader fonts={fonts} />
      {mode === 'composite' && base ? (
        <OffthreadVideo src={staticFile(base.src)} style={baseStyle} />
      ) : null}
      {subtitles.map((cue) => (
        <CueSequence key={cue.id} cue={cue} />
      ))}
    </AbsoluteFill>
  );
};
