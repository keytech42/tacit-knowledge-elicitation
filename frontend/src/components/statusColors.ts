/**
 * Canonical mapping from status → color token name.
 *
 * Every status-aware UI element (badges, borders, backgrounds) must
 * derive its color from this map so they stay in sync.
 */
export const STATUS_COLOR_TOKEN: Record<string, string> = {
  // Question statuses
  draft: "status-gray",
  proposed: "status-amber",
  in_review: "status-blue",
  published: "status-green",
  closed: "status-red",
  archived: "status-gray",
  // Answer statuses
  submitted: "status-amber",
  under_review: "status-blue",
  approved: "status-green",
  revision_requested: "status-orange",
  rejected: "status-red",
  // Review verdicts
  pending: "status-gray",
  changes_requested: "status-orange",
};

/** All valid token names (must exist in globals.css @theme). */
export const VALID_STATUS_TOKENS = [
  "status-gray",
  "status-amber",
  "status-blue",
  "status-green",
  "status-red",
  "status-orange",
] as const;

/** Generate badge classes from a status token. */
export function badgeColor(token: string): string {
  return `bg-${token}/10 text-${token} border border-${token}/20`;
}

/** Generate border class from a status token. */
export function borderColor(token: string): string {
  return `border-${token}/30`;
}
