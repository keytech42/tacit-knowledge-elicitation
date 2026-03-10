import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, ai, Review, Answer, Question, User } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ActionButton } from "@/components/ActionButton";
import { Breadcrumb } from "@/components/Breadcrumb";
import { MarkdownContent } from "@/components/MarkdownContent";
import { StatusBadge, statusLabel } from "@/components/StatusBadge";
import { UserPicker } from "@/components/UserPicker";

export function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, hasRole } = useAuth();
  const [review, setReview] = useState<Review | null>(null);
  const [target, setTarget] = useState<Answer | Question | null>(null);
  const [comment, setComment] = useState("");
  const [newComment, setNewComment] = useState("");
  const [assignUser, setAssignUser] = useState<User | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.get<Review>(`/reviews/${id}`).then((r) => {
      setReview(r);
      setComment(r.comment || "");
      const endpoint = r.target_type === "answer" ? `/answers/${r.target_id}` : `/questions/${r.target_id}`;
      api.get(endpoint).then(setTarget as (v: unknown) => void);
    });
  }, [id]);

  const handleVerdict = async (verdict: string) => {
    if (!id) return;
    try {
      const updated = await api.patch<Review>(`/reviews/${id}`, { verdict, comment: comment.trim() || undefined });
      setReview(updated);
      // Re-fetch target so its status reflects any state change (e.g. answer → approved)
      const endpoint = updated.target_type === "answer" ? `/answers/${updated.target_id}` : `/questions/${updated.target_id}`;
      api.get(endpoint).then(setTarget as (v: unknown) => void);
    } catch (err: unknown) {
      // show error inline
    }
  };

  const handleAddComment = async () => {
    if (!id || !newComment.trim()) return;
    await api.post(`/reviews/${id}/comments`, { body: newComment });
    setNewComment("");
    const updated = await api.get<Review>(`/reviews/${id}`);
    setReview(updated);
  };

  const reloadReview = async () => {
    if (!id) return;
    const r = await api.get<Review>(`/reviews/${id}`);
    setReview(r);
    setComment(r.comment || "");
  };

  const handleAssignReviewer = async (selectedUser: User) => {
    if (!review || review.target_type !== "answer") return;
    setAssigning(true);
    setAssignError(null);
    try {
      await ai.assignReviewer(review.target_id, selectedUser.id);
      setAssignUser(null);
      await reloadReview();
    } catch (err: unknown) {
      setAssignError(err instanceof Error ? err.message : "Failed to assign reviewer");
    } finally {
      setAssigning(false);
    }
  };

  if (!review) return <p className="text-center py-8 text-muted-foreground">Loading...</p>;

  const isReviewer = user?.id === review.reviewer.id;
  const isPending = review.verdict === "pending";

  const targetLink = review.target_type === "answer"
    ? `/answers/${review.target_id}`
    : `/questions/${review.target_id}`;

  // Build verdict button permissions
  const verdictPerm = (() => {
    if (isReviewer && isPending) return { enabled: true };
    if (!isPending)
      return { enabled: false, reason: "Verdict already submitted", hint: "Contact an admin if you need to change it" };
    return { enabled: false, reason: "Only the assigned reviewer can set a verdict" };
  })();

  // Show the version this review targets (from review record), not the answer's current version
  const answerVersion = review.target_type === "answer" ? review.answer_version : null;
  // Use answer_status from the review response (enriched by backend) — updates immediately after verdict
  const answerStatus = review.answer_status ?? null;
  const canAssign = review.target_type === "answer" && (hasRole("admin") || hasRole("reviewer"));
  const answerAuthorId = target && "author" in target ? (target as Answer).author?.id : null;

  return (
    <div className="max-w-3xl mx-auto">
      <Breadcrumb items={[{ label: "Reviews", to: "/reviews" }, { label: "Review" }]} />
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        <div className="flex items-center gap-3 mb-4">
          <StatusBadge status={review.verdict} />
          <span className="text-sm text-muted-foreground">
            Review of {review.target_type}
            {answerVersion != null && <span className="font-mono ml-1">v{answerVersion}</span>}
            {answerStatus && <span className="ml-1">({statusLabel(answerStatus)})</span>}
          </span>
          {review.approval_count != null && review.min_approvals != null && (
            <span className="text-xs text-muted-foreground">
              {review.approval_count}/{review.min_approvals} approvals
            </span>
          )}
          <span className="text-sm text-muted-foreground ml-auto">
            by {review.reviewer.display_name}
            {review.assigned_by && (
              <span className="text-xs text-muted-foreground ml-1">(assigned by {review.assigned_by.display_name})</span>
            )}
          </span>
        </div>

        {/* Target content — clickable link */}
        {target && (
          <Link to={targetLink} className="block bg-muted p-4 rounded-md mb-4 hover:bg-muted/80 transition-colors">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-muted-foreground">View {review.target_type}</span>
              <span className="text-xs text-blue-600">&rarr;</span>
            </div>
            <p className="text-sm font-medium mb-1">{"title" in target ? (target as Question).title : "Answer"}</p>
            <p className="text-sm whitespace-pre-wrap line-clamp-4">{"body" in target ? (target as Answer).body : ""}</p>
          </Link>
        )}

        {/* Assign reviewer — visible to admins and reviewers for answer reviews */}
        {canAssign && (
          <div className="border-t border-border pt-4 mb-4">
            <UserPicker
              role="reviewer"
              selected={assignUser}
              onSelect={(u) => {
                setAssignError(null);
                if (u) {
                  handleAssignReviewer(u);
                } else {
                  setAssignUser(null);
                }
              }}
              label="Assign additional reviewer"
              placeholder="Search for a reviewer..."
              disabled={assigning}
              excludeIds={answerAuthorId ? [answerAuthorId] : []}
              prioritizeUser={user as User | null}
            />
            {assigning && <p className="text-xs text-muted-foreground mt-1">Assigning...</p>}
            {assignError && <p className="text-xs text-red-600 mt-1">{assignError}</p>}
          </div>
        )}

        {/* Verdict actions — always visible for reviewer/assigned user */}
        {isReviewer && (
          <div className="border-t border-border pt-4">
            {isPending && (
              <>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Review comment</label>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Review comment (optional for approve, recommended for others)"
                  className="w-full border border-border rounded-md p-3 min-h-[80px] bg-background text-sm"
                />
                <span className="text-xs text-muted-foreground mt-1 mb-3 block">{comment.length} characters</span>
              </>
            )}
            <div className="flex flex-wrap gap-2">
              <ActionButton label="Approve" onClick={() => handleVerdict("approved")} enabled={verdictPerm.enabled} disabledReason={verdictPerm.reason} disabledHint={verdictPerm.hint} variant="green" />
              <ActionButton label="Request Changes" onClick={() => handleVerdict("changes_requested")} enabled={verdictPerm.enabled} disabledReason={verdictPerm.reason} disabledHint={verdictPerm.hint} variant="blue" />
              <ActionButton label="Reject" onClick={() => handleVerdict("rejected")} enabled={verdictPerm.enabled} disabledReason={verdictPerm.reason} disabledHint={verdictPerm.hint} variant="danger" />
            </div>
          </div>
        )}

        {review.comment && (
          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-xs font-medium text-muted-foreground mb-1">{isPending ? "Previous Feedback" : "Review Comment"}</p>
            <MarkdownContent className="text-sm">{review.comment}</MarkdownContent>
          </div>
        )}
      </div>

      {/* Comments thread */}
      <h2 className="font-semibold text-lg mb-3">Discussion ({review.comments.length})</h2>
      <div className="space-y-3 mb-4">
        {review.comments.map((c) => (
          <div key={c.id} className={`bg-background p-3 rounded border border-border text-sm ${c.parent_id ? "ml-8" : ""}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium text-xs">{c.author.display_name}</span>
              <span className="text-[10px] text-muted-foreground">{new Date(c.created_at).toLocaleString()}</span>
            </div>
            <MarkdownContent className="text-sm">{c.body}</MarkdownContent>
          </div>
        ))}
        {review.comments.length === 0 && <p className="text-sm text-muted-foreground">No comments yet.</p>}
      </div>

      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Add a comment</label>
        <div className="flex gap-2">
          <input
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="Add a comment..."
            className="flex-1 border border-border rounded-md px-3 py-2 text-sm bg-background"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAddComment(); } }}
          />
          <button onClick={handleAddComment} disabled={!newComment.trim()} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm disabled:opacity-50 active:scale-[0.97] transition-all duration-150">Comment</button>
        </div>
      </div>
    </div>
  );
}
