import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api, ai, Question, Answer, Recommendation, TaskStatus } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ActionButton } from "@/components/ActionButton";
import { Admonition } from "@/components/Admonition";
import { MarkdownContent } from "@/components/MarkdownContent";
import { StatusBadge, WORKFLOW_HINTS } from "@/components/StatusBadge";

function editPermission(isAdmin: boolean, isAuthor: boolean, status: string) {
  if (status === "archived") return { enabled: false, reason: "Archived questions are read-only" };
  if (isAdmin) return { enabled: true };
  if (isAuthor && status === "draft") return { enabled: true };
  if (isAuthor && status === "proposed")
    return { enabled: false, reason: "Under review — editing is locked", hint: "Wait for admin to reject back to draft, or ask an admin to make the edit" };
  if (isAuthor)
    return { enabled: false, reason: "Only admins can edit in this state", hint: "Contact an admin if corrections are needed" };
  return { enabled: false, reason: "Only the author or an admin can edit" };
}

function submitPermission(isAdmin: boolean, isAuthor: boolean, status: string) {
  if ((isAuthor || isAdmin) && status === "draft") return { enabled: true };
  if (status !== "draft")
    return { enabled: false, reason: "Already submitted for review", hint: "Question is in the review pipeline" };
  return { enabled: false, reason: "Only the author or an admin can submit" };
}

function deletePermission(isAdmin: boolean, isAuthor: boolean, status: string) {
  if (isAdmin) return { enabled: true };
  if (isAuthor && status === "draft") return { enabled: true };
  if (isAuthor)
    return { enabled: false, reason: "Only draft questions can be deleted by authors", hint: "Ask an admin to delete or archive it instead" };
  return { enabled: false, reason: "Only the author or an admin can delete" };
}

type AdminAction = { action: string; label: string; variant: "blue" | "green" | "danger" | "gray" };
const ADMIN_PIPELINE: AdminAction[] = [
  { action: "start-review", label: "Start Review", variant: "blue" },
  { action: "publish", label: "Publish", variant: "green" },
  { action: "reject", label: "Reject", variant: "danger" },
  { action: "close", label: "Close", variant: "gray" },
  { action: "archive", label: "Archive", variant: "gray" },
];

const ADMIN_ACTION_ENABLED_STATUS: Record<string, string> = {
  "start-review": "proposed",
  publish: "in_review",
  reject: "in_review",
  close: "published",
  archive: "closed",
};

function adminActionPermission(action: string, status: string) {
  const requiredStatus = ADMIN_ACTION_ENABLED_STATUS[action];
  if (status === requiredStatus) return { enabled: true };
  if (status === "archived") return { enabled: false, reason: "Question is archived" };

  // Build a contextual message
  const statusOrder = ["draft", "proposed", "in_review", "published", "closed", "archived"];
  const currentIdx = statusOrder.indexOf(status);
  const requiredIdx = statusOrder.indexOf(requiredStatus);
  if (currentIdx < requiredIdx)
    return { enabled: false, reason: `Not ready yet — question must reach "${requiredStatus.replace(/_/g, " ")}" state first` };
  return { enabled: false, reason: "Already past this stage" };
}

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
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);

  // AI features
  const [scaffoldTask, setScaffoldTask] = useState<TaskStatus | null>(null);
  const [scaffoldLoading, setScaffoldLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recReason, setRecReason] = useState<string | null>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [assignLoading, setAssignLoading] = useState<string | null>(null);

  const loadQuestion = () => {
    if (!id) return;
    api.get<Question>(`/questions/${id}`).then((q) => {
      setQuestion(q);
      setEditTitle(q.title);
      setEditBody(q.body);
      setEditCategory(q.category || "");
    }).catch((err) => setError(err instanceof Error ? err.message : "Question not found"));
    api.get<{ answers: Answer[]; total: number }>(`/questions/${id}/answers`).then((d) => setAnswers(d.answers)).catch(() => {});
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
      setSelectedOptionId(null);
      loadQuestion();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submit failed");
    }
  };

  const handleOptionClick = (optId: string, optBody: string) => {
    if (selectedOptionId === optId) {
      setSelectedOptionId(null);
      setNewAnswer("");
    } else {
      setSelectedOptionId(optId);
      setNewAnswer(optBody);
    }
  };

  const handleAnswerChange = (value: string) => {
    setNewAnswer(value);
    if (selectedOptionId && question) {
      const selectedOpt = question.answer_options.find((o) => o.id === selectedOptionId);
      if (selectedOpt && value !== selectedOpt.body) {
        setSelectedOptionId(null);
      }
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

  const handleScaffoldOptions = async () => {
    if (!id || scaffoldLoading) return;
    setScaffoldLoading(true);
    try {
      const result = await ai.scaffoldOptions(id);
      setScaffoldTask({ task_id: result.task_id, status: result.status });
      const poll = async () => {
        try {
          const status = await ai.getTaskStatus(result.task_id);
          setScaffoldTask(status);
          if (status.status === "accepted" || status.status === "running") {
            setTimeout(poll, 2000);
          } else if (status.status === "completed") {
            loadQuestion(); // Reload to show new options
          }
        } catch { /* stop polling */ }
      };
      poll();
    } catch (e: unknown) {
      setScaffoldTask({ task_id: "", status: "failed", error: e instanceof Error ? e.message : "Failed" });
    }
    setScaffoldLoading(false);
  };

  const handleGetRecommendations = async () => {
    if (!id || recLoading) return;
    setRecLoading(true);
    setRecReason(null);
    try {
      const resp = await ai.recommend(id);
      setRecommendations(resp.items);
      setRecReason(resp.reason);
    } catch (e: unknown) {
      setRecommendations([]);
      setRecReason(e instanceof Error ? e.message : "Failed to get recommendations.");
    }
    setRecLoading(false);
  };

  const handleAssignRespondent = async (userId: string) => {
    if (!id || assignLoading) return;
    setAssignLoading(userId);
    try {
      const updated = await ai.assignRespondent(id, userId);
      setQuestion(updated);
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Assignment failed");
    }
    setAssignLoading(null);
  };

  if (!question) return <p className="text-center py-8 text-muted-foreground">{error || "Loading..."}</p>;

  const isAuthor = user?.id === question.created_by.id;
  const isAdmin = hasRole("admin");
  const showAuthorActions = isAuthor || isAdmin;
  const editPerm = editPermission(isAdmin, isAuthor, question.status);
  const submitPerm = submitPermission(isAdmin, isAuthor, question.status);
  const deletePerm = deletePermission(isAdmin, isAuthor, question.status);

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        {/* Status + workflow hint */}
        <div className="flex items-center gap-3 mb-1">
          <StatusBadge status={question.status} />
          {question.category && <span className="text-sm text-muted-foreground">{question.category}</span>}
          {question.assigned_respondent && (
            <span className="text-sm text-muted-foreground">Assigned: {question.assigned_respondent.display_name}</span>
          )}
          {question.quality_score != null && (
            <span className="text-sm text-muted-foreground ml-auto">Score: {question.quality_score.toFixed(1)}/5</span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-4">{WORKFLOW_HINTS[`q:${question.status}`]}</p>

        {editing ? (
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Title</label>
              <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} className="w-full border border-border rounded-md px-3 py-2 bg-background text-sm font-semibold" />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Body</label>
              <textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} className="w-full border border-border rounded-md p-3 min-h-[150px] bg-background text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Category</label>
              <input value={editCategory} onChange={(e) => setEditCategory(e.target.value)} placeholder="Category (optional)" className="w-full border border-border rounded-md px-3 py-2 bg-background text-sm" />
            </div>
            <div className="flex gap-2">
              <button onClick={handleSaveEdit} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm active:scale-[0.97] transition-all duration-150">Save</button>
              <button onClick={() => setEditing(false)} className="border border-border px-4 py-2 rounded-md text-sm active:scale-[0.97] transition-all duration-150">Cancel</button>
            </div>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold mb-3">{question.title}</h1>
            <MarkdownContent className="text-foreground/80">{question.body}</MarkdownContent>
            <div className="text-sm text-muted-foreground mt-4">
              by {question.created_by.display_name} &middot; {new Date(question.created_at).toLocaleDateString()}
            </div>
          </>
        )}

        {/* Author / edit actions — always visible */}
        {!editing && showAuthorActions && (
          <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-border">
            <ActionButton label="Edit" onClick={() => setEditing(true)} enabled={editPerm.enabled} disabledReason={editPerm.reason} disabledHint={editPerm.hint} variant="secondary" />
            <ActionButton label="Submit for Review" onClick={() => handleAction("submit")} enabled={submitPerm.enabled} disabledReason={submitPerm.reason} disabledHint={submitPerm.hint} variant="primary" />
            <ActionButton label="Delete" onClick={handleDelete} enabled={deletePerm.enabled} disabledReason={deletePerm.reason} disabledHint={deletePerm.hint} variant="danger" />
          </div>
        )}

        {/* Admin workflow pipeline — always visible for admin */}
        {!editing && isAdmin && (
          <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-border">
            <span className="text-xs text-muted-foreground self-center mr-1">Workflow:</span>
            {ADMIN_PIPELINE.map((a) => {
              const perm = adminActionPermission(a.action, question.status);
              return (
                <ActionButton
                  key={a.action}
                  label={a.label}
                  onClick={() => handleAction(a.action)}
                  enabled={perm.enabled}
                  disabledReason={perm.reason}
                  variant={a.variant}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* AI actions for admin on published questions */}
      {isAdmin && question.status === "published" && (
        <div className="bg-background p-4 rounded-lg border border-border mb-6">
          <h2 className="font-semibold text-sm mb-3">AI Actions</h2>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleScaffoldOptions}
              disabled={scaffoldLoading}
              className="bg-primary text-primary-foreground px-3 py-1.5 rounded text-sm disabled:opacity-50 active:scale-[0.97] transition-all duration-150"
            >
              {scaffoldLoading ? "Generating..." : "Generate Answer Options"}
            </button>
            <button
              onClick={handleGetRecommendations}
              disabled={recLoading}
              className="border border-border text-foreground px-3 py-1.5 rounded text-sm hover:bg-muted disabled:opacity-50 active:scale-[0.97] transition-all duration-150"
            >
              {recLoading ? "Loading..." : "Recommend Respondents"}
            </button>
          </div>
          {scaffoldTask && (
            <div className="mt-2 text-xs">
              <span className={`inline-block px-2 py-0.5 rounded-full ${
                scaffoldTask.status === "completed" ? "bg-muted text-foreground" :
                scaffoldTask.status === "failed" ? "bg-destructive/10 text-destructive" :
                "bg-muted text-muted-foreground"
              }`}>{scaffoldTask.status}</span>
              {scaffoldTask.error && <span className="text-destructive ml-2">{scaffoldTask.error}</span>}
            </div>
          )}
          {recReason && recommendations.length === 0 && (
            <div className="mt-3">
              <Admonition variant="warning" title="No recommendations available" size="xs">
                {recReason}
              </Admonition>
            </div>
          )}
          {recommendations.length > 0 && (
            <div className="mt-3 border border-border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted">
                  <tr>
                    <th className="text-left px-3 py-1.5 text-xs font-medium">Respondent</th>
                    <th className="text-left px-3 py-1.5 text-xs font-medium">Score</th>
                    <th className="text-left px-3 py-1.5 text-xs font-medium">Reasoning</th>
                    <th className="text-right px-3 py-1.5 text-xs font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {recommendations.map((r) => {
                    const isAssigned = question.assigned_respondent?.id === r.user_id;
                    return (
                    <tr key={r.user_id} className="border-t border-border">
                      <td className="px-3 py-1.5 text-xs">{r.display_name}</td>
                      <td className="px-3 py-1.5 text-xs">{(r.score * 100).toFixed(0)}%</td>
                      <td className="px-3 py-1.5 text-xs text-muted-foreground">{r.reasoning}</td>
                      <td className="px-3 py-1.5 text-xs text-right">
                        {isAssigned ? (
                          <span className="text-xs text-primary font-medium">Assigned</span>
                        ) : (
                          <button
                            onClick={() => handleAssignRespondent(r.user_id)}
                            disabled={assignLoading === r.user_id}
                            className="text-xs text-primary hover:underline disabled:opacity-50 active:scale-[0.97] transition-all duration-150"
                          >
                            {assignLoading === r.user_id ? "Assigning..." : "Assign"}
                          </button>
                        )}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {error && <p className="text-destructive text-sm mb-4">{error}</p>}

      {/* Answer form */}
      {question.status === "published" && (
        <div className="bg-background p-6 rounded-lg border border-border mb-6">
          <h2 className="font-semibold mb-1">Submit Your Answer</h2>

          {/* Answer templates */}
          {(question.show_suggestions || isAdmin) && question.answer_options.length > 0 && (
            <div className="mb-5">
              <p className="text-xs text-muted-foreground mb-3">Select a template to start with, or write from scratch</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {question.answer_options.map((opt, idx) => {
                  const isSelected = selectedOptionId === opt.id;
                  return (
                    <div key={opt.id} className="group relative">
                      <button
                        onClick={() => handleOptionClick(opt.id, opt.body)}
                        className={`relative w-full h-full flex flex-col justify-start text-left rounded-lg border bg-background p-3 overflow-hidden transition-all duration-200 ${
                          isSelected
                            ? "border-primary ring-1 ring-primary"
                            : "border-border"
                        }`}
                      >
                        <span className={`inline-block text-[10px] font-medium mb-1.5 px-1.5 py-0.5 rounded ${
                          isSelected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                        }`}>
                          {idx + 1}
                        </span>
                        <p className="text-sm text-foreground/80 leading-relaxed line-clamp-3">{opt.body}</p>
                        <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-background to-transparent pointer-events-none" />
                      </button>
                      {/* Hover overlay — identical layout, no truncation */}
                      <button
                        onClick={() => handleOptionClick(opt.id, opt.body)}
                        className={`absolute inset-x-0 top-0 z-10 hidden group-hover:flex flex-col justify-start w-full text-left rounded-lg border bg-background p-3 shadow-lg min-h-full ${
                          isSelected
                            ? "border-primary ring-1 ring-primary"
                            : "border-foreground/20"
                        }`}
                      >
                        <span className={`inline-block text-[10px] font-medium mb-1.5 px-1.5 py-0.5 rounded ${
                          isSelected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                        }`}>
                          {idx + 1}
                        </span>
                        <p className="text-sm text-foreground/80 leading-relaxed">{opt.body}</p>
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <textarea
            value={newAnswer}
            onChange={(e) => handleAnswerChange(e.target.value)}
            className="w-full border border-border rounded-lg p-3 min-h-[120px] bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-colors"
            placeholder="Write your answer..."
          />
          <div className="flex items-center justify-between mt-3">
            <div>
              {selectedOptionId && (
                <span className="text-xs text-muted-foreground">Editing from template — changes are saved to your answer</span>
              )}
            </div>
            <button onClick={handleSubmitAnswer} disabled={!newAnswer.trim()} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50 active:scale-[0.97] transition-all duration-150">
              Submit Answer
            </button>
          </div>
        </div>
      )}

      {/* Answers list */}
      <h2 className="font-semibold text-lg mb-3">Answers ({answers.length})</h2>
      <div className="space-y-3">
        {answers.map((a) => (
          <Link key={a.id} to={`/answers/${a.id}`} className="block bg-background p-4 rounded-lg border border-border hover:border-primary/30">
            <div className="flex items-center gap-3 mb-2">
              <StatusBadge status={a.status} />
              <span className="text-xs text-muted-foreground">v{a.current_version}</span>
            </div>
            <p className="text-sm line-clamp-3">{a.body}</p>
            <div className="text-xs text-muted-foreground mt-2">by {a.author.display_name} &middot; {new Date(a.created_at).toLocaleDateString()}</div>
          </Link>
        ))}
        {answers.length === 0 && <p className="text-center text-muted-foreground py-4">No answers yet.</p>}
      </div>

      {/* Quality feedback */}
      {(question.status === "published" || question.status === "closed") && !feedbackSubmitted && (
        <div className="bg-background p-4 rounded-lg border border-border mt-6">
          <h2 className="font-semibold mb-2 text-sm">Rate this question</h2>
          <div className="flex items-center gap-1 mb-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} onClick={() => setFeedbackRating(n)} className={`w-8 h-8 rounded text-sm font-medium ${n <= feedbackRating ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"}`}>{n}</button>
            ))}
          </div>
          <input value={feedbackComment} onChange={(e) => setFeedbackComment(e.target.value)} placeholder="Optional comment" className="w-full border border-border rounded-md px-3 py-1.5 bg-background text-sm mb-2" />
          <button onClick={handleSubmitFeedback} disabled={feedbackRating < 1} className="bg-primary text-primary-foreground px-3 py-1.5 rounded text-sm disabled:opacity-50 active:scale-[0.97] transition-all duration-150">Submit Feedback</button>
        </div>
      )}
    </div>
  );
}
