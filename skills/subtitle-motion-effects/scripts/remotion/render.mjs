#!/usr/bin/env node

import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const ENTRY_POINT = path.join(ROOT, 'src', 'index.tsx');
const EFFECT_DEFINITIONS = {
  plain: {
    aliases: ['plain', 'none', '静态', '普通'],
    presets: ['default'],
    defaultPreset: 'default',
    defaultDuration: 0.01,
  },
  fade_slide: {
    aliases: ['fade_slide', '淡入上移', '淡入', '上移'],
    presets: ['soft'],
    defaultPreset: 'soft',
    defaultDuration: 0.24,
  },
  pop_word: {
    aliases: ['pop_word', '逐字弹跳', '逐词弹跳', '弹跳字'],
    presets: ['tiktok_pop'],
    defaultPreset: 'tiktok_pop',
    defaultDuration: 0.42,
  },
  drop_word: {
    aliases: ['drop_word', '落字入场', '从上往下出现', '下落出现', '掉字', 'fall_in', 'drop_in'],
    presets: ['soft_drop', 'bounce_drop'],
    defaultPreset: 'soft_drop',
    defaultDuration: 0.52,
  },
  stack_pop: {
    aliases: ['stack_pop', '叠加弹出', '叠层弹出', '叠影弹出', '弹出叠字'],
    presets: ['neon', 'candy', 'soda'],
    defaultPreset: 'neon',
    defaultDuration: 0.46,
  },
  karaoke_highlight: {
    aliases: ['karaoke_highlight', '卡拉ok高亮', '卡拉OK高亮', '逐字高亮', '扫字'],
    presets: ['gold_fill'],
    defaultPreset: 'gold_fill',
    defaultDuration: 0.01,
  },
  bounce_badge: {
    aliases: ['bounce_badge', '上方小标跳动', '跳动小标', '金币跳字', '爱心跳字'],
    presets: ['dot', 'coin', 'heart', 'spark'],
    defaultPreset: 'dot',
    defaultDuration: 0.42,
  },
  typewriter: {
    aliases: ['typewriter', '打字机', '逐字出现'],
    presets: ['notice'],
    defaultPreset: 'notice',
    defaultDuration: 0.75,
  },
  shake_emphasis: {
    aliases: ['shake_emphasis', '轻抖强调', '强调抖动'],
    presets: ['soft'],
    defaultPreset: 'soft',
    defaultDuration: 0.01,
  },
};
const STYLE_PRESETS = {
  standard_white: {
    aliases: ['standard_white', '标准白字', '白字黑边', 'white'],
    style: {color: '#FFFFFF', strokeColor: '#000000', strokeWidth: 3, shadowBlur: 0},
  },
  variety_yellow: {
    aliases: ['variety_yellow', '综艺黄字', '黄字', 'yellow'],
    style: {color: '#FFD700', strokeColor: '#000000', strokeWidth: 4, shadowBlur: 0},
  },
  boxed_white: {
    aliases: ['boxed_white', '黑底白字', '底框白字'],
    style: {
      color: '#FFFFFF',
      strokeColor: '#000000',
      strokeWidth: 0,
      shadowBlur: 0,
      backgroundColor: 'rgba(0,0,0,0.42)',
      paddingX: 18,
      paddingY: 8,
      borderRadius: 8,
    },
  },
  blue_glow: {
    aliases: ['blue_glow', '蓝色荧光', '蓝字青光'],
    style: {color: '#FFFFFF', strokeColor: '#0099FF', strokeWidth: 3, shadowColor: '#28D7FF', shadowBlur: 8},
  },
  red_highlight: {
    aliases: ['red_highlight', '红色高亮', '红字'],
    style: {color: '#FF3434', strokeColor: '#FFFFFF', strokeWidth: 3, shadowBlur: 0},
  },
  cyan_fashion: {
    aliases: ['cyan_fashion', '时尚青色', '青色', 'cyan'],
    style: {color: '#00FFFF', strokeColor: '#000000', strokeWidth: 3, shadowBlur: 0},
  },
  soda_green: {
    aliases: ['soda_green', '汽水绿', '品牌绿'],
    style: {color: '#3BFD42', strokeColor: '#071307', strokeWidth: 4, shadowBlur: 0, fontWeight: 900},
  },
  pink_heart: {
    aliases: ['pink_heart', '爱心粉', '粉色爱心'],
    style: {color: '#FFFFFF', strokeColor: '#FF4D8D', strokeWidth: 4, shadowColor: '#FF4D8D', shadowBlur: 5},
  },
  lyric_gold: {
    aliases: ['lyric_gold', '歌词金色', '金色歌词'],
    style: {color: '#FFFFFF', activeColor: '#FFE456', inactiveColor: '#FFFFFF', strokeColor: '#000000', strokeWidth: 3},
  },
  lyric_cyan: {
    aliases: ['lyric_cyan', '歌词青色', '青色歌词'],
    style: {color: '#DFFBFF', activeColor: '#35F4FF', inactiveColor: '#DFFBFF', strokeColor: '#071B22', strokeWidth: 3},
  },
  lyric_green: {
    aliases: ['lyric_green', '歌词绿色', '绿色高亮', '汽水绿色高亮'],
    style: {color: '#FFFFFF', activeColor: '#3BFD42', inactiveColor: '#FFFFFF', strokeColor: '#071307', strokeWidth: 3},
  },
  lyric_pink: {
    aliases: ['lyric_pink', '歌词粉色', '粉色高亮'],
    style: {color: '#FFFFFF', activeColor: '#FF63A5', inactiveColor: '#FFFFFF', strokeColor: '#240615', strokeWidth: 3},
  },
  lyric_orange: {
    aliases: ['lyric_orange', '歌词橙色', '橙色高亮'],
    style: {color: '#FFFFFF', activeColor: '#FF9F2E', inactiveColor: '#FFFFFF', strokeColor: '#2A1300', strokeWidth: 3},
  },
  lyric_violet: {
    aliases: ['lyric_violet', '歌词紫色', '紫色高亮'],
    style: {color: '#FFFFFF', activeColor: '#B982FF', inactiveColor: '#FFFFFF', strokeColor: '#12051F', strokeWidth: 3},
  },
  white_yellow: {
    aliases: ['white_yellow', '白字黄光', 'White & Yellow'],
    style: {color: '#FFFFFF', activeColor: '#FFE456', inactiveColor: '#FFFFFF', strokeColor: '#000000', strokeWidth: 3},
  },
  white_red: {
    aliases: ['white_red', '白字红光', 'White & Red'],
    style: {color: '#FFFFFF', activeColor: '#FF3434', inactiveColor: '#FFFFFF', strokeColor: '#000000', strokeWidth: 3},
  },
  blue_cyan: {
    aliases: ['blue_cyan', '蓝字青光', 'Blue & Cyan'],
    style: {
      color: '#FFFFFF',
      activeColor: '#35F4FF',
      inactiveColor: '#FFFFFF',
      strokeColor: '#0099FF',
      strokeWidth: 3,
      shadowColor: '#28D7FF',
      shadowBlur: 8,
    },
  },
};
const EFFECT_PRESETS = {
  pop_bold: {
    aliases: ['pop_bold', '综艺弹字', '弹跳字幕'],
    effect: {type: 'pop_word', preset: 'tiktok_pop', duration: 0.42, granularity: 'char', stagger: 0.035},
  },
  drop_in: {
    aliases: ['drop_in', '落字入场', '从上往下出现', '下落字幕', '掉字字幕'],
    effect: {type: 'drop_word', preset: 'soft_drop', duration: 0.52, granularity: 'char', stagger: 0.032},
  },
  drop_bounce: {
    aliases: ['drop_bounce', '弹性落字', '旋转落字'],
    effect: {type: 'drop_word', preset: 'bounce_drop', duration: 0.58, granularity: 'char', stagger: 0.035},
  },
  stack_pop: {
    aliases: ['stack_pop', '叠加弹出', '叠层弹出', '叠影弹字', '弹出叠字'],
    effect: {
      type: 'stack_pop',
      preset: 'neon',
      duration: 0.46,
      granularity: 'char',
      stagger: 0.035,
      stackColors: ['#00E5FF', '#FF4D8D'],
      stackOffset: 5,
      stackOpacity: 0.78,
    },
  },
  heart_jump: {
    aliases: ['heart_jump', '爱心跳字', '爱心字幕', '旋转爱心', '爱心残影'],
    effect: {
      type: 'bounce_badge',
      preset: 'heart',
      duration: 0.44,
      granularity: 'char',
      stagger: 0.04,
      badgeShape: 'heart',
      badgeColor: '#FF4D8D',
      badgeSize: 34,
      badgeSpinDegrees: 720,
      badgeSpinDuration: 0.68,
      badgeSpinWobble: 16,
    },
  },
  coin_jump: {
    aliases: ['coin_jump', '金币跳字', '金币字幕'],
    effect: {
      type: 'bounce_badge',
      preset: 'coin',
      duration: 0.44,
      granularity: 'char',
      stagger: 0.04,
      badgeShape: 'coin',
      badgeColor: '#FFE456',
      badgeSize: 30,
    },
  },
  spark_jump: {
    aliases: ['spark_jump', '星光跳字', '闪光跳字'],
    effect: {
      type: 'bounce_badge',
      preset: 'spark',
      duration: 0.42,
      granularity: 'char',
      stagger: 0.04,
      badgeShape: 'spark',
      badgeColor: '#FFE456',
      badgeSize: 28,
    },
  },
  lyrics_gold: {
    aliases: ['lyrics_gold', '歌词金色', '类似歌词', '歌词高亮'],
    effect: {
      type: 'karaoke_highlight',
      preset: 'gold_fill',
      duration: 0.01,
      granularity: 'char',
      stagger: 0.035,
      activeColor: '#FFE456',
      inactiveColor: '#FFFFFF',
    },
  },
  lyrics_cyan: {
    aliases: ['lyrics_cyan', '歌词青色'],
    effect: {
      type: 'karaoke_highlight',
      preset: 'gold_fill',
      duration: 0.01,
      granularity: 'char',
      stagger: 0.035,
      activeColor: '#35F4FF',
      inactiveColor: '#DFFBFF',
    },
  },
  lyrics_green: {
    aliases: ['lyrics_green', '歌词绿色', '汽水绿高亮'],
    effect: {
      type: 'karaoke_highlight',
      preset: 'gold_fill',
      duration: 0.01,
      granularity: 'char',
      stagger: 0.035,
      activeColor: '#3BFD42',
      inactiveColor: '#FFFFFF',
    },
  },
  lyrics_pink: {
    aliases: ['lyrics_pink', '歌词粉色', '粉色扫字'],
    effect: {
      type: 'karaoke_highlight',
      preset: 'gold_fill',
      duration: 0.01,
      granularity: 'char',
      stagger: 0.035,
      activeColor: '#FF63A5',
      inactiveColor: '#FFFFFF',
    },
  },
  lyrics_orange: {
    aliases: ['lyrics_orange', '歌词橙色', '橙色扫字'],
    effect: {
      type: 'karaoke_highlight',
      preset: 'gold_fill',
      duration: 0.01,
      granularity: 'char',
      stagger: 0.035,
      activeColor: '#FF9F2E',
      inactiveColor: '#FFFFFF',
    },
  },
  lyrics_violet: {
    aliases: ['lyrics_violet', '歌词紫色', '紫色扫字'],
    effect: {
      type: 'karaoke_highlight',
      preset: 'gold_fill',
      duration: 0.01,
      granularity: 'char',
      stagger: 0.035,
      activeColor: '#B982FF',
      inactiveColor: '#FFFFFF',
    },
  },
  notice_typewriter: {
    aliases: ['notice_typewriter', '通知打字', '打字机'],
    effect: {type: 'typewriter', preset: 'notice', duration: 0.75, granularity: 'char', stagger: 0.03},
  },
  glitch_shake: {
    aliases: ['glitch_shake', '故障轻抖', '抖动强调'],
    effect: {type: 'shake_emphasis', preset: 'soft', duration: 0.01, granularity: 'char', stagger: 0.035, amplitude: 2},
  },
};
const EFFECT_ALIASES = new Map(
  Object.entries(EFFECT_DEFINITIONS).flatMap(([type, definition]) =>
    definition.aliases.map((alias) => [alias.toLowerCase(), type]),
  ),
);
const STYLE_PRESET_ALIASES = new Map(
  Object.entries(STYLE_PRESETS).flatMap(([name, preset]) =>
    preset.aliases.map((alias) => [alias.toLowerCase(), name]),
  ),
);
const EFFECT_PRESET_ALIASES = new Map(
  Object.entries(EFFECT_PRESETS).flatMap(([name, preset]) =>
    preset.aliases.map((alias) => [alias.toLowerCase(), name]),
  ),
);
const FONT_EXTENSIONS = new Set(['.ttf', '.otf', '.woff', '.woff2']);

class SubtitleMotionError extends Error {}

const print = (value) => process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);

const expandPath = (value) => {
  if (typeof value !== 'string' || value.length === 0) {
    throw new SubtitleMotionError('Expected a non-empty path');
  }
  const expanded = value === '~' || value.startsWith('~/')
    ? path.join(os.homedir(), value.slice(2))
    : value;
  return path.resolve(expanded);
};

const parseArgs = (argv) => {
  const command = argv[2];
  const flags = {};
  for (let index = 3; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) throw new SubtitleMotionError(`Unexpected argument: ${token}`);
    const key = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith('--')) {
      flags[key] = true;
    } else {
      flags[key] = next;
      index += 1;
    }
  }
  return {command, flags};
};

const requireFlag = (flags, key) => {
  const value = flags[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new SubtitleMotionError(`Missing required option: --${key}`);
  }
  return value;
};

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: 'utf8',
    stdio: options.inherit ? 'inherit' : 'pipe',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new SubtitleMotionError(
      `${command} failed (${result.status})\n${result.stdout ?? ''}${result.stderr ?? ''}`.trim(),
    );
  }
  return result;
};

const findOnPath = (command) => {
  const paths = String(process.env.PATH ?? '').split(path.delimiter).filter(Boolean);
  const extensions = process.platform === 'win32' ? ['.cmd', '.exe', '.bat', ''] : [''];
  for (const dir of paths) {
    for (const extension of extensions) {
      const candidate = path.join(dir, `${command}${extension}`);
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return null;
};

const findFfprobe = () => {
  const candidates = [
    process.env.FFPROBE_PATH,
    findOnPath('ffprobe'),
    path.join(process.cwd(), 'ffprobe.exe'),
    path.join(process.cwd(), 'bin', 'ffprobe.exe'),
    path.join(process.cwd(), 'tools', 'ffmpeg', 'bin', 'ffprobe.exe'),
    path.join(process.cwd(), 'material_remix_desktop_source', 'bin', 'ffprobe.exe'),
    path.join(ROOT, '..', '..', '..', '..', '..', 'material_remix_desktop_source', 'bin', 'ffprobe.exe'),
    path.join(os.homedir(), '.workbuddy', 'bin', 'ffprobe.exe'),
  ].filter(Boolean).map((candidate) => path.resolve(candidate));
  return candidates.find((candidate) => fs.existsSync(candidate)) ?? null;
};

const npmInvocation = () => {
  const bundledCli = path.join(path.dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js');
  if (fs.existsSync(bundledCli)) return {command: process.execPath, args: [bundledCli]};
  return {command: findOnPath('npm') ?? 'npm', args: []};
};

const ffprobe = (filePath) => {
  if (!fs.existsSync(filePath)) throw new SubtitleMotionError(`File not found: ${filePath}`);
  const binary = findFfprobe();
  if (!binary) {
    throw new SubtitleMotionError('ffprobe not found; set FFPROBE_PATH or add ffprobe to PATH');
  }
  const result = run(binary, [
    '-v', 'error',
    '-show_entries',
    'format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,sample_rate,channels',
    '-of', 'json',
    filePath,
  ]);
  const data = JSON.parse(result.stdout);
  const video = data.streams?.find((stream) => stream.codec_type === 'video') ?? {};
  const audio = data.streams?.find((stream) => stream.codec_type === 'audio') ?? {};
  return {
    path: filePath,
    duration: Number(data.format?.duration ?? 0),
    size: Number(data.format?.size ?? 0),
    bitRate: Number(data.format?.bit_rate ?? 0),
    width: Number(video.width ?? 0),
    height: Number(video.height ?? 0),
    videoCodec: video.codec_name ?? null,
    pixelFormat: video.pix_fmt ?? null,
    audioCodec: audio.codec_name ?? null,
    sampleRate: audio.sample_rate ? Number(audio.sample_rate) : null,
    channels: audio.channels ?? null,
  };
};

const containsPlaceholder = (value) => {
  if (Array.isArray(value)) return value.some(containsPlaceholder);
  if (value && typeof value === 'object') return Object.values(value).some(containsPlaceholder);
  return typeof value === 'string' && /^<.*>$/.test(value.trim());
};

const positive = (value, field) => {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) throw new SubtitleMotionError(`${field} must be positive`);
  return number;
};

const parseStringList = (value) => {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item).trim())
      .filter((item) => item.length > 0);
  }
  if (typeof value !== 'string') return [];
  return value
    .replace(/，/g, ',')
    .replace(/\|/g, ',')
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
};

const numberOrNull = (value, field) => {
  if (value == null) return null;
  const number = Number(value);
  if (!Number.isFinite(number)) throw new SubtitleMotionError(`${field} must be numeric`);
  return number;
};

const timeValueOrNull = (item, keys, field, defaultUnit = null) => {
  for (const key of keys) {
    if (item[key] == null) continue;
    const number = Number(item[key]);
    if (!Number.isFinite(number)) throw new SubtitleMotionError(`${field}.${key} must be numeric`);
    const unit = String(item.timeUnit ?? item.time_unit ?? defaultUnit ?? '').toLowerCase();
    if (unit === 'ms' || unit === 'millisecond' || unit === 'milliseconds') return number / 1000;
    if (unit === 's' || unit === 'sec' || unit === 'second' || unit === 'seconds') return number;
    if (key === 'start_time' || key === 'end_time' || key === 'startTime' || key === 'endTime') {
      return Math.abs(number) > 100 ? number / 1000 : number;
    }
    return number;
  }
  return null;
};

const resolveFromRoot = (assetRoot, value, field) => {
  if (typeof value !== 'string' || value.length === 0) {
    throw new SubtitleMotionError(`${field} must be a non-empty path`);
  }
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(assetRoot, value);
};

const normalizeStyle = (style = {}, fallback = {}) => {
  if (!style || typeof style !== 'object') return {...fallback};
  const merged = {...fallback, ...style};
  const numericFields = ['fontSize', 'strokeWidth', 'shadowBlur', 'lineHeight', 'letterSpacing', 'paddingX', 'paddingY', 'borderRadius'];
  for (const field of numericFields) {
    if (merged[field] != null) {
      const number = Number(merged[field]);
      if (!Number.isFinite(number)) throw new SubtitleMotionError(`style.${field} must be numeric`);
      merged[field] = number;
    }
  }
  return merged;
};

const resolveBrandStyle = (branding, fallbackStyle = {}) => {
  const rawStyle = normalizeStyle(branding?.style ?? {});
  const scaleRaw = Number(branding?.scale ?? branding?.fontScale ?? branding?.sizeScale ?? 1.15);
  const scale = Number.isFinite(scaleRaw) && scaleRaw > 0 ? scaleRaw : 1.15;
  const baseFontSize = Number(rawStyle.fontSize ?? fallbackStyle.fontSize ?? 0);
  const fontSize = rawStyle.fontSize ?? (baseFontSize > 0 ? Math.round(baseFontSize * scale) : undefined);
  const baseStroke = Number(fallbackStyle.strokeWidth ?? 3);
  return normalizeStyle({
    ...fallbackStyle,
    ...rawStyle,
    fontSize,
    color: rawStyle.color ?? '#3BFD42',
    strokeColor: rawStyle.strokeColor ?? '#071307',
    strokeWidth: rawStyle.strokeWidth ?? Math.max(3, Math.round(baseStroke * 1.2)),
    fontWeight: rawStyle.fontWeight ?? 900,
    shadowBlur: rawStyle.shadowBlur ?? 0,
    letterSpacing: rawStyle.letterSpacing ?? fallbackStyle.letterSpacing ?? 0,
    brandWord: true,
  });
};

const resolveStylePreset = (name, field) => {
  if (name == null || name === '') return {};
  const key = STYLE_PRESET_ALIASES.get(String(name).toLowerCase());
  if (!key) throw new SubtitleMotionError(`Unsupported ${field}: ${name}`);
  return STYLE_PRESETS[key].style;
};

const resolveEffectPreset = (name, field) => {
  if (name == null || name === '') return {};
  const key = EFFECT_PRESET_ALIASES.get(String(name).toLowerCase());
  if (!key) throw new SubtitleMotionError(`Unsupported ${field}: ${name}`);
  return EFFECT_PRESETS[key].effect;
};

const STATIC_CUE_ROLES = new Set(['disclaimer', 'warning', 'legal', 'notice']);
const DISCLAIMER_TEXT_HINTS = [
  '本视频为广告创意',
  '具体奖励金额以实际情况为准',
  '免责声明',
  '警示语',
  '警告语',
];

const cueRole = (cue) => String(cue?.role ?? cue?.kind ?? cue?.label ?? cue?.tag ?? '').trim().toLowerCase();

const shouldUsePlainEffect = (cue, text) => {
  const role = cueRole(cue);
  if (STATIC_CUE_ROLES.has(role)) return true;
  const cueText = String(text ?? '').trim();
  return DISCLAIMER_TEXT_HINTS.some((hint) => cueText.includes(hint));
};

const makeBrandSpans = (text, branding, fallbackStyle) => {
  return applyBrandingToSpans([{text, style: {}}], branding, fallbackStyle);
};

const brandRangesForText = (text, words) => {
  const sorted = [...words].sort((a, b) => b.length - a.length);
  const ranges = [];
  let index = 0;
  while (index < text.length) {
    const matched = sorted.find((word) => text.startsWith(word, index));
    if (matched) {
      ranges.push({start: index, end: index + matched.length});
      index += matched.length;
    } else {
      index += 1;
    }
  }
  return ranges;
};

const tokenTouchesBrandRange = (ranges, start, end) =>
  start >= 0 && ranges.some((range) => start < range.end && end > range.start);

const applyBrandingToSpans = (spans, branding, fallbackStyle = {}) => {
  const words = Array.isArray(branding?.words)
    ? branding.words.filter((word) => typeof word === 'string' && word.length > 0)
    : [];
  if (!words.length) return spans;

  const fullText = spans.map((span) => span.text).join('');
  const brandRanges = brandRangesForText(fullText, words);
  if (!brandRanges.length) return spans;

  const brandStyle = resolveBrandStyle(branding, fallbackStyle);
  const output = [];
  let globalIndex = 0;
  for (const span of spans) {
    const boundaries = new Set([0, span.text.length]);
    for (const range of brandRanges) {
      const localStart = Math.max(0, range.start - globalIndex);
      const localEnd = Math.min(span.text.length, range.end - globalIndex);
      if (localStart < localEnd) {
        boundaries.add(localStart);
        boundaries.add(localEnd);
      }
    }

    const sortedBoundaries = [...boundaries].sort((a, b) => a - b);
    for (let index = 0; index < sortedBoundaries.length - 1; index += 1) {
      const start = sortedBoundaries[index];
      const end = sortedBoundaries[index + 1];
      const text = span.text.slice(start, end);
      if (!text) continue;
      const inBrandRange = tokenTouchesBrandRange(brandRanges, globalIndex + start, globalIndex + end);
      output.push({
        text,
        // 手动 spans 也不能覆盖品牌字体；品牌规则要最后生效。
        style: inBrandRange ? {...(span.style ?? {}), ...brandStyle} : span.style,
      });
    }
    globalIndex += span.text.length;
  }
  return output;
};

const rootFrontendTokens = (frontend) => {
  if (!frontend || typeof frontend !== 'object') return [];
  const raw = frontend.words ?? frontend.tokens ?? frontend.frontend_words ?? frontend.frontendWords;
  return Array.isArray(raw) ? raw : [];
};

const normalizeTokenTimings = ({rawCue, rootFrontend, cueStart, cueEnd, cueText, branding, cueStyle, index}) => {
  let rawTokens = rawCue.tokens ?? rawCue.words ?? rawCue.tokenTimings ?? rawCue.token_timings
    ?? rawCue.frontend?.words ?? rawCue.frontend?.tokens;
  if ((!Array.isArray(rawTokens) || rawTokens.length === 0) && rootFrontend) {
    rawTokens = rootFrontendTokens(rootFrontend).filter((token) => {
      if (!token || typeof token !== 'object') return false;
      const startRaw = timeValueOrNull(
        token,
        ['start', 'startTime', 'start_time', 'begin', 'beginTime', 'begin_time'],
        'frontend.words',
      );
      const endRaw = timeValueOrNull(
        token,
        ['end', 'endTime', 'end_time', 'stop', 'stopTime', 'stop_time'],
        'frontend.words',
      );
      return startRaw != null && endRaw != null && startRaw < cueEnd + 0.05 && endRaw > cueStart - 0.05;
    });
  }
  if (!Array.isArray(rawTokens) || rawTokens.length === 0) return [];

  const cueDuration = cueEnd - cueStart;
  const normalized = rawTokens.map((token, tokenIndex) => {
    if (!token || typeof token !== 'object') {
      throw new SubtitleMotionError(`subtitles[${index}].tokens[${tokenIndex}] must be an object`);
    }
    const text = String(token.text ?? token.word ?? token.value ?? '').trim();
    if (!text) return null;
    const startRaw = timeValueOrNull(
      token,
      ['start', 'startTime', 'start_time', 'begin', 'beginTime', 'begin_time'],
      `subtitles[${index}].tokens[${tokenIndex}]`,
    );
    const endRaw = timeValueOrNull(
      token,
      ['end', 'endTime', 'end_time', 'stop', 'stopTime', 'stop_time'],
      `subtitles[${index}].tokens[${tokenIndex}]`,
    );
    if (startRaw == null || endRaw == null || endRaw <= startRaw) {
      throw new SubtitleMotionError(`subtitles[${index}].tokens[${tokenIndex}] must have valid start/end`);
    }
    return {
      text,
      startRaw,
      endRaw,
      style: normalizeStyle(token.style ?? {}),
    };
  }).filter(Boolean);

  if (!normalized.length) return [];

  const firstStart = Math.min(...normalized.map((token) => token.startRaw));
  const lastEnd = Math.max(...normalized.map((token) => token.endRaw));
  const looksAbsolute = firstStart >= cueStart - 0.05 && lastEnd <= cueEnd + 0.05;
  const looksRelative = firstStart >= -0.05 && lastEnd <= cueDuration + 0.05;
  const offset = looksAbsolute ? cueStart : looksRelative ? 0 : firstStart;

  const brandWords = Array.isArray(branding?.words)
    ? branding.words.filter((word) => typeof word === 'string' && word.length > 0)
    : [];
  const brandStyle = resolveBrandStyle(branding, cueStyle ?? {});
  const brandRanges = brandRangesForText(cueText, brandWords);
  let textCursor = 0;
  return normalized.map((token, tokenIndex) => {
    const start = Math.max(0, token.startRaw - offset);
    const end = Math.min(cueDuration, Math.max(start + 0.001, token.endRaw - offset));
    if (end > cueDuration + 0.05) {
      throw new SubtitleMotionError(`subtitles[${index}].tokens[${tokenIndex}] is outside cue time range`);
    }
    const textIndex = cueText.indexOf(token.text, textCursor);
    const tokenEndIndex = textIndex >= 0 ? textIndex + token.text.length : -1;
    const isBrandToken = tokenTouchesBrandRange(brandRanges, textIndex, tokenEndIndex);
    if (textIndex >= 0) textCursor = tokenEndIndex;
    const tokenStyle = normalizeStyle(token.style ?? {});
    return {
      text: token.text,
      start,
      end,
      // 品牌词的字体规则优先级最高，避免字幕动效或 TTS token style 把 SodaFont 覆盖掉。
      style: isBrandToken ? {...tokenStyle, ...brandStyle} : tokenStyle,
    };
  }).filter((token) => cueText.includes(token.text) || token.text.length === 1 || !cueText);
};

const normalizeEffect = (raw = {}, cueDuration, index) => {
  const requestedType = String(raw.type ?? 'fade_slide');
  const type = EFFECT_ALIASES.get(requestedType.toLowerCase());
  if (!type) throw new SubtitleMotionError(`Unsupported subtitle effect: ${requestedType}`);
  const definition = EFFECT_DEFINITIONS[type];
  const preset = String(raw.preset ?? definition.defaultPreset);
  if (!definition.presets.includes(preset)) {
    throw new SubtitleMotionError(`Unsupported ${type} preset: ${preset}`);
  }
  const duration = Math.min(
    positive(raw.duration ?? definition.defaultDuration, `subtitles[${index}].effect.duration`),
    cueDuration,
  );
  const granularity = String(raw.granularity ?? 'char');
  if (!['char', 'word'].includes(granularity)) {
    throw new SubtitleMotionError(`subtitles[${index}].effect.granularity must be char or word`);
  }
  const stagger = Number(raw.stagger ?? (granularity === 'word' ? 0.08 : 0.035));
  if (!Number.isFinite(stagger) || stagger < 0) {
    throw new SubtitleMotionError(`subtitles[${index}].effect.stagger must be >= 0`);
  }
  const effect = {
    type,
    preset,
    duration,
    granularity,
    stagger,
  };
  for (const field of ['activeColor', 'inactiveColor', 'badgeText', 'badgeShape', 'badgeColor', 'badgeBackground']) {
    if (raw[field] != null) effect[field] = String(raw[field]);
  }
  if (effect.badgeShape != null && !['dot', 'coin', 'heart', 'spark'].includes(effect.badgeShape)) {
    throw new SubtitleMotionError(`subtitles[${index}].effect.badgeShape must be dot, coin, heart, or spark`);
  }
  for (const field of ['badgeSize', 'badgeSpinDegrees', 'badgeSpinDuration', 'badgeSpinWobble', 'amplitude', 'stackOffset']) {
    if (raw[field] != null) {
      const number = Number(raw[field]);
      if (!Number.isFinite(number) || number < 0) {
        throw new SubtitleMotionError(`subtitles[${index}].effect.${field} must be >= 0`);
      }
      effect[field] = number;
    }
  }
  if (raw.stackOpacity != null) {
    const number = Number(raw.stackOpacity);
    if (!Number.isFinite(number) || number < 0 || number > 1) {
      throw new SubtitleMotionError(`subtitles[${index}].effect.stackOpacity must be between 0 and 1`);
    }
    effect.stackOpacity = number;
  }
  if (raw.stackColors != null) {
    const colors = parseStringList(raw.stackColors);
    if (!colors.length) {
      throw new SubtitleMotionError(`subtitles[${index}].effect.stackColors must contain at least one color`);
    }
    effect.stackColors = colors;
  }
  return effect;
};

const normalizeTimeline = ({timelinePath, assetRoot, inputPath, mode}) => {
  if (!fs.existsSync(timelinePath)) throw new SubtitleMotionError(`Timeline not found: ${timelinePath}`);
  const raw = JSON.parse(fs.readFileSync(timelinePath, 'utf8'));
  if (containsPlaceholder(raw)) throw new SubtitleMotionError('Timeline contains unresolved <...> placeholders');

  const canvasRaw = raw.canvas ?? {};
  const width = Math.round(positive(canvasRaw.width ?? 1080, 'canvas.width'));
  const height = Math.round(positive(canvasRaw.height ?? 1920, 'canvas.height'));
  const fps = Math.round(positive(canvasRaw.fps ?? 30, 'canvas.fps'));
  const baseFit = String(canvasRaw.base_fit ?? canvasRaw.baseFit ?? 'cover');
  if (!['cover', 'contain', 'stretch'].includes(baseFit)) {
    throw new SubtitleMotionError('canvas.base_fit must be cover, contain, or stretch');
  }

  let inputSummary = null;
  if (mode === 'composite') {
    if (!inputPath) throw new SubtitleMotionError('--input is required for composite mode');
    inputSummary = ffprobe(inputPath);
    if (inputSummary.width <= 0 || inputSummary.height <= 0 || inputSummary.duration <= 0) {
      throw new SubtitleMotionError(`Input has no readable video stream: ${inputPath}`);
    }
  }

  const fonts = (Array.isArray(raw.fonts) ? raw.fonts : []).map((font, index) => {
    if (!font || typeof font !== 'object') throw new SubtitleMotionError(`fonts[${index}] must be an object`);
    const family = String(font.family ?? '').trim();
    if (!family) throw new SubtitleMotionError(`fonts[${index}].family is required`);
    let sourcePath = null;
    if (font.path != null) {
      sourcePath = resolveFromRoot(assetRoot, font.path, `fonts[${index}].path`);
      if (!fs.existsSync(sourcePath)) throw new SubtitleMotionError(`Font file not found: ${sourcePath}`);
      if (!FONT_EXTENSIONS.has(path.extname(sourcePath).toLowerCase())) {
        throw new SubtitleMotionError(`Unsupported font file type: ${sourcePath}`);
      }
    }
    return {
      family,
      sourcePath,
      weight: font.weight == null ? undefined : String(font.weight),
      style: font.style == null ? undefined : String(font.style),
    };
  });

  const rootStylePreset = resolveStylePreset(
    raw.defaultStylePreset ?? raw.default_style_preset ?? raw.stylePreset ?? raw.style_preset,
    'defaultStylePreset',
  );
  const defaultStyle = normalizeStyle(raw.defaultStyle ?? raw.default_style ?? {}, {
    fontFamily: 'Arial, sans-serif',
    fontSize: Math.round(width * 0.06),
    fontWeight: 800,
    color: '#FFFFFF',
    strokeColor: '#000000',
    strokeWidth: Math.max(2, Math.round(width * 0.0032)),
    shadowBlur: 0,
    lineHeight: 1.12,
    letterSpacing: 0,
    ...rootStylePreset,
  });
  const rootEffectPreset = resolveEffectPreset(
    raw.defaultEffectPreset ?? raw.default_effect_preset ?? raw.effectPreset ?? raw.effect_preset,
    'defaultEffectPreset',
  );
  const rootEffect = {
    ...rootEffectPreset,
    ...(raw.defaultEffect ?? raw.default_effect ?? {}),
  };

  const rawSubtitles = raw.subtitles ?? raw.captions;
  if (!Array.isArray(rawSubtitles) || rawSubtitles.length === 0) {
    throw new SubtitleMotionError('timeline.subtitles must contain at least one subtitle cue');
  }
  const subtitles = rawSubtitles.map((cue, index) => {
    if (!cue || typeof cue !== 'object') throw new SubtitleMotionError(`subtitles[${index}] must be an object`);
    const text = String(cue.text ?? '').trim();
    if (!text) throw new SubtitleMotionError(`subtitles[${index}].text is required`);
    const start = Number(cue.start);
    const end = Number(cue.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) {
      throw new SubtitleMotionError(`subtitles[${index}] must satisfy 0 <= start < end`);
    }
    const position = String(cue.position ?? raw.position ?? 'lower_center');
    if (!['lower_center', 'middle_lower', 'center', 'top_center', 'bottom_center', 'custom'].includes(position)) {
      throw new SubtitleMotionError(`Unsupported subtitle position: ${position}`);
    }
    const maxWidth = positive(
      cue.maxWidth ?? cue.max_width ?? raw.maxWidth ?? raw.max_width ?? Math.round(width * 0.86),
      `subtitles[${index}].maxWidth`,
    );
    const align = String(cue.align ?? raw.align ?? 'center');
    if (!['left', 'center', 'right'].includes(align)) {
      throw new SubtitleMotionError(`subtitles[${index}].align must be left, center, or right`);
    }
    const cueStylePresetName = cue.stylePreset ?? cue.style_preset;
    const cueStylePreset = resolveStylePreset(cueStylePresetName, `subtitles[${index}].stylePreset`);
    const style = normalizeStyle(cue.style ?? {}, {...defaultStyle, ...cueStylePreset});
    const rawSpans = Array.isArray(cue.spans) && cue.spans.length > 0
      ? cue.spans.map((span, spanIndex) => {
          if (!span || typeof span !== 'object') {
            throw new SubtitleMotionError(`subtitles[${index}].spans[${spanIndex}] must be an object`);
          }
          const spanText = String(span.text ?? '');
          if (!spanText) throw new SubtitleMotionError(`subtitles[${index}].spans[${spanIndex}].text is required`);
          return {text: spanText, style: normalizeStyle(span.style ?? {})};
      })
      : makeBrandSpans(text, raw.branding ?? {}, style);
    const spans = applyBrandingToSpans(rawSpans, raw.branding ?? {}, style);
    const tokenTimings = normalizeTokenTimings({
      rawCue: cue,
      rootFrontend: raw.frontend,
      cueStart: start,
      cueEnd: end,
      cueText: text,
      branding: raw.branding ?? {},
      cueStyle: style,
      index,
    });
    const cueEffectPresetName = cue.effectPreset ?? cue.effect_preset;
    const cueEffectPreset = resolveEffectPreset(cueEffectPresetName, `subtitles[${index}].effectPreset`);
    const explicitEffect = cue.effect != null || cue.effectPreset != null || cue.effect_preset != null;
    const effectSource = shouldUsePlainEffect(cue, text) && !explicitEffect
      ? {type: 'plain'}
      : {
          ...rootEffect,
          ...cueEffectPreset,
          ...(cue.effect ?? {}),
        };
    const effect = normalizeEffect(
      effectSource,
      end - start,
      index,
    );
    return {
      id: String(cue.id ?? `subtitle_${index + 1}`),
      start,
      end,
      text,
      position,
      x: numberOrNull(cue.x, `subtitles[${index}].x`) ?? undefined,
      y: numberOrNull(cue.y, `subtitles[${index}].y`) ?? undefined,
      maxWidth,
      align,
      style,
      stylePreset: cueStylePresetName == null ? undefined : String(cueStylePresetName),
      spans,
      tokens: tokenTimings,
      syncMode: tokenTimings.length > 0 ? 'timed_tokens' : 'uniform',
      effect,
      effectPreset: cueEffectPresetName == null ? undefined : String(cueEffectPresetName),
    };
  });

  const lastSubtitleEnd = Math.max(...subtitles.map((cue) => cue.end));
  const requestedDuration = canvasRaw.duration == null ? null : positive(canvasRaw.duration, 'canvas.duration');
  const durationInSeconds = requestedDuration
    ?? (mode === 'composite' ? inputSummary.duration : lastSubtitleEnd);
  if (lastSubtitleEnd > durationInSeconds + 1e-6) {
    throw new SubtitleMotionError(`Last subtitle ends at ${lastSubtitleEnd}s, after the ${durationInSeconds}s composition`);
  }

  return {
    mode,
    timelinePath,
    assetRoot,
    inputPath,
    inputSummary,
    canvas: {
      width,
      height,
      fps,
      backgroundColor: String(canvasRaw.background_color ?? canvasRaw.backgroundColor ?? '#000000'),
      baseFit,
    },
    durationInSeconds,
    fonts,
    subtitles,
  };
};

const publicCopy = (sourcePath, publicDir, stem) => {
  const extension = path.extname(sourcePath).toLowerCase();
  const relative = path.posix.join('media', `${stem}${extension}`);
  const destination = path.join(publicDir, ...relative.split('/'));
  fs.mkdirSync(path.dirname(destination), {recursive: true});
  fs.copyFileSync(sourcePath, destination);
  return relative;
};

const toRenderProps = (plan, publicDir) => {
  const base = plan.mode === 'composite'
    ? {src: publicCopy(plan.inputPath, publicDir, 'base')}
    : null;
  const fonts = plan.fonts.map((font, index) => ({
    family: font.family,
    src: font.sourcePath ? publicCopy(font.sourcePath, publicDir, `font-${String(index + 1).padStart(3, '0')}`) : null,
    weight: font.weight,
    style: font.style,
  }));
  return {
    mode: plan.mode,
    canvas: plan.canvas,
    durationInSeconds: plan.durationInSeconds,
    base,
    fonts,
    subtitles: plan.subtitles,
  };
};

const reportPlan = (plan) => ({
  engine: 'remotion',
  effectImplementation: 'remotion-react-css-subtitle-motion',
  mode: plan.mode,
  input: plan.inputPath,
  inputSummary: plan.inputSummary,
  assetRoot: plan.assetRoot,
  timelineJson: plan.timelinePath,
  canvas: plan.canvas,
  durationInSeconds: plan.durationInSeconds,
  fonts: plan.fonts.map((font) => ({
    family: font.family,
    path: font.sourcePath,
    weight: font.weight,
    style: font.style,
  })),
  subtitles: plan.subtitles,
});

const findChrome = () => {
  const candidates = [
    process.env.CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) ?? null;
};

const ensureDependencies = () => {
  const required = [
    path.join(ROOT, 'node_modules', 'remotion', 'package.json'),
    path.join(ROOT, 'node_modules', '@remotion', 'renderer', 'package.json'),
    path.join(ROOT, 'node_modules', '@remotion', 'bundler', 'package.json'),
  ];
  if (!required.every((item) => fs.existsSync(item))) {
    throw new SubtitleMotionError(`Remotion dependencies are missing. Run: node ${path.join(ROOT, 'render.mjs')} setup`);
  }
};

const setup = () => {
  const npm = npmInvocation();
  run(npm.command, [...npm.args, 'install', '--no-audit', '--no-fund'], {cwd: ROOT, inherit: true});
  run(npm.command, [...npm.args, 'run', 'check'], {cwd: ROOT, inherit: true});
  print({ok: true, engine: 'remotion', project: ROOT});
};

const render = async ({plan, outputPath, reportPath}) => {
  ensureDependencies();
  const chrome = findChrome();
  if (!chrome) throw new SubtitleMotionError('Chrome/Chromium not found; set CHROME_PATH');
  fs.mkdirSync(path.dirname(outputPath), {recursive: true});
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'subtitle-motion-effects-remotion-'));
  const publicDir = path.join(tempRoot, 'public');
  fs.mkdirSync(publicDir, {recursive: true});
  let serveUrl = null;
  try {
    const inputProps = toRenderProps(plan, publicDir);
    const [{bundle}, renderer] = await Promise.all([
      import('@remotion/bundler'),
      import('@remotion/renderer'),
    ]);
    serveUrl = await bundle({entryPoint: ENTRY_POINT, publicDir});
    const compositionId = plan.mode === 'alpha' ? 'SubtitleMotionAlpha' : 'SubtitleMotionComposite';
    const composition = await renderer.selectComposition({
      serveUrl,
      id: compositionId,
      inputProps,
      browserExecutable: chrome,
      logLevel: 'warn',
    });
    const common = {
      composition,
      serveUrl,
      outputLocation: outputPath,
      inputProps,
      browserExecutable: chrome,
      concurrency: 1,
      logLevel: 'warn',
    };
    if (plan.mode === 'alpha') {
      await renderer.renderMedia({
        ...common,
        codec: 'prores',
        proResProfile: '4444',
        pixelFormat: 'yuva444p10le',
        imageFormat: 'png',
        muted: true,
      });
    } else {
      await renderer.renderMedia({
        ...common,
        codec: 'h264',
        pixelFormat: 'yuv420p',
        crf: 18,
        audioCodec: 'aac',
      });
    }
    const report = {
      ok: true,
      ...reportPlan(plan),
      output: outputPath,
      outputSummary: ffprobe(outputPath),
      compositionId,
      chrome,
    };
    const resolvedReport = reportPath ?? outputPath.replace(/\.[^.]+$/, '.subtitle-motion.json');
    fs.mkdirSync(path.dirname(resolvedReport), {recursive: true});
    fs.writeFileSync(resolvedReport, `${JSON.stringify(report, null, 2)}\n`);
    print(report);
    process.stdout.write(`Finished video: ${outputPath}\nSubtitle motion report: ${resolvedReport}\n`);
  } finally {
    if (serveUrl && fs.existsSync(serveUrl)) fs.rmSync(serveUrl, {recursive: true, force: true});
    fs.rmSync(tempRoot, {recursive: true, force: true});
  }
};

const main = async () => {
  const {command, flags} = parseArgs(process.argv);
  if (command === 'setup') return setup();
  if (command === 'list-effects') {
    return print({
      engine: 'remotion',
      effects: Object.entries(EFFECT_DEFINITIONS).map(([type, definition]) => ({
        type,
        aliases: definition.aliases.filter((alias) => alias !== type),
        presets: definition.presets,
        defaultPreset: definition.defaultPreset,
        defaultDuration: definition.defaultDuration,
      })),
      stylePresets: Object.entries(STYLE_PRESETS).map(([name, preset]) => ({
        name,
        aliases: preset.aliases.filter((alias) => alias !== name),
        style: preset.style,
      })),
      effectPresets: Object.entries(EFFECT_PRESETS).map(([name, preset]) => ({
        name,
        aliases: preset.aliases.filter((alias) => alias !== name),
        effect: preset.effect,
      })),
    });
  }
  if (command === 'list-presets') {
    return print({
      engine: 'remotion',
      stylePresets: Object.entries(STYLE_PRESETS).map(([name, preset]) => ({name, ...preset})),
      effectPresets: Object.entries(EFFECT_PRESETS).map(([name, preset]) => ({name, ...preset})),
    });
  }
  if (!['validate', 'render'].includes(command)) {
    throw new SubtitleMotionError('Usage: render.mjs setup|list-effects|validate|render [options]');
  }

  const mode = String(flags.mode ?? 'alpha');
  if (!['composite', 'alpha'].includes(mode)) throw new SubtitleMotionError('--mode must be composite or alpha');
  const assetRoot = expandPath(requireFlag(flags, 'asset-root'));
  const timelinePath = expandPath(requireFlag(flags, 'timeline-json'));
  if (!fs.existsSync(assetRoot) || !fs.statSync(assetRoot).isDirectory()) {
    throw new SubtitleMotionError(`Asset root not found: ${assetRoot}`);
  }
  const inputPath = typeof flags.input === 'string' ? expandPath(flags.input) : null;
  const plan = normalizeTimeline({timelinePath, assetRoot, inputPath, mode});
  const baseReport = {ok: true, ...reportPlan(plan)};
  if (command === 'validate') return print(baseReport);

  const outputPath = expandPath(requireFlag(flags, 'output'));
  if (mode === 'alpha' && path.extname(outputPath).toLowerCase() !== '.mov') {
    throw new SubtitleMotionError('Alpha mode output must use a .mov extension');
  }
  if (mode === 'composite' && path.extname(outputPath).toLowerCase() !== '.mp4') {
    throw new SubtitleMotionError('Composite mode output must use a .mp4 extension');
  }
  const reportPath = typeof flags.report === 'string' ? expandPath(flags.report) : null;
  if (flags['dry-run']) return print({...baseReport, dryRun: true, output: outputPath, report: reportPath});
  await render({plan, outputPath, reportPath});
};

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${JSON.stringify({ok: false, error: message}, null, 2)}\n`);
  process.exitCode = 2;
});
