import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, Answer, AnswerRevision, Review } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function AnswerDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, hasRole } = useAuth();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [revisions, setRevisions] = useState<AnswerRevision[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [editing, setEditing] = useState(false);
  const [editBody, setEditBody] = useState("");
  const [error, setError] = useState("");
  // diff
  const [diffFrom, setDiffFrom] = useState<number | null>(null);
  const [diffTo, setDiffTo] = useState<number | null>(null);
  const [diffText, setDiffText] = useState<string | null>(null);
  // assign review
  const [showAssignReview, setShowAssignReview] = useState(false);

  const load = () => {
    if (!id) return;
    api.get<Answer>(`/answers/${id}`).then((a) => { setAnswer(a); setEditBody(a.body); });
    api.get<AnswerRevision[]>(`/answers/${id}/versions`).then(setRevisions);
    api.get<Review[]>(`/reviews?target_type=answer&target_id=${id}`).then(setReviews);
  };

  useEffect(load, [id]);

  const handleSave = async () => {
    if (!id) return;
    try {
      const updated = await api.patch<Answer>(`/answers/${id}`, { body: editBody });
      setAnswer(updated);
      setEditing(false);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  };

  const handleRevise = async () => {
    if (!id) return;
    try {
      const updated = await api.post<Answer>(`/answers/${id}/revise`);
      setAnswer(updated);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Revise failed");
    }
  };

  const handleViewDiff = async () => {
    if (!id || diffFrom == null || diffTo == null) return;
    try {
      const result = await api.get<{ diff: string }>(`/answers/${id}/diff?from=${diffFrom}&to=${diffTo}`);
      setDiffText(result.diff);
    } catch (err: unknown) {
      setDiffText(err instanceof Error ? err.message : "Could not load diff");
    }
  };

  const handleCreateReview = async () => {
    if (!id) return;
    try {
      const review = await api.post<Review>("/reviews", { target_type: "answer", target_id: id });
      setShowAssignReview(false);
      setReviews([...reviews, review]);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not create review");
    }
  };

  if (!answer) return <p className="text-center py-8 text-muted-foreground">{error || "Loading..."}</p>;

  const isAuthor = user?.id === answer.author.id;
  const canEdit = (isAuthor && (answer.status === "draft" || answer.status === "revision_requested")) || hasRole("admin");
  const canRevise = isAuthor && answer.status === "approved";
  const canAssignReview = (hasRole("reviewer") || hasRole("admin")) && (answer.status === "submitted" || answer.status === "under_review");

  const VERDICT_COLORS: Record<string, string> = {
    approved: "bg-green-100 text-green-800",
    changes_requested: "bg-yellow-100 text-yellow-800",
    rejected: "bg-red-100 text-red-800",
    pending: "bg-gray-100 text-gray-700",
  };

  const STATUS_COLORS: Record<string, string> = {
    draft: "bg-gray-200 text-gray-700",
    submitted: "bg-yellow-100 text-yellow-800",
    under_review: "bg-blue-100 text-blue-800",
    approved: "bg-green-100 text-green-800",
    revision_requested: "bg-orange-100 text-orange-800",
    rejected: "bg-red-100 text-red-800",
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        <div className="flex items-center gap-3 mb-4">
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLORS[answer.status] || "bg-gray-100"}`}>
            {answer.status}
          </span>
          <span className="text-xs text-muted-foreground">Version {answer.current_version}</span>
          <Link to={`/questions/${answer.question_id}`} className="text-xs text-blue-600 hover:underline ml-auto">Back to question</Link>
        </div>

        {editing ? (
          <>
            <textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} className="w-full border border-border rounded-md p-3 min-h-[200px] bg-background text-sm" />
            <div className="flex gap-2 mt-3">
              <button onClick={handleSave} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm">Save</button>
              <button onClick={() => setEditing(false)} className="border border-border px-4 py-2 rounded-md text-sm">Cancel</button>
            </div>
          </>
        ) : (
          <>
            <p className="whitespace-pre-wrap text-foreground/80">{answer.body}</p>
            <div className="text-sm text-muted-foreground mt-4">
              by {answer.author.display_name} &middot; {new Date(answer.created_at).toLocaleDateString()}
            </div>
            <div className="flex gap-2 mt-4 pt-4 border-t border-border">
              {canEdit && <button onClick={() => setEditing(true)} className="bg-secondary text-secondary-foreground px-3 py-1.5 rounded text-sm">Edit</button>}
              {canRevise && <button onClick={handleRevise} className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm">Revise (new version)</button>}
              {canAssignReview && !showAssignReview && (
                <button onClick={() => setShowAssignReview(true)} className="bg-purple-600 text-white px-3 py-1.5 rounded text-sm">Assign Review</button>
              )}
            </div>
          </>
        )}
      </div>

      {error && <p className="text-destructive text-sm mb-4">{error}</p>}

      {/* Assign review */}
      {showAssignReview && (
        <div className="bg-background p-4 rounded-lg border border-border mb-6">
          <p className="text-sm mb-3">Create a review assignment for this answer. You will be assigned as reviewer.</p>
          <div className="flex gap-2">
            <button onClick={handleCreateReview} className="bg-purple-600 text-white px-4 py-2 rounded-md text-sm">Confirm — Assign to Me</button>
            <button onClick={() => setShowAssignReview(false)} className="border border-border px-4 py-2 rounded-md text-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* Version History */}
      <h2 className="font-semibold text-lg mb-3">Version History</h2>
      <div className="space-y-2 mb-4">
        {revisions.map((rev) => (
          <div key={rev.id} className="bg-background p-3 rounded border border-border text-sm">
            <div className="flex items-center gap-3">
              <span className="font-mono font-medium">v{rev.version}</span>
              <span className="text-xs bg-secondary px-2 py-0.5 rounded">{rev.trigger.replace(/_/g, " ")}</span>
              <span className="text-xs text-muted-foreground">{rev.created_by.display_name}</span>
              <span className="text-xs text-muted-foreground ml-auto">{new Date(rev.created_at).toLocaleString()}</span>
            </div>
          </div>
        ))}
        {revisions.length === 0 && <p className="text-sm text-muted-foreground">No revisions yet.</p>}
      </div>

      {/* Diff viewer */}
      {revisions.length >= 2 && (
        <div className="bg-background p-4 rounded-lg border border-border mb-6">
          <h3 className="text-sm font-semibold mb-2">Compare Versions</h3>
          <div className="flex items-center gap-2 mb-3">
            <select value={diffFrom ?? ""} onChange={(e) => setDiffFrom(Number(e.target.value))} className="border border-border rounded px-2 py-1 text-sm bg-background">
              <option value="">From...</option>
              {revisions.map((r) => <option key={r.version} value={r.version}>v{r.version}</option>)}
            </select>
            <span className="text-muted-foreground text-sm">→</span>
            <select value={diffTo ?? ""} onChange={(e) => setDiffTo(Number(e.target.value))} className="border border-border rounded px-2 py-1 text-sm bg-background">
              <option value="">To...</option>
              {revisions.map((r) => <option key={r.version} value={r.version}>v{r.version}</option>)}
            </select>
            <button
              onClick={handleViewDiff}
              disabled={diffFrom == null || diffTo == null || diffFrom === diffTo}
              className="bg-secondary text-secondary-foreground px-3 py-1 rounded text-sm disabled:opacity-50"
            >
              View Diff
            </button>
          </div>
          {diffText !== null && (
            <pre className="bg-muted p-3 rounded text-xs overflow-x-auto whitespace-pre-wrap font-mono">{diffText}</pre>
          )}
        </div>
      )}

      {/* Reviews */}
      <h2 className="font-semibold text-lg mb-3">Reviews</h2>
      <div className="space-y-2">
        {reviews.map((rev) => (
          <Link key={rev.id} to={`/reviews/${rev.id}`} className="block bg-background p-3 rounded border border-border text-sm hover:border-primary/30">
            <div className="flex items-center gap-3">
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${VERDICT_COLORS[rev.verdict] || "bg-gray-100"}`}>{rev.verdict}</span>
              <span className="text-muted-foreground">{rev.reviewer.display_name}</span>
              {rev.comment && <span className="text-muted-foreground truncate ml-auto max-w-[200px]">{rev.comment}</span>}
            </div>
          </Link>
        ))}
        {reviews.length === 0 && <p className="text-sm text-muted-foreground">No reviews yet.</p>}
      </div>
    </div>
  );
}
