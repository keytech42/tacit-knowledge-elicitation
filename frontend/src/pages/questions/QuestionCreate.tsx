import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Question } from "@/api/client";

export function QuestionCreate() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("");
  const [minApprovals, setMinApprovals] = useState(1);
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
        review_policy: minApprovals > 1 ? { min_approvals: minApprovals } : null,
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

        {/* Review Settings */}
        <div className="space-y-3">
          <h3 className="text-sm font-medium">Review Settings</h3>
          <div className="flex items-center gap-3">
            <label className="text-sm text-muted-foreground">Required approvals</label>
            <input
              type="number"
              min={1}
              max={10}
              value={minApprovals}
              onChange={(e) => setMinApprovals(Number(e.target.value))}
              className="w-20 border border-border rounded-md px-3 py-2 text-sm bg-background"
            />
          </div>
          <p className="text-xs text-muted-foreground">Number of reviewer approvals required before an answer is accepted (default: 1)</p>
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
