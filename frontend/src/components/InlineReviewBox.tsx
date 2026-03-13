import { useState } from "react";
import { api, ApiError, Review } from "@/api/client";
import { ActionButton } from "@/components/ActionButton";

interface InlineReviewBoxProps {
  review: Review;
  onVerdictSubmitted: () => void;
}

export function InlineReviewBox({ review, onVerdictSubmitted }: InlineReviewBoxProps) {
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submitVerdict = async (verdict: string) => {
    setLoading(true);
    setError("");
    try {
      await api.patch<Review>(`/reviews/${review.id}`, {
        verdict,
        ...(comment.trim() ? { comment: comment.trim() } : {}),
      });
      onVerdictSubmitted();
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setError("Review already submitted. Refreshing...");
        setTimeout(onVerdictSubmitted, 1000);
      } else {
        setError(err instanceof Error ? err.message : "Failed to submit review");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border border-border rounded-lg p-4 bg-background">
      <h3 className="text-sm font-semibold mb-3">Submit Your Review</h3>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Leave a comment (optional)"
        className="w-full border border-border rounded-md p-3 min-h-[80px] bg-background text-sm mb-3 resize-y"
      />
      {error && <p className="text-destructive text-xs mb-2">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="Approve"
          onClick={() => submitVerdict("approved")}
          enabled={!loading}
          variant="green"
          loading={loading}
        />
        <ActionButton
          label="Request Changes"
          onClick={() => submitVerdict("changes_requested")}
          enabled={!loading}
          variant="blue"
          loading={loading}
        />
        <ActionButton
          label="Reject"
          onClick={() => submitVerdict("rejected")}
          enabled={!loading}
          variant="danger"
          loading={loading}
        />
      </div>
    </div>
  );
}
