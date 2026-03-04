import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Question } from "@/api/client";

export function QuestionCreate() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleCreate = async (andSubmit: boolean) => {
    if (!title.trim() || !body.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const q = await api.post<Question>("/questions", {
        title: title.trim(),
        body: body.trim(),
        category: category.trim() || undefined,
      });
      if (andSubmit) {
        await api.post(`/questions/${q.id}/submit`);
      }
      navigate(`/questions/${q.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create question");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">New Question</h1>
      <div className="bg-background p-6 rounded-lg border border-border space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full border border-border rounded-md px-3 py-2 bg-background text-sm"
            placeholder="What do you want to know?"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Body</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="w-full border border-border rounded-md p-3 min-h-[200px] bg-background text-sm"
            placeholder="Provide context, constraints, and what a good answer looks like..."
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Category (optional)</label>
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full border border-border rounded-md px-3 py-2 bg-background text-sm"
            placeholder="e.g. engineering, process, domain-knowledge"
          />
        </div>

        {error && <p className="text-destructive text-sm">{error}</p>}

        <div className="flex gap-3 pt-2">
          <button
            onClick={() => handleCreate(true)}
            disabled={!title.trim() || !body.trim() || submitting}
            className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50"
          >
            Create &amp; Submit for Review
          </button>
          <button
            onClick={() => handleCreate(false)}
            disabled={!title.trim() || !body.trim() || submitting}
            className="border border-border px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50"
          >
            Save as Draft
          </button>
        </div>
      </div>
    </div>
  );
}
