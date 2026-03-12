import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, Question } from "@/api/client";
import { StatusBadge } from "@/components/StatusBadge";
import { QuestionImportExport } from "./QuestionImportExport";

interface AdminQueueItem {
  id: string;
  title: string;
  body: string;
  category: string | null;
  status: string;
  quality_score: number | null;
  created_by: { id: string; display_name: string };
  created_at: string;
  updated_at: string;
  published_at: string | null;
  answer_count: number;
  approved_count: number;
  pending_count: number;
}

interface AdminQueueData {
  proposed: AdminQueueItem[];
  in_review: AdminQueueItem[];
  pending: AdminQueueItem[];
  published: AdminQueueItem[];
  closed: AdminQueueItem[];
}

interface SectionConfig {
  key: keyof AdminQueueData;
  title: string;
  actions: { action: string; label: string; variant: string; needsConfirm?: boolean; needsComment?: boolean }[];
}

const SECTIONS: SectionConfig[] = [
  {
    key: "proposed",
    title: "Proposed",
    actions: [{ action: "start-review", label: "Start Review", variant: "blue" }],
  },
  {
    key: "in_review",
    title: "In Review",
    actions: [
      { action: "publish", label: "Publish", variant: "green", needsConfirm: true },
      { action: "reject", label: "Reject to Draft", variant: "danger", needsComment: true },
    ],
  },
  {
    key: "pending",
    title: "Pending Answers",
    actions: [{ action: "close", label: "Close", variant: "gray", needsConfirm: true }],
  },
  {
    key: "published",
    title: "Published",
    actions: [{ action: "close", label: "Close", variant: "gray", needsConfirm: true }],
  },
  {
    key: "closed",
    title: "Closed",
    actions: [{ action: "archive", label: "Archive", variant: "gray", needsConfirm: true }],
  },
];

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function QuestionReviewQueue() {
  const [data, setData] = useState<AdminQueueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [rejectModal, setRejectModal] = useState<{ questionId: string; title: string } | null>(null);
  const [rejectComment, setRejectComment] = useState("");

  const loadQueue = useCallback(async () => {
    try {
      const result = await api.get<AdminQueueData>("/questions/admin-queue");
      setData(result);
      setError("");
    } catch {
      setError("Failed to load admin queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  const handleAction = async (questionId: string, action: string, body?: unknown) => {
    setActionLoading(questionId);
    try {
      await api.post<Question>(`/questions/${questionId}/${action}`, body);
      await loadQueue();
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRejectSubmit = async () => {
    if (!rejectModal) return;
    await handleAction(rejectModal.questionId, "reject", rejectComment.trim() ? { comment: rejectComment.trim() } : undefined);
    setRejectModal(null);
    setRejectComment("");
  };

  const totalCount = data ? data.proposed.length + data.in_review.length + data.pending.length + data.published.length + data.closed.length : 0;

  if (loading) return <p className="text-center py-8 text-muted-foreground">Loading...</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Admin Queue</h1>
          <p className="text-sm text-muted-foreground mt-1">{totalCount} questions need attention</p>
        </div>
        <div className="flex items-center gap-2">
          <QuestionImportExport onRefresh={loadQueue} />
          <button onClick={loadQueue} className="text-sm px-3 py-1.5 border border-border rounded-md hover:bg-muted active:scale-[0.97] transition-all duration-150">
            Refresh
          </button>
        </div>
      </div>

      {error && <p className="text-destructive text-sm mb-4 p-3 bg-destructive/5 rounded-md border border-destructive/20">{error}</p>}

      {SECTIONS.map((section) => {
        const items = data?.[section.key] ?? [];
        return (
          <div key={section.key} className="mb-8">
            <div className="flex items-center gap-2 mb-3">
              <h2 className="font-semibold text-lg">{section.title}</h2>
              <span className="text-sm text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{items.length}</span>
            </div>

            {items.length === 0 ? (
              <p className="text-sm text-muted-foreground py-3 pl-1">No questions in this stage.</p>
            ) : (
              <div className="space-y-2">
                {items.map((q) => (
                  <div key={q.id} className="bg-background p-4 rounded-lg border border-border">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <StatusBadge status={q.status} />
                          {q.category && <span className="text-xs text-muted-foreground">{q.category}</span>}
                          <span className="text-xs text-muted-foreground">
                            {q.answer_count} answer{q.answer_count !== 1 ? "s" : ""}
                            {q.approved_count > 0 && ` (${q.approved_count} approved`}
                            {q.approved_count > 0 && q.pending_count > 0 && `, ${q.pending_count} pending`}
                            {q.approved_count > 0 && ")"}
                          </span>
                          {q.quality_score != null && (
                            <span className="text-xs text-muted-foreground">Score: {q.quality_score.toFixed(1)}</span>
                          )}
                        </div>
                        <Link to={`/questions/${q.id}`} className="font-medium hover:text-primary transition-colors">
                          {q.title}
                        </Link>
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-1">{q.body}</p>
                        <div className="text-xs text-muted-foreground mt-2">
                          by {q.created_by.display_name} &middot; {timeAgo(q.updated_at)}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {section.actions.map((a) => (
                          <button
                            key={a.action}
                            disabled={actionLoading === q.id}
                            onClick={() => {
                              if (a.needsComment) {
                                setRejectModal({ questionId: q.id, title: q.title });
                              } else if (a.needsConfirm) {
                                if (confirm(`${a.label} "${q.title}"?`)) {
                                  handleAction(q.id, a.action);
                                }
                              } else {
                                handleAction(q.id, a.action);
                              }
                            }}
                            className={`px-3 py-1.5 rounded text-sm font-medium disabled:opacity-50 active:scale-[0.97] ${
                              a.variant === "green" ? "bg-status-green text-white hover:bg-status-green/90" :
                              a.variant === "blue" ? "bg-status-blue text-white hover:bg-status-blue/90" :
                              a.variant === "danger" ? "bg-status-red text-white hover:bg-status-red/90" :
                              "bg-muted text-muted-foreground hover:bg-muted/80"
                            } transition-all duration-150 ${actionLoading === q.id ? "opacity-75 cursor-wait" : ""}`}
                          >
                            {actionLoading === q.id ? (
                              <span className="inline-flex items-center gap-1.5">
                                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                                {a.label}
                              </span>
                            ) : a.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {/* Reject modal */}
      {rejectModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setRejectModal(null)}>
          <div className="bg-background p-6 rounded-lg border border-border shadow-xl w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-lg mb-1">Reject Question</h3>
            <p className="text-sm text-muted-foreground mb-4 truncate">{rejectModal.title}</p>
            <label className="block text-sm font-medium mb-1">Reason (optional)</label>
            <textarea
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              className="w-full border border-border rounded-md p-3 min-h-[100px] bg-background text-sm mb-4"
              placeholder="Explain why this question is being sent back to draft..."
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => { setRejectModal(null); setRejectComment(""); }} className="px-4 py-2 border border-border rounded-md text-sm active:scale-[0.97] transition-all duration-150">
                Cancel
              </button>
              <button onClick={handleRejectSubmit} disabled={actionLoading !== null} className="px-4 py-2 bg-destructive text-destructive-foreground rounded-md text-sm font-medium hover:bg-destructive/90 disabled:opacity-50 active:scale-[0.97] transition-all duration-150">
                {actionLoading ? (
                  <span className="inline-flex items-center gap-1.5">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Rejecting...
                  </span>
                ) : "Reject to Draft"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
