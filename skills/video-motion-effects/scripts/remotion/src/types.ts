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

export type EventLayout = {
  width: number;
  height: number;
  x: number;
  y: number;
  originX: number;
  originY: number;
  borderRadius: number;
};

export type DynamicShrinkEffect = {
  type: 'dynamic_shrink';
  preset: 'reference_first_v1' | 'reference_first_v2';
  duration: number;
  samples: number;
};

export type BottomRiseEffect = {
  type: 'bottom_rise';
  preset: 'reference_second_v1';
  duration: number;
};

export type PerspectiveSettleEffect = {
  type: 'perspective_settle';
  preset: 'reference_third_v3';
  duration: number;
  samples: number;
};

export type FlashStretchEffect = {
  type: 'flash_stretch';
  preset: 'reference_fourth_v1';
  duration: number;
};

export type PageCurlEffect = {
  type: 'page_curl';
  preset: 'webgl_page_curl_v1';
  duration: number;
  backTextureStrength: number;
};

export type MotionEffect =
  | DynamicShrinkEffect
  | BottomRiseEffect
  | PerspectiveSettleEffect
  | FlashStretchEffect
  | PageCurlEffect;

export type MotionEventBase = {
  name: string;
  src: string;
  kind: 'image';
  start: number;
  end: number;
  layout: EventLayout;
};

export type DynamicShrinkEvent = MotionEventBase & {effect: DynamicShrinkEffect};
export type BottomRiseEvent = MotionEventBase & {effect: BottomRiseEffect};
export type PerspectiveSettleEvent = MotionEventBase & {effect: PerspectiveSettleEffect};
export type FlashStretchEvent = MotionEventBase & {effect: FlashStretchEffect};
export type PageCurlEvent = MotionEventBase & {effect: PageCurlEffect};

export type MotionEvent =
  | DynamicShrinkEvent
  | BottomRiseEvent
  | PerspectiveSettleEvent
  | FlashStretchEvent
  | PageCurlEvent;

export type MotionCompositionProps = {
  mode: RenderMode;
  canvas: CanvasConfig;
  durationInSeconds: number;
  base: BaseVideo | null;
  events: MotionEvent[];
};
