import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, Question, Answer } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function QuestionDetail() {
  const { id } = useParams<{ id: string }>();
  const { hasRole } = useAuth();
  const [question, setQuestion] = useState<Question | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [newAnswer, setNewAnswer] = useState("");
  const [error, setError] = useState("");

  const loadQuestion = () => {
    if (!id) return;
    api.get<Question>(`/questions/${id}`).then(setQuestion).catch(() => setError("Question not found"));
    api.get<{ answers: Answer[]; total: number }>(`/questions/${id}/answers`).then((d) => setAnswers(d.answers));
  };

  useEffect(loadQuestion, [id]);

  const handleAction = async (action: string) => {
    if (!id) return;
    try {
      const updated = await api.post<Question>(`/questions/${id}/${action}`);
      setQuestion(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  };

  const handleSubmitAnswer = async () => {
    if (!id || !newAnswer.trim()) return;
    try {
      const answer = await api.post<Answer>(`/questions/${id}/answers`, { body: newAnswer });
      // Auto-submit
      await api.post<Answer>(`/answers/${answer.id}/submit`);
      setNewAnswer("");
      loadQuestion();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submit failed");
    }
  };

  if (!question) return <p className="text-center py-8 text-muted-foreground">{error || "Loading..."}</p>;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-xs px-2 py-1 rounded-full bg-primary/10 font-medium">{question.status}</span>
          {question.category && <span className="text-sm text-muted-foreground">{question.category}</span>}
        </div>
        <h1 className="text-2xl font-bold mb-3">{question.title}</h1>
        <p className="whitespace-pre-wrap text-foreground/80">{question.body}</p>
        <div className="text-sm text-muted-foreground mt-4">
          by {question.created_by.display_name} &middot; {new Date(question.created_at).toLocaleDateString()}
        </div>

        {hasRole("admin") && (
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
          </div>
        )}
      </div>

      {error && <p className="text-destructive text-sm mb-4">{error}</p>}

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
      </div>
    </div>
  );
}
