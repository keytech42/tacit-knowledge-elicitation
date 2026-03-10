import { useEffect, useRef, useState } from "react";
import { STATUS_COLOR_TOKEN, badgeColor } from "./statusColors";

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  proposed: "Proposed",
  in_review: "In Review",
  published: "Published",
  closed: "Closed",
  archived: "Archived",
  submitted: "Submitted",
  under_review: "Under Review",
  approved: "Approved",
  revision_requested: "Changes Requested",
  rejected: "Rejected",
  pending: "Pending",
  changes_requested: "Changes Requested",
  superseded: "Superseded",
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
  return STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}

export function statusColor(status: string): string {
  const token = STATUS_COLOR_TOKEN[status];
  return token ? badgeColor(token) : "bg-muted text-muted-foreground";
}

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "xs";
}

export function StatusBadge({ status, size = "xs" }: StatusBadgeProps) {
  const sizeClass = size === "sm" ? "text-sm px-2.5 py-1" : "text-xs px-2 py-1";
  const prevStatus = useRef(status);
  const [pulsing, setPulsing] = useState(false);

  useEffect(() => {
    if (prevStatus.current !== status) {
      prevStatus.current = status;
      setPulsing(true);
      const timer = setTimeout(() => setPulsing(false), 200);
      return () => clearTimeout(timer);
    }
  }, [status]);

  return (
    <span
      className={`${sizeClass} rounded-full font-medium ${statusColor(status)} ${pulsing ? "badge-pulse" : ""}`}
    >
      {statusLabel(status)}
    </span>
  );
}
