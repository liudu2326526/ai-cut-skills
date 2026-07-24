export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  return hours > 0 ? `${String(hours).padStart(2, "0")}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function buildQualityDurationHint({ totalBytes, durationSeconds } = {}) {
  const bytes = Number(totalBytes || 0);
  const duration = Number(durationSeconds || 0);

  if (bytes > 0 && duration > 1) {
    const kbps = (bytes * 8) / duration / 1000;
    let quality = "";
    if (kbps < 600) quality = ` · ⚠ 低画质 ${Math.round(kbps)}kbps`;
    else if (kbps < 1500) quality = ` · 中画质 ${Math.round(kbps)}kbps`;
    else quality = ` · 高画质 ${(kbps / 1000).toFixed(1)}Mbps`;
    return `${quality} · 时长 ${formatDuration(duration)}`;
  }

  if (bytes > 0 && bytes < 5 * 1024 * 1024) {
    return " · ⚠ 文件偏小，可能是低画质";
  }

  return "";
}
