import { useEffect, useState } from "react";
import { api } from "@/api/client";

interface AILog {
  id: string;
  service_user: { display_name: string };
  model_id: string | null;
  endpoint: string;
  response_status: number;
  latency_ms: number | null;
  feedback_rating: number | null;
  feedback_comment: string | null;
  created_at: string;
}

export function AILogs() {
  const [logs, setLogs] = useState<AILog[]>([]);
  const [total, setTotal] = useState(0);
  const [feedbackId, setFeedbackId] = useState<string | null>(null);
  const [rating, setRating] = useState(3);
  const [comment, setComment] = useState("");

  useEffect(() => {
    api.get<{ logs: AILog[]; total: number }>("/ai-logs").then((d) => {
      setLogs(d.logs);
      setTotal(d.total);
    });
  }, []);

  const handleFeedback = async () => {
    if (!feedbackId) return;
    await api.post(`/ai-logs/${feedbackId}/feedback`, { rating, comment: comment || null });
    setFeedbackId(null);
    setComment("");
    // Reload
    api.get<{ logs: AILog[]; total: number }>("/ai-logs").then((d) => setLogs(d.logs));
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">AI Interaction Logs ({total})</h1>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 pr-4 font-medium">Service Account</th>
              <th className="py-2 pr-4 font-medium">Endpoint</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 pr-4 font-medium">Latency</th>
              <th className="py-2 pr-4 font-medium">Feedback</th>
              <th className="py-2 font-medium">Time</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="border-b border-border hover:bg-muted/50">
                <td className="py-2 pr-4">{log.service_user.display_name}</td>
                <td className="py-2 pr-4 font-mono text-xs">{log.endpoint}</td>
                <td className="py-2 pr-4">
                  <span className={`text-xs px-2 py-0.5 rounded ${log.response_status < 400 ? "bg-status-green/10 text-status-green" : "bg-status-red/10 text-status-red"}`}>
                    {log.response_status}
                  </span>
                </td>
                <td className="py-2 pr-4 text-muted-foreground">{log.latency_ms ?? "-"}ms</td>
                <td className="py-2 pr-4">
                  {log.feedback_rating ? (
                    <span className="text-xs">{"★".repeat(log.feedback_rating)}{"☆".repeat(5 - log.feedback_rating)}</span>
                  ) : (
                    <button onClick={() => setFeedbackId(log.id)} className="text-xs text-primary hover:underline">Add feedback</button>
                  )}
                </td>
                <td className="py-2 text-xs text-muted-foreground">{new Date(log.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Feedback modal */}
      {feedbackId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background p-6 rounded-lg max-w-md w-full">
            <h3 className="font-semibold mb-4">Submit Feedback</h3>
            <label className="block text-sm mb-2">
              Rating (1-5):
              <select value={rating} onChange={(e) => setRating(Number(e.target.value))} className="ml-2 border border-border rounded px-2 py-1 text-sm">
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (optional)" className="w-full border border-border rounded-md p-3 min-h-[80px] text-sm mb-3" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setFeedbackId(null)} className="border border-border px-4 py-2 rounded-md text-sm">Cancel</button>
              <button onClick={handleFeedback} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm">Submit</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
