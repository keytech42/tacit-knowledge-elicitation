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
  superseded: "status-gray",
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

/*
 * Static class lookups — Tailwind purges dynamic `bg-${token}/10` strings,
 * so every class must appear as a full literal for the scanner to find it.
 */

const BADGE_CLASSES: Record<string, string> = {
  "status-gray": "bg-status-gray/10 text-status-gray border border-status-gray/20",
  "status-amber": "bg-status-amber/10 text-status-amber border border-status-amber/20",
  "status-blue": "bg-status-blue/10 text-status-blue border border-status-blue/20",
  "status-green": "bg-status-green/10 text-status-green border border-status-green/20",
  "status-red": "bg-status-red/10 text-status-red border border-status-red/20",
  "status-orange": "bg-status-orange/10 text-status-orange border border-status-orange/20",
};

const BORDER_CLASSES: Record<string, string> = {
  "status-gray": "border-status-gray/30",
  "status-amber": "border-status-amber/30",
  "status-blue": "border-status-blue/30",
  "status-green": "border-status-green/30",
  "status-red": "border-status-red/30",
  "status-orange": "border-status-orange/30",
};

const HOVER_BORDER_CLASSES: Record<string, string> = {
  "status-gray": "hover:border-status-gray/40",
  "status-amber": "hover:border-status-amber/40",
  "status-blue": "hover:border-status-blue/40",
  "status-green": "hover:border-status-green/40",
  "status-red": "hover:border-status-red/40",
  "status-orange": "hover:border-status-orange/40",
};

/** Generate badge classes from a status token. */
export function badgeColor(token: string): string {
  return BADGE_CLASSES[token] ?? "bg-muted text-muted-foreground";
}

/** Generate border class from a status token. */
export function borderColor(token: string): string {
  return BORDER_CLASSES[token] ?? "border-border";
}

/** Generate hover border class from a status token. */
export function hoverBorderColor(token: string): string {
  return HOVER_BORDER_CLASSES[token] ?? "hover:border-primary/30";
}
