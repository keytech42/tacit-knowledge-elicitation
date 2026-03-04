import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Review } from "@/api/client";

export function ReviewQueue() {
  const [reviews, setReviews] = useState<Review[]>([]);

  useEffect(() => {
    api.get<Review[]>("/reviews/my-queue").then(setReviews);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">My Review Queue</h1>
      <div className="space-y-3">
        {reviews.map((rev) => (
          <Link
            key={rev.id}
            to={`/reviews/${rev.id}`}
            className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30"
          >
            <div className="flex items-center gap-3">
              <span className="text-xs px-2 py-1 rounded-full bg-yellow-100 text-yellow-800 font-medium">
                {rev.verdict}
              </span>
              <span className="text-sm font-medium">{rev.target_type}</span>
              <span className="text-xs text-muted-foreground ml-auto">{new Date(rev.created_at).toLocaleDateString()}</span>
            </div>
          </Link>
        ))}
        {reviews.length === 0 && <p className="text-center text-muted-foreground py-8">No pending reviews.</p>}
      </div>
    </div>
  );
}
