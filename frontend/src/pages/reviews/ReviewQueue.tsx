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

function KanbanCard({ rev }: { rev: Review }) {
  return (
    <Link
      to={`/reviews/${rev.id}`}
      className="block bg-background p-3 rounded-lg border border-border hover:border-primary/30 transition-colors shadow-sm"
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-medium capitalize">{rev.target_type}</span>
      </div>
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
    <div className="flex gap-4 overflow-x-auto pb-4" style={{ minHeight: "calc(100vh - 220px)" }}>
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

export function ReviewQueue() {
  const { user } = useAuth();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    return (localStorage.getItem("reviewQueueView") as ViewMode) || "list";
  });

  useEffect(() => {
    if (viewMode === "kanban" && user) {
      api.get<Review[]>(`/reviews?reviewer_id=${user.id}`).then(setReviews);
    } else {
      api.get<Review[]>("/reviews/my-queue").then(setReviews);
    }
  }, [viewMode, user]);

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem("reviewQueueView", mode);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">
          {viewMode === "kanban" ? `My Reviews (${reviews.length})` : `My Review Queue (${reviews.length})`}
        </h1>
        <div className="flex border border-border rounded-md overflow-hidden">
          <button onClick={() => handleViewChange("list")} className={`px-3 py-2 text-sm ${viewMode === "list" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>List</button>
          <button onClick={() => handleViewChange("kanban")} className={`px-3 py-2 text-sm ${viewMode === "kanban" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>Board</button>
        </div>
      </div>

      {viewMode === "kanban" ? (
        <KanbanBoard reviews={reviews} />
      ) : (
        <div className="space-y-3">
          {reviews.map((rev) => (
            <Link key={rev.id} to={`/reviews/${rev.id}`} className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30">
              <div className="flex items-center gap-3">
                <StatusBadge status={rev.verdict} />
                <span className="text-sm font-medium capitalize">{rev.target_type}</span>
                <span className="text-xs text-muted-foreground ml-auto">{new Date(rev.created_at).toLocaleDateString()}</span>
              </div>
            </Link>
          ))}
          {reviews.length === 0 && <p className="text-center text-muted-foreground py-8">No pending reviews.</p>}
        </div>
      )}
    </div>
  );
}
