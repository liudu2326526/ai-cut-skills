export type RenderMode = 'composite' | 'alpha';

export type CanvasConfig = {
  width: number;
  height: number;
  fps: number;
  backgroundColor: string;
  baseFit: 'cover' | 'contain' | 'stretch';
};

export type BaseVideo = {
  src: string;
};

export type FontAsset = {
  family: string;
  src: string | null;
  weight?: string;
  style?: string;
};

export type SubtitlePosition =
  | 'lower_center'
  | 'middle_lower'
  | 'center'
  | 'top_center'
  | 'bottom_center'
  | 'custom';

export type TextStyle = {
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: number | string;
  color?: string;
  strokeColor?: string;
  strokeWidth?: number;
  shadowColor?: string;
  shadowBlur?: number;
  backgroundColor?: string;
  paddingX?: number;
  paddingY?: number;
  borderRadius?: number;
  lineHeight?: number;
  letterSpacing?: number;
  activeColor?: string;
  inactiveColor?: string;
  brandWord?: boolean;
};

export type SubtitleSpan = {
  text: string;
  style?: TextStyle;
};

export type SubtitleTokenTiming = {
  text: string;
  start: number;
  end: number;
  style?: TextStyle;
};

export type SubtitleEffectType =
  | 'plain'
  | 'fade_slide'
  | 'pop_word'
  | 'drop_word'
  | 'stack_pop'
  | 'karaoke_highlight'
  | 'bounce_badge'
  | 'typewriter'
  | 'shake_emphasis';

export type SubtitleEffect = {
  type: SubtitleEffectType;
  preset: string;
  duration: number;
  granularity: 'char' | 'word';
  stagger: number;
  activeColor?: string;
  inactiveColor?: string;
  badgeText?: string;
  badgeShape?: 'dot' | 'coin' | 'heart' | 'spark';
  badgeColor?: string;
  badgeBackground?: string;
  badgeSize?: number;
  badgeSpinDegrees?: number;
  badgeSpinDuration?: number;
  badgeSpinWobble?: number;
  amplitude?: number;
  stackColors?: string[];
  stackOffset?: number;
  stackOpacity?: number;
};

export type SubtitleCue = {
  id: string;
  start: number;
  end: number;
  text: string;
  role?: string;
  position: SubtitlePosition;
  x?: number;
  y?: number;
  maxWidth: number;
  align: 'left' | 'center' | 'right';
  style: TextStyle;
  stylePreset?: string;
  spans: SubtitleSpan[];
  tokens: SubtitleTokenTiming[];
  syncMode: 'timed_tokens' | 'uniform';
  effect: SubtitleEffect;
  effectPreset?: string;
};

export type SubtitleCompositionProps = {
  mode: RenderMode;
  canvas: CanvasConfig;
  durationInSeconds: number;
  base: BaseVideo | null;
  fonts: FontAsset[];
  subtitles: SubtitleCue[];
};
