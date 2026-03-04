import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Question } from "@/api/client";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-200 text-gray-700",
  proposed: "bg-yellow-100 text-yellow-800",
  in_review: "bg-blue-100 text-blue-800",
  published: "bg-green-100 text-green-800",
  closed: "bg-red-100 text-red-800",
  archived: "bg-gray-100 text-gray-500",
};

export function QuestionList() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    const params = statusFilter ? `?status=${statusFilter}` : "";
    api.get<{ questions: Question[]; total: number }>(`/questions${params}`).then((data) => {
      setQuestions(data.questions);
      setTotal(data.total);
    });
  }, [statusFilter]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Questions ({total})</h1>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-border rounded-md px-3 py-2 text-sm bg-background"
        >
          <option value="">All statuses</option>
          <option value="published">Published</option>
          <option value="draft">Draft</option>
          <option value="proposed">Proposed</option>
          <option value="in_review">In Review</option>
          <option value="closed">Closed</option>
        </select>
      </div>
      <div className="space-y-3">
        {questions.map((q) => (
          <Link
            key={q.id}
            to={`/questions/${q.id}`}
            className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30 transition-colors"
          >
            <div className="flex items-center gap-3 mb-2">
              <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLORS[q.status] || "bg-gray-100"}`}>
                {q.status}
              </span>
              {q.category && <span className="text-xs text-muted-foreground">{q.category}</span>}
              {q.quality_score && <span className="text-xs text-muted-foreground">Score: {q.quality_score.toFixed(1)}</span>}
            </div>
            <h3 className="font-semibold">{q.title}</h3>
            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{q.body}</p>
            <div className="text-xs text-muted-foreground mt-2">
              by {q.created_by.display_name} &middot; {new Date(q.created_at).toLocaleDateString()}
            </div>
          </Link>
        ))}
        {questions.length === 0 && (
          <p className="text-center text-muted-foreground py-8">No questions found.</p>
        )}
      </div>
    </div>
  );
}
