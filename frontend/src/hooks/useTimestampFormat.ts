import { useState, useCallback } from "react";

export type TimestampFormat = "24h" | "12h" | "relative";

const STORAGE_KEY = "timestamp-format";

function getStoredFormat(): TimestampFormat {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "24h" || stored === "12h" || stored === "relative") return stored;
  return "24h";
}

function relativeTime(date: Date): string {
  const now = Date.now();
  const diff = now - date.getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months} months ago`;
}

export function formatTimestampWith(
  isoString: string,
  format: TimestampFormat,
): { display: string; title: string } {
  const date = new Date(isoString);
  const title = date.toISOString();
  const rel = relativeTime(date);

  if (format === "relative") {
    return { display: rel, title };
  }

  if (format === "12h") {
    const formatted = new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(date);
    return { display: `${formatted} · ${rel}`, title };
  }

  // 24h (default)
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const h = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return { display: `${y}-${m}-${d} ${h}:${min} · ${rel}`, title };
}

export function useTimestampFormat() {
  const [format, setFormatState] = useState<TimestampFormat>(getStoredFormat);

  const setFormat = useCallback((f: TimestampFormat) => {
    localStorage.setItem(STORAGE_KEY, f);
    setFormatState(f);
  }, []);

  const formatTimestamp = useCallback(
    (isoString: string) => formatTimestampWith(isoString, format),
    [format],
  );

  return { format, setFormat, formatTimestamp } as const;
}
