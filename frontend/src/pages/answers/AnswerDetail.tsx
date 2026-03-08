import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, ai, Answer, AnswerRevision, Review, TaskStatus } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ActionButton } from "@/components/ActionButton";
import { MarkdownContent } from "@/components/MarkdownContent";
import { StatusBadge, WORKFLOW_HINTS } from "@/components/StatusBadge";

function editPermission(isAdmin: boolean, isAuthor: boolean, status: string) {
  if ((isAdmin || isAuthor) && (status === "draft" || status === "revision_requested")) return { enabled: true };
  if (status === "submitted")
    return { enabled: false, reason: "Answer is awaiting review", hint: "Wait for the review outcome" };
  if (status === "under_review")
    return { enabled: false, reason: "Answer is under review", hint: "Changes will be possible if revision is requested" };
  if (status === "approved")
    return { enabled: false, reason: "Committed answers can only be edited through revision", hint: "Use 'Revise' to propose changes" };
  if (status === "rejected")
    return { enabled: false, reason: "Rejected answers cannot be edited" };
  return { enabled: false, reason: "Only the author or an admin can edit" };
}

function submitPermission(isAdmin: boolean, isAuthor: boolean, status: string) {
  if ((isAuthor || isAdmin) && (status === "draft" || status === "revision_requested")) return { enabled: true };
  if (status === "submitted" || status === "under_review")
    return { enabled: false, reason: "Already submitted", hint: "Awaiting review" };
  if (status === "approved")
    return { enabled: false, reason: "Already approved", hint: "Use 'Revise' to reopen for changes" };
  if (status === "rejected")
    return { enabled: false, reason: "Rejected answers cannot be resubmitted" };
  return { enabled: false, reason: "Only the author or an admin can submit" };
}

function revisePermission(isAdmin: boolean, isAuthor: boolean, status: string) {
  if ((isAuthor || isAdmin) && status === "approved") return { enabled: true };
  if (status === "approved")
    return { enabled: false, reason: "Only the author or an admin can revise" };
  return { enabled: false, reason: "Only approved answers can be revised" };
}

function assignReviewPermission(hasReviewerRole: boolean, isAdmin: boolean, status: string) {
  if ((hasReviewerRole || isAdmin) && (status === "submitted" || status === "under_review")) return { enabled: true };
  if (status === "draft")
    return { enabled: false, reason: "Answer must be submitted first" };
  if (status === "approved" || status === "rejected")
    return { enabled: false, reason: "Review cycle is complete" };
  if (status === "revision_requested")
    return { enabled: false, reason: "Awaiting author revision", hint: "A review can be assigned after resubmission" };
  return { enabled: false, reason: "Only reviewers or admins can assign reviews" };
}

export function AnswerDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, hasRole } = useAuth();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [revisions, setRevisions] = useState<AnswerRevision[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [editing, setEditing] = useState(false);
  const [revising, setRevising] = useState(false);
  const [editBody, setEditBody] = useState("");
  const [error, setError] = useState("");
  const [diffFrom, setDiffFrom] = useState<number>(0);
  const [diffTo, setDiffTo] = useState<number>(0);
  const [diffText, setDiffText] = useState<string | null>(null);
  const [showAssignReview, setShowAssignReview] = useState(false);
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [aiReviewTask, setAiReviewTask] = useState<TaskStatus | null>(null);
  const [aiReviewLoading, setAiReviewLoading] = useState(false);

  const load = () => {
    if (!id) return;
    api.get<Answer>(`/answers/${id}`)
      .then((a) => { setAnswer(a); setEditBody(a.body); })
      .catch((err) => setError(err instanceof Error ? err.message : "Answer not found"));
    api.get<AnswerRevision[]>(`/answers/${id}/versions`).then((revs) => {
      setRevisions(revs);
      // Auto-select last two versions for diff
      if (revs.length >= 2) {
        setDiffFrom(revs[revs.length - 2].version);
        setDiffTo(revs[revs.length - 1].version);
      }
    }).catch(() => {});
    api.get<Review[]>(`/reviews?target_type=answer&target_id=${id}`).then(setReviews).catch(() => {});
  };

  useEffect(load, [id]);

  const handleSave = async () => {
    if (!id || isLoading) return;
    setIsLoading(true);
    try {
      const updated = await api.patch<Answer>(`/answers/${id}`, { body: editBody });
      setAnswer(updated);
      setEditing(false);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!id || isLoading) return;
    setIsLoading(true);
    try {
      const updated = await api.post<Answer>(`/answers/${id}/submit`);
      setAnswer(updated);
      load();
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRevise = async () => {
    if (!id || isLoading) return;
    setIsLoading(true);
    try {
      const updated = await api.post<Answer>(`/answers/${id}/revise`, { body: editBody });
      setAnswer(updated);
      setRevising(false);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Revise failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleViewDiff = async () => {
    if (!id || !diffFrom || !diffTo) return;
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

  const handleAiReview = async () => {
    if (!id || aiReviewLoading) return;
    setAiReviewLoading(true);
    try {
      const result = await ai.reviewAssist(id);
      setAiReviewTask({ task_id: result.task_id, status: result.status });
      const poll = async () => {
        try {
          const status = await ai.getTaskStatus(result.task_id);
          setAiReviewTask(status);
          if (status.status === "accepted" || status.status === "running") {
            setTimeout(poll, 2000);
          } else if (status.status === "completed") {
            load(); // Reload to show new review
          }
        } catch { /* stop polling */ }
      };
      poll();
    } catch (e: unknown) {
      setAiReviewTask({ task_id: "", status: "failed", error: e instanceof Error ? e.message : "Failed" });
    }
    setAiReviewLoading(false);
  };

  if (!answer) return <p className="text-center py-8 text-muted-foreground">{error || "Loading..."}</p>;

  const isAuthor = user?.id === answer.author.id;
  const isAdmin = hasRole("admin");
  const isReviewer = hasRole("reviewer");
  const showAuthorActions = isAuthor || isAdmin;
  const showReviewerActions = isReviewer || isAdmin;

  const editPerm = editPermission(isAdmin, isAuthor, answer.status);
  const submitPerm = submitPermission(isAdmin, isAuthor, answer.status);
  const revisePerm = revisePermission(isAdmin, isAuthor, answer.status);
  const assignPerm = assignReviewPermission(isReviewer, isAdmin, answer.status);

  // Use answer_version from the API (set at review creation time)
  const reviewsWithMeta = reviews.map((rev) => ({
    ...rev,
    answerVersion: rev.answer_version ?? 1,
  }));

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        {/* Status + workflow hint */}
        <div className="flex items-center gap-3 mb-1">
          <StatusBadge status={answer.status} />
          <span className="text-xs text-muted-foreground">Version {answer.current_version}</span>
          <Link to={`/questions/${answer.question_id}`} className="text-xs text-primary hover:underline ml-auto">Back to question</Link>
        </div>
        <p className="text-xs text-muted-foreground mb-4">{WORKFLOW_HINTS[`a:${answer.status}`]}</p>

        {editing || revising ? (
          <>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              {revising ? "Revise answer (this will create a new version)" : "Answer body"}
            </label>
            <textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} className="w-full border border-border rounded-md p-3 min-h-[200px] bg-background text-sm" />
            <div className="flex gap-2 mt-3">
              {revising ? (
                <button onClick={handleRevise} disabled={isLoading || editBody === answer.body} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm disabled:opacity-50 active:scale-[0.97] transition-all duration-150">
                  Submit Revision
                </button>
              ) : (
                <button onClick={handleSave} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm active:scale-[0.97] transition-all duration-150">Save</button>
              )}
              <button onClick={() => { setEditing(false); setRevising(false); setEditBody(answer.body); }} className="border border-border px-4 py-2 rounded-md text-sm active:scale-[0.97] transition-all duration-150">Cancel</button>
            </div>
          </>
        ) : (
          <>
            <MarkdownContent className="text-foreground/80">{answer.body}</MarkdownContent>
            <div className="text-sm text-muted-foreground mt-4">
              by {answer.author.display_name} &middot; {new Date(answer.created_at).toLocaleDateString()}
            </div>
          </>
        )}

        {/* Author actions — always visible */}
        {!editing && !revising && showAuthorActions && (
          <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-border">
            <ActionButton label="Edit" onClick={() => setEditing(true)} enabled={editPerm.enabled && !isLoading} disabledReason={editPerm.reason} disabledHint={editPerm.hint} variant="secondary" />
            <ActionButton label={answer.status === "revision_requested" ? "Resubmit" : "Submit for Review"} onClick={handleSubmit} enabled={submitPerm.enabled && !isLoading} disabledReason={submitPerm.reason} disabledHint={submitPerm.hint} variant="primary" />
            <ActionButton label="Revise (new version)" onClick={() => { setEditBody(answer.body); setRevising(true); }} enabled={revisePerm.enabled && !isLoading} disabledReason={revisePerm.reason} variant="blue" />
          </div>
        )}

        {/* Reviewer actions — always visible */}
        {!editing && !revising && showReviewerActions && (
          <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-border">
            <span className="text-xs text-muted-foreground self-center mr-1">Review:</span>
            {!showAssignReview ? (
              <ActionButton label="Assign Review" onClick={() => setShowAssignReview(true)} enabled={assignPerm.enabled} disabledReason={assignPerm.reason} disabledHint={assignPerm.hint} variant="purple" />
            ) : (
              <>
                <button onClick={handleCreateReview} className="bg-primary text-primary-foreground px-3 py-1.5 rounded text-sm active:scale-[0.97] transition-all duration-150">Confirm — Assign to Me</button>
                <button onClick={() => setShowAssignReview(false)} className="border border-border px-3 py-1.5 rounded text-sm active:scale-[0.97] transition-all duration-150">Cancel</button>
              </>
            )}
            {isAdmin && (answer.status === "submitted" || answer.status === "under_review") && (
              <button
                onClick={handleAiReview}
                disabled={aiReviewLoading}
                className="bg-primary text-primary-foreground px-3 py-1.5 rounded text-sm disabled:opacity-50 ml-auto active:scale-[0.97] transition-all duration-150"
              >
                {aiReviewLoading ? (
                  <span className="inline-flex items-center gap-1.5">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Running...
                  </span>
                ) : "AI Review"}
              </button>
            )}
          </div>
        )}
        {aiReviewTask && (
          <div className="mt-2 px-1 text-xs">
            <span className={`inline-block px-2 py-0.5 rounded-full ${
              aiReviewTask.status === "completed" ? "bg-muted text-foreground" :
              aiReviewTask.status === "failed" ? "bg-destructive/10 text-destructive" :
              "bg-muted text-muted-foreground"
            }`}>{aiReviewTask.status}</span>
            {aiReviewTask.error && <span className="text-destructive ml-2">{aiReviewTask.error}</span>}
            {aiReviewTask.result && (
              <span className="ml-2 text-muted-foreground">
                Confidence: {String((aiReviewTask.result as Record<string, unknown>).confidence)},
                Submitted: {String((aiReviewTask.result as Record<string, unknown>).submitted)}
              </span>
            )}
          </div>
        )}
      </div>

      {error && <p className="text-destructive text-sm mb-4">{error}</p>}

      {/* Version History */}
      <h2 className="font-semibold text-lg mb-3">Version History</h2>
      <div className="space-y-2 mb-4">
        {revisions.map((rev) => (
          <div key={rev.id} className="bg-background rounded border border-border text-sm">
            <button
              onClick={() => setExpandedVersion(expandedVersion === rev.version ? null : rev.version)}
              className="flex items-center gap-3 w-full p-3 text-left hover:bg-muted/50"
            >
              <span className="font-mono font-medium">v{rev.version}</span>
              <span className="text-xs bg-secondary px-2 py-0.5 rounded">{rev.trigger.replace(/_/g, " ")}</span>
              <span className="text-xs text-muted-foreground">{rev.created_by.display_name}</span>
              <span className="text-xs text-muted-foreground ml-auto">{new Date(rev.created_at).toLocaleString()}</span>
              <span className="text-muted-foreground text-xs">{expandedVersion === rev.version ? "\u25B2" : "\u25BC"}</span>
            </button>
            {expandedVersion === rev.version && (
              <div className="px-3 pb-3 border-t border-border">
                <p className="whitespace-pre-wrap text-foreground/70 text-xs mt-2">{rev.body}</p>
              </div>
            )}
          </div>
        ))}
        {revisions.length === 0 && <p className="text-sm text-muted-foreground">No revisions yet.</p>}
      </div>

      {/* Diff viewer */}
      {revisions.length >= 2 && (
        <div className="bg-background p-4 rounded-lg border border-border mb-6">
          <h3 className="text-sm font-semibold mb-2">Compare Versions</h3>
          <div className="flex items-center gap-2 mb-3">
            <select value={diffFrom} onChange={(e) => setDiffFrom(Number(e.target.value))} className="border border-border rounded px-2 py-1 text-sm bg-background">
              <option value={0}>From...</option>
              {revisions.map((r) => <option key={r.version} value={r.version}>v{r.version}</option>)}
            </select>
            <span className="text-muted-foreground text-sm">&rarr;</span>
            <select value={diffTo} onChange={(e) => setDiffTo(Number(e.target.value))} className="border border-border rounded px-2 py-1 text-sm bg-background">
              <option value={0}>To...</option>
              {revisions.map((r) => <option key={r.version} value={r.version}>v{r.version}</option>)}
            </select>
            <button onClick={handleViewDiff} disabled={!diffFrom || !diffTo || diffFrom === diffTo} className="bg-secondary text-secondary-foreground px-3 py-1 rounded text-sm disabled:opacity-50 active:scale-[0.97] transition-all duration-150">View Diff</button>
          </div>
          {diffText !== null && (
            <div className="bg-muted rounded text-xs overflow-x-auto font-mono border border-border">
              {diffText.split("\n").map((line, i) => {
                let bg = "";
                let fg = "text-foreground/70";
                if (line.startsWith("+++") || line.startsWith("---")) {
                  bg = "bg-muted"; fg = "text-muted-foreground font-semibold";
                } else if (line.startsWith("@@")) {
                  bg = "bg-blue-500/10"; fg = "text-blue-600 dark:text-blue-400";
                } else if (line.startsWith("+")) {
                  bg = "bg-green-500/15"; fg = "text-green-700 dark:text-green-400";
                } else if (line.startsWith("-")) {
                  bg = "bg-red-500/15"; fg = "text-red-700 dark:text-red-400";
                }
                return (
                  <div key={i} className={`px-3 py-0.5 ${bg} ${fg} whitespace-pre-wrap`}>
                    {line || "\u00a0"}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Reviews — enriched with metadata */}
      <h2 className="font-semibold text-lg mb-3">Reviews ({reviews.length})</h2>
      <div className="space-y-2">
        {reviewsWithMeta.map((rev) => (
          <Link key={rev.id} to={`/reviews/${rev.id}`} className="block bg-background p-3 rounded border border-border text-sm hover:border-primary/30">
            <div className="flex items-center gap-3">
              <StatusBadge status={rev.verdict} />
              <span className="text-xs text-muted-foreground font-mono">v{rev.answerVersion}</span>
              <span className="text-muted-foreground">{rev.reviewer.display_name}</span>
              {rev.reviewer.user_type === "service" && (
                <span className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded-full font-medium border border-border">AI</span>
              )}
              <span className="text-xs text-muted-foreground ml-auto">{new Date(rev.created_at).toLocaleDateString()}</span>
            </div>
            {rev.comment && <p className="text-xs text-muted-foreground mt-1 truncate">{rev.comment}</p>}
          </Link>
        ))}
        {reviews.length === 0 && <p className="text-sm text-muted-foreground">No reviews yet.</p>}
      </div>
    </div>
  );
}
