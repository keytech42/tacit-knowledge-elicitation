const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  // Question statuses
  draft: { label: "Draft", color: "bg-status-gray/10 text-status-gray border border-status-gray/20" },
  proposed: { label: "Proposed", color: "bg-status-amber/10 text-status-amber border border-status-amber/20" },
  in_review: { label: "In Review", color: "bg-status-blue/10 text-status-blue border border-status-blue/20" },
  published: { label: "Published", color: "bg-status-green/10 text-status-green border border-status-green/20" },
  closed: { label: "Closed", color: "bg-status-red/10 text-status-red border border-status-red/20" },
  archived: { label: "Archived", color: "bg-muted text-muted-foreground" },
  // Answer statuses
  submitted: { label: "Submitted", color: "bg-status-amber/10 text-status-amber border border-status-amber/20" },
  under_review: { label: "Under Review", color: "bg-status-blue/10 text-status-blue border border-status-blue/20" },
  approved: { label: "Approved", color: "bg-status-green/10 text-status-green border border-status-green/20" },
  revision_requested: { label: "Revision Requested", color: "bg-status-orange/10 text-status-orange border border-status-orange/20" },
  rejected: { label: "Rejected", color: "bg-status-red/10 text-status-red border border-status-red/20" },
  // Review verdicts
  pending: { label: "Pending", color: "bg-status-gray/10 text-status-gray border border-status-gray/20" },
  changes_requested: { label: "Changes Requested", color: "bg-status-orange/10 text-status-orange border border-status-orange/20" },
};

/** Workflow hints shown below status badges */
export const WORKFLOW_HINTS: Record<string, string> = {
  // Question
  "q:draft": "Edit and submit when ready for review",
  "q:proposed": "Waiting for an admin to start the review process",
  "q:in_review": "Under admin review — may be published or sent back for revisions",
  "q:published": "Live and accepting answers",
  "q:closed": "No longer accepting answers",
  "q:archived": "Permanently archived",
  // Answer
  "a:draft": "Edit your answer and submit when ready",
  "a:submitted": "Waiting for a reviewer to be assigned",
  "a:under_review": "A reviewer is evaluating your answer",
  "a:revision_requested": "Changes requested — edit and resubmit",
  "a:approved": "Answer accepted",
  "a:rejected": "Answer was not accepted",
};

export function statusLabel(status: string): string {
  return STATUS_CONFIG[status]?.label ?? status.replace(/_/g, " ");
}

export function statusColor(status: string): string {
  return STATUS_CONFIG[status]?.color ?? "bg-muted text-muted-foreground";
}

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "xs";
}

export function StatusBadge({ status, size = "xs" }: StatusBadgeProps) {
  const sizeClass = size === "sm" ? "text-sm px-2.5 py-1" : "text-xs px-2 py-1";
  return (
    <span className={`${sizeClass} rounded-full font-medium ${statusColor(status)}`}>
      {statusLabel(status)}
    </span>
  );
}
