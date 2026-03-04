import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Question } from "@/api/client";

export function QuestionReviewQueue() {
  const [proposed, setProposed] = useState<Question[]>([]);
  const [inReview, setInReview] = useState<Question[]>([]);

  useEffect(() => {
    api.get<{ questions: Question[] }>("/questions?status=proposed").then((d) => setProposed(d.questions));
    api.get<{ questions: Question[] }>("/questions?status=in_review").then((d) => setInReview(d.questions));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Question Review Queue</h1>

      <h2 className="font-semibold text-lg mb-3">Proposed ({proposed.length})</h2>
      <div className="space-y-2 mb-8">
        {proposed.map((q) => (
          <Link key={q.id} to={`/questions/${q.id}`} className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30">
            <h3 className="font-medium">{q.title}</h3>
            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{q.body}</p>
            <div className="text-xs text-muted-foreground mt-2">by {q.created_by.display_name}</div>
          </Link>
        ))}
        {proposed.length === 0 && <p className="text-sm text-muted-foreground">No proposed questions.</p>}
      </div>

      <h2 className="font-semibold text-lg mb-3">In Review ({inReview.length})</h2>
      <div className="space-y-2">
        {inReview.map((q) => (
          <Link key={q.id} to={`/questions/${q.id}`} className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30">
            <h3 className="font-medium">{q.title}</h3>
            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{q.body}</p>
          </Link>
        ))}
        {inReview.length === 0 && <p className="text-sm text-muted-foreground">No questions in review.</p>}
      </div>
    </div>
  );
}
