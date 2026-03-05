const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  // Question statuses
  draft: { label: "Draft", color: "bg-muted text-muted-foreground" },
  proposed: { label: "Proposed", color: "bg-secondary text-secondary-foreground border border-border" },
  in_review: { label: "In Review", color: "bg-primary/10 text-primary border border-primary/20" },
  published: { label: "Published", color: "bg-primary text-primary-foreground" },
  closed: { label: "Closed", color: "bg-destructive/10 text-destructive border border-destructive/20" },
  archived: { label: "Archived", color: "bg-muted text-muted-foreground/60" },
  // Answer statuses
  submitted: { label: "Submitted", color: "bg-secondary text-secondary-foreground border border-border" },
  under_review: { label: "Under Review", color: "bg-primary/10 text-primary border border-primary/20" },
  approved: { label: "Approved", color: "bg-primary text-primary-foreground" },
  revision_requested: { label: "Revision Requested", color: "bg-destructive/10 text-destructive border border-destructive/20" },
  rejected: { label: "Rejected", color: "bg-destructive text-destructive-foreground" },
  // Review verdicts
  pending: { label: "Pending", color: "bg-muted text-muted-foreground" },
  changes_requested: { label: "Changes Requested", color: "bg-secondary text-secondary-foreground border border-border" },
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
