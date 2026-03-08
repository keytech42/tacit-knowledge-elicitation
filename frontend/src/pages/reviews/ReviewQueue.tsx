import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Review } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { StatusBadge, statusColor, statusLabel } from "@/components/StatusBadge";
import { borderColor, STATUS_COLOR_TOKEN } from "@/components/statusColors";
import { Tooltip } from "@/components/Tooltip";

const VERDICT_BORDER_COLORS: Record<string, string> = {
  pending: borderColor(STATUS_COLOR_TOKEN["pending"]),
  approved: borderColor(STATUS_COLOR_TOKEN["approved"]),
  changes_requested: borderColor(STATUS_COLOR_TOKEN["changes_requested"]),
  rejected: borderColor(STATUS_COLOR_TOKEN["rejected"]),
  superseded: borderColor(STATUS_COLOR_TOKEN["superseded"]),
};

const ALL_VERDICTS = ["pending", "approved", "changes_requested", "rejected"];

const VERDICT_TOOLTIPS: Record<string, string> = {
  pending: "Reviewer has not yet submitted a verdict",
  approved: "Reviewer approved the submission",
  changes_requested: "Reviewer requested changes to the submission",
  rejected: "Reviewer rejected the submission",
  superseded: "Review was auto-closed because the answer was already resolved",
};

const ANSWER_STATUS_TOOLTIPS: Record<string, string> = {
  draft: "Answer is being drafted",
  submitted: "Answer submitted, awaiting reviewer assignment",
  under_review: "Answer is being evaluated by reviewers",
  approved: "Answer approved after all reviewers agreed",
  revision_requested: "Answer needs revision — at least one reviewer requested changes",
  rejected: "Answer was rejected by a reviewer",
};

type ViewMode = "list" | "kanban";
type ReviewTab = "answer" | "question";

function ReviewStatusChips({ rev }: { rev: Review }) {
  return (
    <div className="flex items-center gap-1.5 mt-1">
      {rev.answer_status && (
        <Tooltip text={ANSWER_STATUS_TOOLTIPS[rev.answer_status]}>
          <span className="inline-flex items-center gap-1.5">
            <span className="text-[10px] text-muted-foreground">Answer:</span>
            <StatusBadge status={rev.answer_status} size="xs" />
          </span>
        </Tooltip>
      )}
    </div>
  );
}

function KanbanCard({ rev }: { rev: Review }) {
  return (
    <Link
      to={`/reviews/${rev.id}`}
      className="block bg-background p-3 rounded-lg border border-border hover:border-primary/30 transition-colors shadow-sm"
    >
      {rev.question_title && (
        <p className="text-xs font-medium text-foreground/80 line-clamp-1">{rev.question_title}</p>
      )}
      <div className="flex items-center gap-2 mt-1">
        {rev.answer_version != null && (
          <span className="text-[10px] text-muted-foreground">v{rev.answer_version}</span>
        )}
        {rev.reviewer && (
          <span className="text-[10px] text-muted-foreground">{rev.reviewer.display_name}</span>
        )}
        {rev.approval_count != null && rev.min_approvals != null && (
          <Tooltip text={`${rev.approval_count} of ${rev.min_approvals} required approvals`}>
            <span className="text-[10px] text-muted-foreground">{rev.approval_count}/{rev.min_approvals}</span>
          </Tooltip>
        )}
      </div>
      <ReviewStatusChips rev={rev} />
      <div className="text-[10px] text-muted-foreground mt-1.5">{new Date(rev.created_at).toLocaleDateString()}</div>
    </Link>
  );
}

function KanbanBoard({ reviews }: { reviews: Review[] }) {
  const grouped = ALL_VERDICTS.reduce<Record<string, Review[]>>((acc, verdict) => {
    acc[verdict] = reviews.filter((r) => r.verdict === verdict);
    return acc;
  }, {});

  return (
    <div className="flex gap-4 overflow-x-auto pb-4" style={{ minHeight: "calc(100vh - 280px)" }}>
      {ALL_VERDICTS.map((verdict) => (
        <div key={verdict} className="flex-shrink-0 w-64">
          <div className="flex items-center gap-2 mb-3 px-1">
            <Tooltip text={VERDICT_TOOLTIPS[verdict]}>
              <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(verdict)}`}>
                {statusLabel(verdict)}
              </span>
            </Tooltip>
            <span className="text-xs text-muted-foreground">{grouped[verdict].length}</span>
          </div>
          <div className={`space-y-2 p-2 rounded-lg bg-muted/50 border ${VERDICT_BORDER_COLORS[verdict]} min-h-[200px]`}>
            {grouped[verdict].map((rev) => <KanbanCard key={rev.id} rev={rev} />)}
            {grouped[verdict].length === 0 && <p className="text-xs text-muted-foreground text-center py-6">No items</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function ReviewList({ reviews }: { reviews: Review[] }) {
  return (
    <div className="space-y-3">
      {reviews.map((rev) => (
        <Link key={rev.id} to={`/reviews/${rev.id}`} className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30 transition-colors">
          <div className="flex items-center gap-3">
            <Tooltip text={VERDICT_TOOLTIPS[rev.verdict]}>
              <StatusBadge status={rev.verdict} />
            </Tooltip>
            {rev.question_title && (
              <span className="text-sm text-foreground/70 truncate max-w-[300px]">{rev.question_title}</span>
            )}
            {rev.answer_version != null && (
              <span className="text-xs text-muted-foreground font-mono">v{rev.answer_version}</span>
            )}
            <span className="text-xs text-muted-foreground ml-auto">{rev.reviewer.display_name} &middot; {new Date(rev.created_at).toLocaleDateString()}</span>
          </div>
          <div className="flex items-center gap-1.5 mt-1.5">
            {rev.answer_status && (
              <Tooltip text={ANSWER_STATUS_TOOLTIPS[rev.answer_status]}>
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-[10px] text-muted-foreground">Answer:</span>
                  <StatusBadge status={rev.answer_status} size="xs" />
                </span>
              </Tooltip>
            )}
            {rev.approval_count != null && rev.min_approvals != null && (
              <Tooltip text={`${rev.approval_count} of ${rev.min_approvals} required approvals`}>
                <span className="text-[10px] text-muted-foreground">{rev.approval_count}/{rev.min_approvals} approvals</span>
              </Tooltip>
            )}
          </div>
        </Link>
      ))}
      {reviews.length === 0 && <p className="text-center text-muted-foreground py-8">No reviews in this section.</p>}
    </div>
  );
}

export function ReviewQueue() {
  const { user, hasRole } = useAuth();
  const [reviews, setReviews] = useState<Review[]>([]);
  const isAdmin = hasRole("admin");
  const [activeTab, setActiveTab] = useState<ReviewTab>(() => {
    return (localStorage.getItem("reviewQueueTab") as ReviewTab) || "answer";
  });
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    return (localStorage.getItem("reviewQueueView") as ViewMode) || "list";
  });

  useEffect(() => {
    if (!user) return;
    if (viewMode === "kanban") {
      // Admins see all reviews; reviewers see only their own
      const params = isAdmin
        ? `target_type=${activeTab}`
        : `reviewer_id=${user.id}&target_type=${activeTab}`;
      api.get<Review[]>(`/reviews?${params}`).then(setReviews).catch(() => setReviews([]));
    } else {
      if (isAdmin) {
        // Admins see all pending reviews
        api.get<Review[]>(`/reviews?target_type=${activeTab}`).then((all) =>
          setReviews(all.filter((r) => r.verdict === "pending"))
        ).catch(() => setReviews([]));
      } else {
        api.get<Review[]>("/reviews/my-queue").then((all) =>
          setReviews(all.filter((r) => r.target_type === activeTab))
        ).catch(() => setReviews([]));
      }
    }
  }, [viewMode, user, activeTab, isAdmin]);

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem("reviewQueueView", mode);
  };

  const handleTabChange = (tab: ReviewTab) => {
    setActiveTab(tab);
    localStorage.setItem("reviewQueueTab", tab);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{isAdmin ? "All Reviews" : "My Reviews"}</h1>
        <div className="flex border border-border rounded-md overflow-hidden">
          <button onClick={() => handleViewChange("list")} className={`px-3 py-2 text-sm transition-colors ${viewMode === "list" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>List</button>
          <button onClick={() => handleViewChange("kanban")} className={`px-3 py-2 text-sm transition-colors ${viewMode === "kanban" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>Board</button>
        </div>
      </div>

      {/* Tab bar for question vs answer reviews */}
      <div className="flex gap-1 mb-5 border-b border-border">
        <button
          onClick={() => handleTabChange("answer")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "answer"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Answer Reviews
        </button>
        <button
          onClick={() => handleTabChange("question")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "question"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Question Reviews
        </button>
      </div>

      {viewMode === "kanban" ? (
        <KanbanBoard reviews={reviews} />
      ) : (
        <ReviewList reviews={reviews} />
      )}
    </div>
  );
}
