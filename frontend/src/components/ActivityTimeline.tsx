import { useState } from "react";
import { ActivityEvent } from "@/api/client";
import { DiffViewer } from "@/components/DiffViewer";
import { Timestamp } from "@/components/Timestamp";
import { MarkdownContent } from "@/components/MarkdownContent";

interface ActivityTimelineProps {
  events: ActivityEvent[];
  currentVersion: number;
}

function verdictLabel(verdict: string): string {
  switch (verdict) {
    case "approved": return "approved";
    case "changes_requested": return "requested changes";
    case "rejected": return "rejected";
    default: return verdict.replace(/_/g, " ");
  }
}

function triggerLabel(trigger: string): string {
  switch (trigger) {
    case "initial_submit": return "submitted";
    case "revision_after_review": return "resubmitted";
    case "post_approval_update": return "revised";
    default: return trigger.replace(/_/g, " ");
  }
}

function dotColor(event: ActivityEvent): string {
  if (event.type === "version_submitted") return "bg-blue-500";
  if (event.type === "reviewer_assigned") return "bg-gray-400";
  if (event.type === "review_submitted") {
    switch (event.verdict) {
      case "approved": return "bg-green-500";
      case "changes_requested": return "bg-amber-500";
      case "rejected": return "bg-red-500";
      default: return "bg-gray-400";
    }
  }
  return "bg-gray-400";
}

function EventContent({ event }: { event: ActivityEvent }) {
  const [showDiff, setShowDiff] = useState(false);

  if (event.type === "version_submitted") {
    const actorName = event.actor?.display_name ?? "Unknown";
    const action = triggerLabel(event.trigger ?? "submitted");
    return (
      <div>
        <p className="text-sm">
          <span className="font-medium">{actorName}</span>{" "}
          {action} v{event.version}
        </p>
        {event.diff && (
          <div className="mt-1">
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="text-xs text-primary hover:underline"
            >
              {showDiff ? "Hide changes" : "Show changes"}
            </button>
            {showDiff && <DiffViewer diff={event.diff} className="mt-2" />}
          </div>
        )}
      </div>
    );
  }

  if (event.type === "reviewer_assigned") {
    const reviewerName = event.reviewer?.display_name ?? "Unknown";
    const text = event.self_assigned
      ? "started a review"
      : "was assigned to review";
    return (
      <p className="text-sm">
        <span className="font-medium">{reviewerName}</span> {text}
        {event.answer_version != null && (
          <span className="text-muted-foreground"> on v{event.answer_version}</span>
        )}
      </p>
    );
  }

  if (event.type === "review_submitted") {
    const reviewerName = event.reviewer?.display_name ?? "Unknown";
    return (
      <div>
        <p className="text-sm">
          <span className="font-medium">{reviewerName}</span>{" "}
          {verdictLabel(event.verdict ?? "")}
          {event.answer_version != null && (
            <span className="text-muted-foreground"> on v{event.answer_version}</span>
          )}
          {event.is_stale && (
            <span className="ml-2 inline-block text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 font-medium">
              Outdated
            </span>
          )}
        </p>
        {event.comment && (
          <div className="mt-1 pl-3 border-l-2 border-border">
            <MarkdownContent className="text-xs text-muted-foreground">{event.comment}</MarkdownContent>
          </div>
        )}
      </div>
    );
  }

  return null;
}

export function ActivityTimeline({ events }: ActivityTimelineProps) {
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">No activity yet.</p>;
  }

  return (
    <div className="relative pl-6">
      {/* Vertical connector line */}
      <div className="absolute left-[9px] top-2 bottom-2 w-px bg-border" />

      <div className="space-y-4">
        {events.map((event, i) => (
          <div key={i} className="relative flex items-start gap-3">
            {/* Dot */}
            <div className={`absolute left-[-15px] top-1.5 w-[10px] h-[10px] rounded-full ${dotColor(event)} ring-2 ring-background`} />

            {/* Content */}
            <div className="flex-1 min-w-0">
              <EventContent event={event} />
              <Timestamp iso={event.timestamp} className="text-[11px] text-muted-foreground mt-0.5 block" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
