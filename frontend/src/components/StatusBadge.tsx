const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  // Question statuses
  draft: { label: "Draft", color: "bg-gray-200 text-gray-700" },
  proposed: { label: "Proposed", color: "bg-yellow-100 text-yellow-800" },
  in_review: { label: "In Review", color: "bg-blue-100 text-blue-800" },
  published: { label: "Published", color: "bg-green-100 text-green-800" },
  closed: { label: "Closed", color: "bg-red-100 text-red-800" },
  archived: { label: "Archived", color: "bg-gray-100 text-gray-500" },
  // Answer statuses
  submitted: { label: "Submitted", color: "bg-yellow-100 text-yellow-800" },
  under_review: { label: "Under Review", color: "bg-blue-100 text-blue-800" },
  approved: { label: "Approved", color: "bg-green-100 text-green-800" },
  revision_requested: { label: "Revision Requested", color: "bg-orange-100 text-orange-800" },
  rejected: { label: "Rejected", color: "bg-red-100 text-red-800" },
  // Review verdicts
  pending: { label: "Pending", color: "bg-gray-200 text-gray-700" },
  changes_requested: { label: "Changes Requested", color: "bg-yellow-100 text-yellow-800" },
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
  return STATUS_CONFIG[status]?.color ?? "bg-gray-100 text-gray-600";
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
