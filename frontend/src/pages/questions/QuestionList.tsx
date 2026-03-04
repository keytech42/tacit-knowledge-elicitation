import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Question } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-200 text-gray-700",
  proposed: "bg-yellow-100 text-yellow-800",
  in_review: "bg-blue-100 text-blue-800",
  published: "bg-green-100 text-green-800",
  closed: "bg-red-100 text-red-800",
  archived: "bg-gray-100 text-gray-500",
};

const STATUS_BORDER_COLORS: Record<string, string> = {
  draft: "border-gray-300",
  proposed: "border-yellow-300",
  in_review: "border-blue-300",
  published: "border-green-300",
  closed: "border-red-300",
  archived: "border-gray-200",
};

const ALL_STATUSES = ["draft", "proposed", "in_review", "published", "closed", "archived"];

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  proposed: "Proposed",
  in_review: "In Review",
  published: "Published",
  closed: "Closed",
  archived: "Archived",
};

type ViewMode = "list" | "kanban";

function KanbanCard({ q }: { q: Question }) {
  return (
    <Link
      to={`/questions/${q.id}`}
      className="block bg-background p-3 rounded-lg border border-border hover:border-primary/30 transition-colors shadow-sm"
    >
      <h4 className="font-medium text-sm leading-snug">{q.title}</h4>
      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{q.body}</p>
      <div className="flex items-center gap-2 mt-2">
        {q.category && <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{q.category}</span>}
        {q.quality_score != null && <span className="text-[10px] text-muted-foreground">{q.quality_score.toFixed(1)}</span>}
      </div>
      <div className="text-[10px] text-muted-foreground mt-1.5">
        {q.created_by.display_name}
      </div>
    </Link>
  );
}

function KanbanBoard({ questions }: { questions: Question[] }) {
  const grouped = ALL_STATUSES.reduce<Record<string, Question[]>>((acc, status) => {
    acc[status] = questions.filter((q) => q.status === status);
    return acc;
  }, {});

  return (
    <div className="flex gap-4 overflow-x-auto pb-4" style={{ minHeight: "calc(100vh - 220px)" }}>
      {ALL_STATUSES.map((status) => (
        <div key={status} className="flex-shrink-0 w-64">
          <div className={`flex items-center gap-2 mb-3 px-1`}>
            <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLORS[status]}`}>
              {STATUS_LABELS[status]}
            </span>
            <span className="text-xs text-muted-foreground">{grouped[status].length}</span>
          </div>
          <div className={`space-y-2 p-2 rounded-lg bg-muted/50 border ${STATUS_BORDER_COLORS[status]} min-h-[200px]`}>
            {grouped[status].map((q) => (
              <KanbanCard key={q.id} q={q} />
            ))}
            {grouped[status].length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">No items</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function QuestionList() {
  const { hasRole } = useAuth();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    return (localStorage.getItem("questionListView") as ViewMode) || "list";
  });

  useEffect(() => {
    const params = viewMode === "list" && statusFilter ? `?status=${statusFilter}` : "";
    api.get<{ questions: Question[]; total: number }>(`/questions${params}`).then((data) => {
      setQuestions(data.questions);
      setTotal(data.total);
    });
  }, [statusFilter, viewMode]);

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem("questionListView", mode);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">Questions ({total})</h1>
          {(hasRole("author") || hasRole("admin")) && (
            <Link to="/questions/new" className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium">New Question</Link>
          )}
        </div>
        <div className="flex items-center gap-3">
          {viewMode === "list" && (
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
          )}
          <div className="flex border border-border rounded-md overflow-hidden">
            <button
              onClick={() => handleViewChange("list")}
              className={`px-3 py-2 text-sm ${viewMode === "list" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}
            >
              List
            </button>
            <button
              onClick={() => handleViewChange("kanban")}
              className={`px-3 py-2 text-sm ${viewMode === "kanban" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}
            >
              Board
            </button>
          </div>
        </div>
      </div>

      {viewMode === "kanban" ? (
        <KanbanBoard questions={questions} />
      ) : (
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
      )}
    </div>
  );
}
