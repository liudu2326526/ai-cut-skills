#!/usr/bin/env node

import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const ENTRY_POINT = path.join(ROOT, 'src', 'index.tsx');
const EFFECT_DEFINITIONS = {
  dynamic_shrink: {
    aliases: ['dynamic_shrink', '动感缩小', '第一动效'],
    presets: ['reference_first_v2', 'reference_first_v1'],
    defaultPreset: 'reference_first_v2',
    defaultDuration: 10 / 30,
  },
  bottom_rise: {
    aliases: ['bottom_rise', '底部上冲回正', '底部上冲', '第二动效'],
    presets: ['reference_second_v1'],
    defaultPreset: 'reference_second_v1',
    defaultDuration: 15 / 30,
  },
  perspective_settle: {
    aliases: ['perspective_settle', '透视翻转回正', '第三动效'],
    presets: ['reference_third_v3'],
    defaultPreset: 'reference_third_v3',
    defaultDuration: 16 / 30,
  },
  flash_stretch: {
    aliases: ['flash_stretch', '白闪拉伸回正', '白闪拉伸', '第四动效'],
    presets: ['reference_fourth_v1'],
    defaultPreset: 'reference_fourth_v1',
    defaultDuration: 13 / 30,
  },
  page_curl: {
    aliases: ['page_curl', '卷页翻入回正', '卷页翻入', '第五动效'],
    presets: ['reference_fifth_v1'],
    defaultPreset: 'reference_fifth_v1',
    defaultDuration: 26 / 30,
  },
};
const EFFECT_ALIASES = new Map(
  Object.entries(EFFECT_DEFINITIONS).flatMap(([type, definition]) =>
    definition.aliases.map((alias) => [alias, type]),
  ),
);
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff']);

class MotionError extends Error {}

const print = (value) => process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);

const expandPath = (value) => {
  if (typeof value !== 'string' || value.length === 0) {
    throw new MotionError('Expected a non-empty path');
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
    if (!token.startsWith('--')) {
      throw new MotionError(`Unexpected argument: ${token}`);
    }
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
    throw new MotionError(`Missing required option: --${key}`);
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
    throw new MotionError(
      `${command} failed (${result.status})\n${result.stdout ?? ''}${result.stderr ?? ''}`.trim(),
    );
  }
  return result;
};

const ffprobe = (filePath) => {
  if (!fs.existsSync(filePath)) throw new MotionError(`File not found: ${filePath}`);
  const result = run('ffprobe', [
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

const resolveAsset = (assetRoot, value) => {
  if (typeof value !== 'string' || value.length === 0) {
    throw new MotionError('Event path must be a non-empty string');
  }
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(assetRoot, value);
};

const position = (value, canvasSize, targetSize, field) => {
  if (value === 'center' || value == null) return (canvasSize - targetSize) / 2;
  const number = Number(value);
  if (!Number.isFinite(number)) throw new MotionError(`${field} must be a number or center`);
  return number;
};

const positive = (value, field) => {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) throw new MotionError(`${field} must be positive`);
  return number;
};

const normalizeTimeline = ({timelinePath, assetRoot, inputPath, mode}) => {
  if (!fs.existsSync(timelinePath)) throw new MotionError(`Timeline not found: ${timelinePath}`);
  const raw = JSON.parse(fs.readFileSync(timelinePath, 'utf8'));
  if (containsPlaceholder(raw)) throw new MotionError('Timeline contains unresolved <...> placeholders');

  const canvasRaw = raw.canvas ?? {};
  const width = Math.round(positive(canvasRaw.width ?? 1080, 'canvas.width'));
  const height = Math.round(positive(canvasRaw.height ?? 1920, 'canvas.height'));
  const fps = Math.round(positive(canvasRaw.fps ?? 30, 'canvas.fps'));
  const baseFit = String(canvasRaw.base_fit ?? 'cover');
  if (!['cover', 'contain', 'stretch'].includes(baseFit)) {
    throw new MotionError('canvas.base_fit must be cover, contain, or stretch');
  }

  let inputSummary = null;
  if (mode === 'composite') {
    if (!inputPath) throw new MotionError('--input is required for composite mode');
    inputSummary = ffprobe(inputPath);
    if (inputSummary.width <= 0 || inputSummary.height <= 0 || inputSummary.duration <= 0) {
      throw new MotionError(`Input has no readable video stream: ${inputPath}`);
    }
  }

  if (!Array.isArray(raw.events) || raw.events.length === 0) {
    throw new MotionError('timeline.events must contain at least one image event');
  }

  const events = raw.events.map((item, index) => {
    if (!item || typeof item !== 'object') throw new MotionError(`events[${index}] must be an object`);
    const sourcePath = resolveAsset(assetRoot, item.path);
    if (!fs.existsSync(sourcePath)) throw new MotionError(`Overlay asset not found: ${sourcePath}`);
    if (!IMAGE_EXTENSIONS.has(path.extname(sourcePath).toLowerCase())) {
      throw new MotionError(`events[${index}] must use an image asset`);
    }
    const source = ffprobe(sourcePath);
    if (source.width <= 0 || source.height <= 0) {
      throw new MotionError(`Unable to read image dimensions: ${sourcePath}`);
    }
    const kind = String(item.kind ?? 'image');
    if (kind !== 'image') throw new MotionError(`events[${index}].kind currently supports image only`);
    const start = Number(item.start);
    const end = Number(item.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) {
      throw new MotionError(`events[${index}] must satisfy 0 <= start < end`);
    }

    const layoutRaw = item.layout ?? {};
    const targetWidth = positive(layoutRaw.width, `events[${index}].layout.width`);
    const targetHeight = layoutRaw.height == null
      ? source.height * targetWidth / source.width
      : positive(layoutRaw.height, `events[${index}].layout.height`);
    const x = position(layoutRaw.x, width, targetWidth, `events[${index}].layout.x`);
    const y = position(layoutRaw.y, height, targetHeight, `events[${index}].layout.y`);
    const originX = layoutRaw.origin_x == null ? targetWidth / 2 : Number(layoutRaw.origin_x);
    const originY = layoutRaw.origin_y == null ? targetHeight / 2 : Number(layoutRaw.origin_y);
    if (!Number.isFinite(originX) || !Number.isFinite(originY)) {
      throw new MotionError(`events[${index}] origin_x/origin_y must be numeric`);
    }
    const borderRadius = layoutRaw.border_radius == null
      ? 17 * targetWidth / 506
      : Number(layoutRaw.border_radius);
    if (!Number.isFinite(borderRadius) || borderRadius < 0) {
      throw new MotionError(`events[${index}].layout.border_radius must be >= 0`);
    }

    const effectRaw = item.effect ?? {};
    const requestedType = String(effectRaw.type ?? 'dynamic_shrink');
    const effectType = EFFECT_ALIASES.get(requestedType);
    if (!effectType) throw new MotionError(`Unsupported Remotion effect: ${requestedType}`);
    const definition = EFFECT_DEFINITIONS[effectType];
    const preset = String(effectRaw.preset ?? definition.defaultPreset);
    if (!definition.presets.includes(preset)) {
      throw new MotionError(`Unsupported ${effectType} preset: ${preset}`);
    }
    const effectDuration = positive(
      effectRaw.duration ?? definition.defaultDuration,
      `events[${index}].effect.duration`,
    );
    if (effectDuration > end - start) {
      throw new MotionError(`events[${index}].effect.duration exceeds the visible event duration`);
    }

    let effect;
    if (effectType === 'dynamic_shrink') {
      const defaultSamples = preset === 'reference_first_v2' ? 72 : 48;
      const minimumSamples = preset === 'reference_first_v2' ? 12 : 1;
      const samples = Math.round(Number(effectRaw.samples ?? defaultSamples));
      if (!Number.isInteger(samples) || samples < minimumSamples || samples > 96) {
        throw new MotionError(
          `events[${index}].effect.samples must be an integer from ${minimumSamples} to 96 for ${preset}`,
        );
      }
      effect = {type: effectType, preset, duration: effectDuration, samples};
    } else if (effectType === 'perspective_settle') {
      const samples = Math.round(Number(effectRaw.samples ?? 72));
      if (!Number.isInteger(samples) || samples < 12 || samples > 96) {
        throw new MotionError(
          `events[${index}].effect.samples must be an integer from 12 to 96 for ${preset}`,
        );
      }
      effect = {type: effectType, preset, duration: effectDuration, samples};
    } else if (effectType === 'page_curl') {
      const slices = Math.round(Number(effectRaw.slices ?? 192));
      if (!Number.isInteger(slices) || slices < 64 || slices > 256) {
        throw new MotionError(
          `events[${index}].effect.slices must be an integer from 64 to 256 for ${preset}`,
        );
      }
      effect = {type: effectType, preset, duration: effectDuration, slices};
    } else {
      effect = {type: effectType, preset, duration: effectDuration};
    }

    return {
      name: String(item.name ?? `event_${index + 1}`),
      sourcePath,
      source,
      kind: 'image',
      start,
      end,
      layout: {
        width: targetWidth,
        height: targetHeight,
        x,
        y,
        originX,
        originY,
        borderRadius,
      },
      effect,
    };
  });

  const lastEventEnd = Math.max(...events.map((event) => event.end));
  const requestedDuration = canvasRaw.duration == null ? null : positive(canvasRaw.duration, 'canvas.duration');
  const durationInSeconds = requestedDuration
    ?? (mode === 'composite' ? inputSummary.duration : lastEventEnd);
  if (lastEventEnd > durationInSeconds + 1e-6) {
    throw new MotionError(`Last event ends at ${lastEventEnd}s, after the ${durationInSeconds}s composition`);
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
      backgroundColor: String(canvasRaw.background_color ?? '#000000'),
      baseFit,
    },
    durationInSeconds,
    events,
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
  const events = plan.events.map((event, index) => ({
    name: event.name,
    src: publicCopy(event.sourcePath, publicDir, `event-${String(index + 1).padStart(3, '0')}`),
    kind: event.kind,
    start: event.start,
    end: event.end,
    layout: event.layout,
    effect: event.effect,
  }));
  return {
    mode: plan.mode,
    canvas: plan.canvas,
    durationInSeconds: plan.durationInSeconds,
    base,
    events,
  };
};

const reportPlan = (plan) => ({
  engine: 'remotion',
  effectImplementation: 'remotion-react',
  mode: plan.mode,
  input: plan.inputPath,
  inputSummary: plan.inputSummary,
  assetRoot: plan.assetRoot,
  timelineJson: plan.timelinePath,
  canvas: plan.canvas,
  durationInSeconds: plan.durationInSeconds,
  events: plan.events.map((event) => ({
    name: event.name,
    path: event.sourcePath,
    kind: event.kind,
    start: event.start,
    end: event.end,
    source: event.source,
    layout: event.layout,
    effect: event.effect,
  })),
});

const findChrome = () => {
  const candidates = [
    process.env.CHROME_PATH,
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
    throw new MotionError(`Remotion dependencies are missing. Run: node ${path.join(ROOT, 'render.mjs')} setup`);
  }
};

const setup = () => {
  run('npm', ['install', '--no-audit', '--no-fund'], {cwd: ROOT, inherit: true});
  run('npm', ['run', 'check'], {cwd: ROOT, inherit: true});
  print({ok: true, engine: 'remotion', project: ROOT});
};

const render = async ({plan, outputPath, reportPath}) => {
  ensureDependencies();
  const chrome = findChrome();
  if (!chrome) throw new MotionError('Chrome/Chromium not found; set CHROME_PATH');
  fs.mkdirSync(path.dirname(outputPath), {recursive: true});
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'video-motion-effects-remotion-'));
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
    const compositionId = plan.mode === 'alpha' ? 'MotionEffectsAlpha' : 'MotionEffectsComposite';
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
    const resolvedReport = reportPath ?? outputPath.replace(/\.[^.]+$/, '.motion.json');
    fs.mkdirSync(path.dirname(resolvedReport), {recursive: true});
    fs.writeFileSync(resolvedReport, `${JSON.stringify(report, null, 2)}\n`);
    print(report);
    process.stdout.write(`Finished video: ${outputPath}\nMotion report: ${resolvedReport}\n`);
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
        ...(type === 'dynamic_shrink' || type === 'perspective_settle'
          ? {defaultSamples: 72}
          : {}),
        ...(type === 'page_curl' ? {defaultSlices: 192} : {}),
      })),
    });
  }
  if (!['validate', 'render'].includes(command)) {
    throw new MotionError('Usage: render.mjs setup|list-effects|validate|render [options]');
  }

  const mode = String(flags.mode ?? 'composite');
  if (!['composite', 'alpha'].includes(mode)) throw new MotionError('--mode must be composite or alpha');
  const assetRoot = expandPath(requireFlag(flags, 'asset-root'));
  const timelinePath = expandPath(requireFlag(flags, 'timeline-json'));
  if (!fs.existsSync(assetRoot) || !fs.statSync(assetRoot).isDirectory()) {
    throw new MotionError(`Asset root not found: ${assetRoot}`);
  }
  const inputPath = typeof flags.input === 'string' ? expandPath(flags.input) : null;
  const plan = normalizeTimeline({timelinePath, assetRoot, inputPath, mode});
  const baseReport = {ok: true, ...reportPlan(plan)};
  if (command === 'validate') return print(baseReport);

  const outputPath = expandPath(requireFlag(flags, 'output'));
  if (mode === 'alpha' && path.extname(outputPath).toLowerCase() !== '.mov') {
    throw new MotionError('Alpha mode output must use a .mov extension');
  }
  if (mode === 'composite' && path.extname(outputPath).toLowerCase() !== '.mp4') {
    throw new MotionError('Composite mode output must use a .mp4 extension');
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
