import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api, Question, Answer } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function QuestionDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, hasRole } = useAuth();
  const navigate = useNavigate();
  const [question, setQuestion] = useState<Question | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [newAnswer, setNewAnswer] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editBody, setEditBody] = useState("");
  const [editCategory, setEditCategory] = useState("");
  // feedback
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  const loadQuestion = () => {
    if (!id) return;
    api.get<Question>(`/questions/${id}`).then((q) => {
      setQuestion(q);
      setEditTitle(q.title);
      setEditBody(q.body);
      setEditCategory(q.category || "");
    }).catch(() => setError("Question not found"));
    api.get<{ answers: Answer[]; total: number }>(`/questions/${id}/answers`).then((d) => setAnswers(d.answers));
  };

  useEffect(loadQuestion, [id]);

  const handleAction = async (action: string) => {
    if (!id) return;
    try {
      const updated = await api.post<Question>(`/questions/${id}/${action}`);
      setQuestion(updated);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  };

  const handleSaveEdit = async () => {
    if (!id || !editTitle.trim() || !editBody.trim()) return;
    try {
      const updated = await api.patch<Question>(`/questions/${id}`, {
        title: editTitle.trim(),
        body: editBody.trim(),
        category: editCategory.trim() || null,
      });
      setQuestion(updated);
      setEditing(false);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  };

  const handleDelete = async () => {
    if (!id || !confirm("Delete this question? This cannot be undone.")) return;
    try {
      await api.delete(`/questions/${id}`);
      navigate("/questions");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleSubmitAnswer = async () => {
    if (!id || !newAnswer.trim()) return;
    try {
      const answer = await api.post<Answer>(`/questions/${id}/answers`, { body: newAnswer });
      await api.post<Answer>(`/answers/${answer.id}/submit`);
      setNewAnswer("");
      loadQuestion();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submit failed");
    }
  };

  const handleSubmitFeedback = async () => {
    if (!id || feedbackRating < 1) return;
    try {
      await api.post(`/questions/${id}/feedback`, {
        rating: feedbackRating,
        comment: feedbackComment.trim() || undefined,
      });
      setFeedbackSubmitted(true);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Feedback failed");
    }
  };

  if (!question) return <p className="text-center py-8 text-muted-foreground">{error || "Loading..."}</p>;

  const isAuthor = user?.id === question.created_by.id;
  const canEdit = (isAuthor || hasRole("admin")) && question.status === "draft";
  const canSubmit = (isAuthor || hasRole("admin")) && question.status === "draft";
  const canDelete = (isAuthor || hasRole("admin")) && question.status === "draft";

  const STATUS_COLORS: Record<string, string> = {
    draft: "bg-gray-200 text-gray-700",
    proposed: "bg-yellow-100 text-yellow-800",
    in_review: "bg-blue-100 text-blue-800",
    published: "bg-green-100 text-green-800",
    closed: "bg-red-100 text-red-800",
    archived: "bg-gray-100 text-gray-500",
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        <div className="flex items-center gap-3 mb-4">
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLORS[question.status] || "bg-gray-100"}`}>
            {question.status}
          </span>
          {question.category && <span className="text-sm text-muted-foreground">{question.category}</span>}
          {question.quality_score != null && (
            <span className="text-sm text-muted-foreground ml-auto">Score: {question.quality_score.toFixed(1)}/5</span>
          )}
        </div>

        {editing ? (
          <div className="space-y-3">
            <input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="w-full border border-border rounded-md px-3 py-2 bg-background text-sm font-semibold"
            />
            <textarea
              value={editBody}
              onChange={(e) => setEditBody(e.target.value)}
              className="w-full border border-border rounded-md p-3 min-h-[150px] bg-background text-sm"
            />
            <input
              value={editCategory}
              onChange={(e) => setEditCategory(e.target.value)}
              placeholder="Category (optional)"
              className="w-full border border-border rounded-md px-3 py-2 bg-background text-sm"
            />
            <div className="flex gap-2">
              <button onClick={handleSaveEdit} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm">Save</button>
              <button onClick={() => setEditing(false)} className="border border-border px-4 py-2 rounded-md text-sm">Cancel</button>
            </div>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold mb-3">{question.title}</h1>
            <p className="whitespace-pre-wrap text-foreground/80">{question.body}</p>
            <div className="text-sm text-muted-foreground mt-4">
              by {question.created_by.display_name} &middot; {new Date(question.created_at).toLocaleDateString()}
            </div>
          </>
        )}

        {/* Author actions */}
        {!editing && (canEdit || canSubmit || canDelete) && (
          <div className="flex gap-2 mt-4 pt-4 border-t border-border">
            {canEdit && <button onClick={() => setEditing(true)} className="bg-secondary text-secondary-foreground px-3 py-1.5 rounded text-sm">Edit</button>}
            {canSubmit && <button onClick={() => handleAction("submit")} className="bg-primary text-primary-foreground px-3 py-1.5 rounded text-sm">Submit for Review</button>}
            {canDelete && <button onClick={handleDelete} className="bg-red-600 text-white px-3 py-1.5 rounded text-sm">Delete</button>}
          </div>
        )}

        {/* Admin actions */}
        {!editing && hasRole("admin") && (
          <div className="flex gap-2 mt-4 pt-4 border-t border-border">
            {question.status === "proposed" && (
              <button onClick={() => handleAction("start-review")} className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm">Start Review</button>
            )}
            {question.status === "in_review" && (
              <>
                <button onClick={() => handleAction("publish")} className="bg-green-600 text-white px-3 py-1.5 rounded text-sm">Publish</button>
                <button onClick={() => handleAction("reject")} className="bg-red-600 text-white px-3 py-1.5 rounded text-sm">Reject</button>
              </>
            )}
            {question.status === "published" && (
              <button onClick={() => handleAction("close")} className="bg-gray-600 text-white px-3 py-1.5 rounded text-sm">Close</button>
            )}
            {question.status === "closed" && (
              <button onClick={() => handleAction("archive")} className="bg-gray-500 text-white px-3 py-1.5 rounded text-sm">Archive</button>
            )}
          </div>
        )}
      </div>

      {error && <p className="text-destructive text-sm mb-4">{error}</p>}

      {/* Quality feedback for published/closed questions */}
      {(question.status === "published" || question.status === "closed") && !feedbackSubmitted && (
        <div className="bg-background p-4 rounded-lg border border-border mb-6">
          <h2 className="font-semibold mb-2 text-sm">Rate this question</h2>
          <div className="flex items-center gap-1 mb-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                onClick={() => setFeedbackRating(n)}
                className={`w-8 h-8 rounded text-sm font-medium ${n <= feedbackRating ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"}`}
              >
                {n}
              </button>
            ))}
          </div>
          <input
            value={feedbackComment}
            onChange={(e) => setFeedbackComment(e.target.value)}
            placeholder="Optional comment"
            className="w-full border border-border rounded-md px-3 py-1.5 bg-background text-sm mb-2"
          />
          <button
            onClick={handleSubmitFeedback}
            disabled={feedbackRating < 1}
            className="bg-primary text-primary-foreground px-3 py-1.5 rounded text-sm disabled:opacity-50"
          >
            Submit Feedback
          </button>
        </div>
      )}

      {/* Answer form for published questions */}
      {question.status === "published" && (
        <div className="bg-background p-6 rounded-lg border border-border mb-6">
          <h2 className="font-semibold mb-3">Submit Your Answer</h2>
          {question.show_suggestions && question.answer_options.length > 0 && (
            <div className="mb-4">
              <p className="text-sm text-muted-foreground mb-2">Suggested starting points:</p>
              <div className="space-y-2">
                {question.answer_options.map((opt) => (
                  <button
                    key={opt.id}
                    onClick={() => setNewAnswer(opt.body)}
                    className="block w-full text-left p-3 border border-border rounded-md hover:bg-muted text-sm"
                  >
                    {opt.body}
                  </button>
                ))}
              </div>
            </div>
          )}
          <textarea
            value={newAnswer}
            onChange={(e) => setNewAnswer(e.target.value)}
            className="w-full border border-border rounded-md p-3 min-h-[120px] bg-background text-sm"
            placeholder="Write your answer..."
          />
          <button
            onClick={handleSubmitAnswer}
            disabled={!newAnswer.trim()}
            className="mt-3 bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50"
          >
            Submit Answer
          </button>
        </div>
      )}

      {/* Answers list */}
      <h2 className="font-semibold text-lg mb-3">Answers ({answers.length})</h2>
      <div className="space-y-3">
        {answers.map((a) => (
          <Link key={a.id} to={`/answers/${a.id}`} className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-xs px-2 py-1 rounded-full bg-secondary font-medium">{a.status}</span>
              <span className="text-xs text-muted-foreground">v{a.current_version}</span>
            </div>
            <p className="text-sm line-clamp-3">{a.body}</p>
            <div className="text-xs text-muted-foreground mt-2">
              by {a.author.display_name} &middot; {new Date(a.created_at).toLocaleDateString()}
            </div>
          </Link>
        ))}
        {answers.length === 0 && (
          <p className="text-center text-muted-foreground py-4">No answers yet.</p>
        )}
      </div>
    </div>
  );
}
