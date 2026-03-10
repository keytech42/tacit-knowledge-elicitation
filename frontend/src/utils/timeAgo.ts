/**
 * Convert an ISO datetime string to a human-friendly relative timestamp.
 *
 * - < 60 seconds: "just now"
 * - < 60 minutes: "X minutes ago"
 * - < 24 hours:   "X hours ago"
 * - < 2 days:     "Yesterday"
 * - < 7 days:     "X days ago"
 * - >= 7 days:    full date (e.g. "Mar 10, 2026")
 */
export function timeAgo(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;

  const days = Math.floor(hours / 24);
  if (days < 2) return "Yesterday";
  if (days < 7) return `${days} days ago`;

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Format an ISO datetime string to a readable exact datetime. */
export function exactDateTime(isoString: string): string {
  return new Date(isoString).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
