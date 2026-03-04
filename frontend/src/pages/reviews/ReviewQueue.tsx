import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Review } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { StatusBadge, statusColor, statusLabel } from "@/components/StatusBadge";

const VERDICT_BORDER_COLORS: Record<string, string> = {
  pending: "border-gray-300",
  approved: "border-green-300",
  changes_requested: "border-yellow-300",
  rejected: "border-red-300",
};

const ALL_VERDICTS = ["pending", "approved", "changes_requested", "rejected"];

type ViewMode = "list" | "kanban";
type ReviewTab = "answer" | "question";

function KanbanCard({ rev }: { rev: Review }) {
  return (
    <Link
      to={`/reviews/${rev.id}`}
      className="block bg-background p-3 rounded-lg border border-border hover:border-primary/30 transition-colors shadow-sm"
    >
      {rev.question_title && (
        <p className="text-xs font-medium text-foreground/80 line-clamp-1">{rev.question_title}</p>
      )}
      {rev.answer_version && (
        <span className="text-[10px] text-muted-foreground">v{rev.answer_version}</span>
      )}
      {rev.comment && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{rev.comment}</p>}
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
            <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(verdict)}`}>
              {statusLabel(verdict)}
            </span>
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
        <Link key={rev.id} to={`/reviews/${rev.id}`} className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30">
          <div className="flex items-center gap-3">
            <StatusBadge status={rev.verdict} />
            {rev.question_title && (
              <span className="text-sm text-foreground/70 truncate max-w-[300px]">{rev.question_title}</span>
            )}
            {rev.answer_version && (
              <span className="text-xs text-muted-foreground">v{rev.answer_version}</span>
            )}
            <span className="text-xs text-muted-foreground ml-auto">{new Date(rev.created_at).toLocaleDateString()}</span>
          </div>
        </Link>
      ))}
      {reviews.length === 0 && <p className="text-center text-muted-foreground py-8">No reviews in this section.</p>}
    </div>
  );
}

export function ReviewQueue() {
  const { user } = useAuth();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [activeTab, setActiveTab] = useState<ReviewTab>(() => {
    return (localStorage.getItem("reviewQueueTab") as ReviewTab) || "answer";
  });
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    return (localStorage.getItem("reviewQueueView") as ViewMode) || "list";
  });

  useEffect(() => {
    if (!user) return;
    if (viewMode === "kanban") {
      api.get<Review[]>(`/reviews?reviewer_id=${user.id}&target_type=${activeTab}`).then(setReviews);
    } else {
      // my-queue returns only pending; filter by target_type client-side
      api.get<Review[]>("/reviews/my-queue").then((all) =>
        setReviews(all.filter((r) => r.target_type === activeTab))
      );
    }
  }, [viewMode, user, activeTab]);

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
        <h1 className="text-2xl font-bold">My Reviews</h1>
        <div className="flex border border-border rounded-md overflow-hidden">
          <button onClick={() => handleViewChange("list")} className={`px-3 py-2 text-sm ${viewMode === "list" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>List</button>
          <button onClick={() => handleViewChange("kanban")} className={`px-3 py-2 text-sm ${viewMode === "kanban" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>Board</button>
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
