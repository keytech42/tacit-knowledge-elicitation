import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, Review, Answer, Question } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [review, setReview] = useState<Review | null>(null);
  const [target, setTarget] = useState<Answer | Question | null>(null);
  const [comment, setComment] = useState("");
  const [newComment, setNewComment] = useState("");

  useEffect(() => {
    if (!id) return;
    api.get<Review>(`/reviews/${id}`).then((r) => {
      setReview(r);
      const endpoint = r.target_type === "answer" ? `/answers/${r.target_id}` : `/questions/${r.target_id}`;
      api.get(endpoint).then(setTarget as (v: unknown) => void);
    });
  }, [id]);

  const handleVerdict = async (verdict: string) => {
    if (!id) return;
    const updated = await api.patch<Review>(`/reviews/${id}`, { verdict, comment });
    setReview(updated);
  };

  const handleAddComment = async () => {
    if (!id || !newComment.trim()) return;
    await api.post(`/reviews/${id}/comments`, { body: newComment });
    setNewComment("");
    const updated = await api.get<Review>(`/reviews/${id}`);
    setReview(updated);
  };

  if (!review) return <p className="text-center py-8 text-muted-foreground">Loading...</p>;

  const isReviewer = user?.id === review.reviewer.id;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        <div className="flex items-center gap-3 mb-4">
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${
            review.verdict === "approved" ? "bg-green-100 text-green-800" :
            review.verdict === "changes_requested" ? "bg-yellow-100 text-yellow-800" :
            review.verdict === "rejected" ? "bg-red-100 text-red-800" : "bg-gray-100"
          }`}>{review.verdict}</span>
          <span className="text-sm text-muted-foreground">Review of {review.target_type}</span>
          <span className="text-sm text-muted-foreground ml-auto">by {review.reviewer.display_name}</span>
        </div>

        {/* Target content */}
        {target && (
          <div className="bg-muted p-4 rounded-md mb-4">
            <p className="text-sm font-medium mb-2">{"title" in target ? (target as Question).title : "Answer"}</p>
            <p className="text-sm whitespace-pre-wrap">{"body" in target ? (target as Answer).body : ""}</p>
          </div>
        )}

        {/* Verdict actions */}
        {isReviewer && review.verdict === "pending" && (
          <div className="border-t border-border pt-4">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Review comment (optional for approve, recommended for others)"
              className="w-full border border-border rounded-md p-3 min-h-[80px] bg-background text-sm mb-3"
            />
            <div className="flex gap-2">
              <button onClick={() => handleVerdict("approved")} className="bg-green-600 text-white px-4 py-2 rounded-md text-sm">Approve</button>
              <button onClick={() => handleVerdict("changes_requested")} className="bg-yellow-600 text-white px-4 py-2 rounded-md text-sm">Request Changes</button>
              <button onClick={() => handleVerdict("rejected")} className="bg-red-600 text-white px-4 py-2 rounded-md text-sm">Reject</button>
            </div>
          </div>
        )}

        {review.comment && (
          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-sm font-medium mb-1">Review Comment</p>
            <p className="text-sm text-muted-foreground">{review.comment}</p>
          </div>
        )}
      </div>

      {/* Comments thread */}
      <h2 className="font-semibold text-lg mb-3">Discussion</h2>
      <div className="space-y-3 mb-4">
        {review.comments.map((c) => (
          <div key={c.id} className={`bg-background p-3 rounded border border-border text-sm ${c.parent_id ? "ml-8" : ""}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium">{c.author.display_name}</span>
              <span className="text-xs text-muted-foreground">{new Date(c.created_at).toLocaleString()}</span>
            </div>
            <p>{c.body}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          className="flex-1 border border-border rounded-md px-3 py-2 text-sm bg-background"
        />
        <button onClick={handleAddComment} disabled={!newComment.trim()} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm disabled:opacity-50">Comment</button>
      </div>
    </div>
  );
}
