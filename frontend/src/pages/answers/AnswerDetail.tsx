import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, ai, Answer, ActivityTimeline as ActivityTimelineType, Review, User, fetchActivityTimeline } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ActionButton } from "@/components/ActionButton";
import { ActivityTimeline } from "@/components/ActivityTimeline";
import { Breadcrumb } from "@/components/Breadcrumb";
import { InlineReviewBox } from "@/components/InlineReviewBox";
import { MarkdownContent } from "@/components/MarkdownContent";
import { StatusBadge, WORKFLOW_HINTS } from "@/components/StatusBadge";
import { UserPicker } from "@/components/UserPicker";
import { useAITasks } from "@/contexts/AITaskContext";
import { useQuestionEvents } from "@/hooks/useQuestionEvents";

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

export function AnswerDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, hasRole, authConfig } = useAuth();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [timeline, setTimeline] = useState<ActivityTimelineType | null>(null);
  const [pendingReview, setPendingReview] = useState<Review | null>(null);
  const [editing, setEditing] = useState(false);
  const [revising, setRevising] = useState(false);
  const [editBody, setEditBody] = useState("");
  const [error, setError] = useState("");
  const [assigningReviewer, setAssigningReviewer] = useState(false);
  const [pickedReviewer, setPickedReviewer] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { addTask, cancelTask, getTask } = useAITasks();
  const [aiReviewTaskId, setAiReviewTaskId] = useState<string | null>(null);
  const aiReviewTask = aiReviewTaskId ? getTask(aiReviewTaskId) : null;
  const [aiReviewLoading, setAiReviewLoading] = useState(false);
  const [questionTitle, setQuestionTitle] = useState<string | null>(null);

  const load = () => {
    if (!id) return;
    // Clear stale pending review immediately so the InlineReviewBox
    // disappears while fresh data loads (avoids double-submit window)
    setPendingReview(null);
    api.get<Answer>(`/answers/${id}`)
      .then((a) => {
        setAnswer(a);
        setEditBody(a.body);
        api.get<{ title: string }>(`/questions/${a.question_id}`).then((q) => setQuestionTitle(q.title)).catch(() => {});
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Answer not found"));
    fetchActivityTimeline(id, true).then(setTimeline).catch(() => {});
    // Find pending review for current user
    api.get<Review[]>(`/reviews?target_type=answer&target_id=${id}`).then((reviews) => {
      const mine = reviews.find(
        (r) => r.reviewer.id === user?.id && r.verdict === "pending"
      );
      setPendingReview(mine ?? null);
    }).catch(() => {});
  };

  useEffect(load, [id]);

  // SSE: refresh when answer status changes on the parent question
  useQuestionEvents(answer?.question_id, (event) => {
    if (event.type === "answer_status_changed" && event.answer_id === id) {
      load();
    }
  });

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

  const handleAssignReviewer = async (selectedUser: User | null) => {
    if (!id || !selectedUser) {
      setPickedReviewer(null);
      return;
    }
    setAssigningReviewer(true);
    try {
      await ai.assignReviewer(id, selectedUser.id);
      setPickedReviewer(null);
      setError("");
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not assign reviewer");
    }
    setAssigningReviewer(false);
  };

  const handleAiReview = async () => {
    if (!id || aiReviewLoading) return;
    setAiReviewLoading(true);
    try {
      const task = await ai.reviewAssist(id);
      setAiReviewTaskId(task.id);
      addTask(task);
    } catch {
      setAiReviewTaskId(null);
    }
    setAiReviewLoading(false);
  };

  // Reload when AI review task completes
  const prevReviewStatus = useRef(aiReviewTask?.status);
  useEffect(() => {
    if (
      prevReviewStatus.current &&
      (prevReviewStatus.current === "pending" || prevReviewStatus.current === "running") &&
      aiReviewTask?.status === "completed"
    ) {
      load();
    }
    prevReviewStatus.current = aiReviewTask?.status;
  }, [aiReviewTask?.status]);

  if (!answer) return <p className="text-center py-8 text-muted-foreground">{error || "Loading..."}</p>;

  const isAuthor = user?.id === answer.author.id;
  const isAdmin = hasRole("admin");
  const isReviewer = hasRole("reviewer");
  const showAuthorActions = isAuthor || isAdmin;
  const showReviewerActions = isReviewer || isAdmin;

  const editPerm = editPermission(isAdmin, isAuthor, answer.status);
  const submitPerm = submitPermission(isAdmin, isAuthor, answer.status);
  const revisePerm = revisePermission(isAdmin, isAuthor, answer.status);
  const canAssignReview = (isReviewer || isAdmin) && (answer.status === "submitted" || answer.status === "under_review");

  return (
    <div className="max-w-3xl mx-auto">
      <Breadcrumb items={[
        { label: "Questions", to: "/questions" },
        { label: questionTitle || "Question", to: `/questions/${answer.question_id}` },
        { label: "Answer" },
      ]} />
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
            <span className="text-xs text-muted-foreground mt-1 block">{editBody.length} characters</span>
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

        {/* Reviewer actions */}
        {!editing && !revising && showReviewerActions && canAssignReview && (
          <div className="mt-3 pt-3 border-t border-border">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-muted-foreground">Assign reviewer:</span>
              {isAdmin && (
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
            <UserPicker
              role="reviewer"
              selected={pickedReviewer}
              onSelect={handleAssignReviewer}
              placeholder="Search reviewers..."
              disabled={assigningReviewer}
              excludeIds={authConfig?.dev_login_enabled ? [] : [answer.author.id]}
              prioritizeUser={user && (isReviewer || isAdmin) ? user as User : null}
            />
            {authConfig?.dev_login_enabled && (
              <p className="text-xs text-amber-600 mt-1">Self-review allowed in test mode</p>
            )}
          </div>
        )}
        {aiReviewTask && (
          <div className="mt-2 px-1 text-xs flex items-center gap-2">
            <span className={`inline-block px-2 py-0.5 rounded-full ${
              aiReviewTask.status === "completed" ? "bg-muted text-foreground" :
              aiReviewTask.status === "failed" ? "bg-destructive/10 text-destructive" :
              "bg-muted text-muted-foreground"
            }`}>{aiReviewTask.status}</span>
            {aiReviewTask.error && <span className="text-destructive">{aiReviewTask.error}</span>}
            {aiReviewTask.result && (
              <span className="text-muted-foreground">
                Confidence: {String(aiReviewTask.result.confidence)},
                Submitted: {String(aiReviewTask.result.submitted)}
              </span>
            )}
            {(aiReviewTask.status === "pending" || aiReviewTask.status === "running") && (
              <button onClick={() => cancelTask(aiReviewTask.id)} className="text-muted-foreground hover:text-destructive transition-colors" title="Cancel">
                <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
              </button>
            )}
          </div>
        )}
      </div>

      {error && <p className="text-destructive text-sm mb-4">{error}</p>}

      {/* Activity Timeline */}
      <h2 className="font-semibold text-lg mb-3">Activity</h2>
      {timeline ? (
        <div className="mb-6">
          <ActivityTimeline events={timeline.events} currentVersion={timeline.current_version} />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground mb-6">Loading timeline...</p>
      )}

      {/* Inline Review Box */}
      {pendingReview && (
        <div className="mb-6">
          <InlineReviewBox review={pendingReview} onVerdictSubmitted={load} />
        </div>
      )}
    </div>
  );
}
