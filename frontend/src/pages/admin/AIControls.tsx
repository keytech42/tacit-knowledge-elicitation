import { useState } from "react";
import { ai, TaskAccepted, TaskStatus, Recommendation } from "@/api/client";

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    accepted: "bg-blue-100 text-blue-700",
    running: "bg-yellow-100 text-yellow-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${colors[status] || "bg-muted text-muted-foreground"}`}>
      {status}
    </span>
  );
}

export function AIControls() {
  // Question generation
  const [topic, setTopic] = useState("");
  const [domain, setDomain] = useState("");
  const [count, setCount] = useState(3);
  const [genContext, setGenContext] = useState("");
  const [genTask, setGenTask] = useState<TaskStatus | null>(null);
  const [genLoading, setGenLoading] = useState(false);

  // Scaffold options
  const [scaffoldQId, setScaffoldQId] = useState("");
  const [scaffoldTask, setScaffoldTask] = useState<TaskStatus | null>(null);
  const [scaffoldLoading, setScaffoldLoading] = useState(false);

  // Review assist
  const [reviewAnswerId, setReviewAnswerId] = useState("");
  const [reviewTask, setReviewTask] = useState<TaskStatus | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);

  // Recommendations
  const [recQId, setRecQId] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recLoading, setRecLoading] = useState(false);

  const pollTask = async (taskId: string, setter: (t: TaskStatus) => void) => {
    const poll = async () => {
      try {
        const status = await ai.getTaskStatus(taskId);
        setter(status);
        if (status.status === "accepted" || status.status === "running") {
          setTimeout(poll, 2000);
        }
      } catch {
        // stop polling on error
      }
    };
    poll();
  };

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setGenLoading(true);
    try {
      const result = await ai.generateQuestions(topic, domain, count, genContext || undefined);
      setGenTask({ task_id: result.task_id, status: result.status });
      pollTask(result.task_id, setGenTask);
    } catch (e: unknown) {
      setGenTask({ task_id: "", status: "failed", error: e instanceof Error ? e.message : "Unknown error" });
    }
    setGenLoading(false);
  };

  const handleScaffold = async () => {
    if (!scaffoldQId.trim()) return;
    setScaffoldLoading(true);
    try {
      const result = await ai.scaffoldOptions(scaffoldQId);
      setScaffoldTask({ task_id: result.task_id, status: result.status });
      pollTask(result.task_id, setScaffoldTask);
    } catch (e: unknown) {
      setScaffoldTask({ task_id: "", status: "failed", error: e instanceof Error ? e.message : "Unknown error" });
    }
    setScaffoldLoading(false);
  };

  const handleReviewAssist = async () => {
    if (!reviewAnswerId.trim()) return;
    setReviewLoading(true);
    try {
      const result = await ai.reviewAssist(reviewAnswerId);
      setReviewTask({ task_id: result.task_id, status: result.status });
      pollTask(result.task_id, setReviewTask);
    } catch (e: unknown) {
      setReviewTask({ task_id: "", status: "failed", error: e instanceof Error ? e.message : "Unknown error" });
    }
    setReviewLoading(false);
  };

  const handleRecommend = async () => {
    if (!recQId.trim()) return;
    setRecLoading(true);
    try {
      const results = await ai.recommend(recQId);
      setRecommendations(results);
    } catch {
      setRecommendations([]);
    }
    setRecLoading(false);
  };

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">AI Controls</h1>

      {/* Question Generation */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Generate Questions</h2>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium mb-1">Topic *</label>
            <input
              value={topic} onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. engineering trade-offs"
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Domain</label>
            <input
              value={domain} onChange={(e) => setDomain(e.target.value)}
              placeholder="e.g. software architecture"
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Count</label>
            <input
              type="number" min={1} max={10} value={count}
              onChange={(e) => setCount(parseInt(e.target.value) || 3)}
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Additional Context</label>
            <input
              value={genContext} onChange={(e) => setGenContext(e.target.value)}
              placeholder="Optional context..."
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
        </div>
        <button
          onClick={handleGenerate} disabled={genLoading || !topic.trim()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
        >
          {genLoading ? "Submitting..." : "Generate Questions"}
        </button>
        {genTask && (
          <div className="mt-3 p-3 bg-muted rounded-md text-sm">
            <div className="flex items-center gap-2">
              <StatusBadge status={genTask.status} />
              {genTask.task_id && <span className="text-muted-foreground text-xs">ID: {genTask.task_id.slice(0, 8)}...</span>}
            </div>
            {genTask.error && <p className="text-destructive mt-1">{genTask.error}</p>}
            {genTask.result && (
              <p className="mt-1 text-muted-foreground">
                Created {(genTask.result as Record<string, unknown>).count} questions
              </p>
            )}
          </div>
        )}
      </section>

      {/* Answer Option Scaffolding */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Scaffold Answer Options</h2>
        <div className="flex gap-4 mb-4">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1">Question ID *</label>
            <input
              value={scaffoldQId} onChange={(e) => setScaffoldQId(e.target.value)}
              placeholder="UUID of the question"
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
        </div>
        <button
          onClick={handleScaffold} disabled={scaffoldLoading || !scaffoldQId.trim()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
        >
          {scaffoldLoading ? "Submitting..." : "Generate Options"}
        </button>
        {scaffoldTask && (
          <div className="mt-3 p-3 bg-muted rounded-md text-sm">
            <StatusBadge status={scaffoldTask.status} />
            {scaffoldTask.error && <p className="text-destructive mt-1">{scaffoldTask.error}</p>}
            {scaffoldTask.result && <p className="mt-1 text-muted-foreground">Options created</p>}
          </div>
        )}
      </section>

      {/* Review Assist */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">AI Review Assist</h2>
        <div className="flex gap-4 mb-4">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1">Answer ID *</label>
            <input
              value={reviewAnswerId} onChange={(e) => setReviewAnswerId(e.target.value)}
              placeholder="UUID of the answer"
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
        </div>
        <button
          onClick={handleReviewAssist} disabled={reviewLoading || !reviewAnswerId.trim()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
        >
          {reviewLoading ? "Submitting..." : "Run AI Review"}
        </button>
        {reviewTask && (
          <div className="mt-3 p-3 bg-muted rounded-md text-sm">
            <StatusBadge status={reviewTask.status} />
            {reviewTask.error && <p className="text-destructive mt-1">{reviewTask.error}</p>}
            {reviewTask.result && (
              <p className="mt-1 text-muted-foreground">
                Verdict: {(reviewTask.result as Record<string, unknown>).verdict},
                Confidence: {String((reviewTask.result as Record<string, unknown>).confidence)},
                Submitted: {String((reviewTask.result as Record<string, unknown>).submitted)}
              </p>
            )}
          </div>
        )}
      </section>

      {/* Respondent Recommendations */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Respondent Recommendations</h2>
        <div className="flex gap-4 mb-4">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-1">Question ID *</label>
            <input
              value={recQId} onChange={(e) => setRecQId(e.target.value)}
              placeholder="UUID of the published question"
              className="w-full border border-border rounded-md px-3 py-2 text-sm"
            />
          </div>
        </div>
        <button
          onClick={handleRecommend} disabled={recLoading || !recQId.trim()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50"
        >
          {recLoading ? "Loading..." : "Get Recommendations"}
        </button>
        {recommendations.length > 0 && (
          <div className="mt-4 border border-border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Respondent</th>
                  <th className="text-left px-3 py-2 font-medium">Score</th>
                  <th className="text-left px-3 py-2 font-medium">Reasoning</th>
                </tr>
              </thead>
              <tbody>
                {recommendations.map((r) => (
                  <tr key={r.user_id} className="border-t border-border">
                    <td className="px-3 py-2">{r.display_name}</td>
                    <td className="px-3 py-2">{(r.score * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.reasoning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
