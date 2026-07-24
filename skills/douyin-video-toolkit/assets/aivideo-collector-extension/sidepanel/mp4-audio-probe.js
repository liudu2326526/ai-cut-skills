const DEFAULT_PROBE_BYTES = 1024 * 1024;
const MP4_CONTAINER_TYPES = new Set(["moov", "trak", "mdia"]);

function readType(bytes, offset) {
  return String.fromCharCode(bytes[offset], bytes[offset + 1], bytes[offset + 2], bytes[offset + 3]);
}

function parseBoxes(bytes, start, end, visitor) {
  let offset = start;
  while (offset + 8 <= end) {
    const view = new DataView(bytes.buffer, bytes.byteOffset + offset, end - offset);
    let size = view.getUint32(0);
    const type = readType(bytes, offset + 4);
    let headerSize = 8;

    if (size === 1) {
      if (offset + 16 > end) return "incomplete";
      const high = view.getUint32(8);
      const low = view.getUint32(12);
      const largeSize = high * 2 ** 32 + low;
      if (!Number.isSafeInteger(largeSize)) return "incomplete";
      size = largeSize;
      headerSize = 16;
    } else if (size === 0) {
      size = end - offset;
    }

    if (size < headerSize) {
      offset += 1;
      continue;
    }

    const boxEnd = offset + size;
    if (boxEnd > end) return "incomplete";

    const result = visitor(type, offset + headerSize, boxEnd);
    if (result) return result;
    offset = boxEnd;
  }
  return null;
}

function scanContainer(bytes, start, end) {
  return parseBoxes(bytes, start, end, (type, payloadStart, payloadEnd) => {
    if (type === "hdlr") {
      if (payloadStart + 12 > payloadEnd) return "incomplete";
      const handlerType = readType(bytes, payloadStart + 8);
      if (handlerType === "soun") return "audio";
      return null;
    }

    if (MP4_CONTAINER_TYPES.has(type)) {
      const nested = scanContainer(bytes, payloadStart, payloadEnd);
      if (nested === "audio" || nested === "incomplete") return nested;
    }
    return null;
  });
}

function findMoov(bytes) {
  let sawIncomplete = false;
  for (let offset = 0; offset + 8 <= bytes.length; offset += 1) {
    if (readType(bytes, offset + 4) !== "moov") continue;

    const view = new DataView(bytes.buffer, bytes.byteOffset + offset, bytes.length - offset);
    let size = view.getUint32(0);
    let headerSize = 8;
    if (size === 1) {
      if (offset + 16 > bytes.length) return "incomplete";
      const high = view.getUint32(8);
      const low = view.getUint32(12);
      size = high * 2 ** 32 + low;
      headerSize = 16;
    } else if (size === 0) {
      size = bytes.length - offset;
    }

    if (size < headerSize) continue;
    const boxEnd = offset + size;
    if (boxEnd > bytes.length) {
      sawIncomplete = true;
      continue;
    }

    const result = scanContainer(bytes, offset + headerSize, boxEnd);
    if (result === "audio") return "audio";
    if (result === "incomplete") sawIncomplete = true;
    else return "no-audio";
  }
  return sawIncomplete ? "incomplete" : null;
}

export function detectMp4AudioTrack(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length < 8) return null;

  const result = findMoov(bytes);
  if (result === "audio") return true;
  if (result === "incomplete") return null;
  if (result === "no-audio") return false;
  return null;
}

function parseTotalBytes(contentRange) {
  const match = /\/(\d+)$/.exec(contentRange || "");
  return match ? Number(match[1]) : null;
}

async function fetchRange(url, start, end, fetchImpl) {
  const response = await fetchImpl(url, {
    method: "GET",
    headers: { Range: `bytes=${start}-${end}` },
  });
  if (!response.ok && response.status !== 206) return { bytes: null, totalBytes: null };

  const contentType = response.headers?.get?.("content-type") || "";
  if (contentType && !contentType.toLowerCase().startsWith("video/") && !contentType.startsWith("application/octet-stream")) {
    return { bytes: null, totalBytes: null };
  }

  const buffer = await response.arrayBuffer();
  return {
    bytes: new Uint8Array(buffer),
    totalBytes: parseTotalBytes(response.headers?.get?.("content-range")),
  };
}

export async function probeMp4AudioTrack(url, options = {}) {
  const probeBytes = options.probeBytes || DEFAULT_PROBE_BYTES;
  const fetchImpl = options.fetchImpl || fetch;

  const head = await fetchRange(url, 0, probeBytes - 1, fetchImpl);
  if (!head.bytes) return null;
  const headResult = detectMp4AudioTrack(head.bytes);
  if (headResult !== null) return headResult;

  const totalBytes = head.totalBytes;
  if (!totalBytes || totalBytes <= probeBytes) return null;

  const tailStart = Math.max(0, totalBytes - probeBytes);
  const tail = await fetchRange(url, tailStart, totalBytes - 1, fetchImpl);
  if (!tail.bytes) return null;
  return detectMp4AudioTrack(tail.bytes);
}
