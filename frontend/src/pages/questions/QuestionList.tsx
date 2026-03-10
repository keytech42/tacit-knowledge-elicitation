import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Question } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { StatusBadge, statusLabel, statusColor, WORKFLOW_HINTS } from "@/components/StatusBadge";
import { STATUS_COLOR_TOKEN, badgeColor, borderColor, hoverBorderColor } from "@/components/statusColors";
import { Tooltip } from "@/components/Tooltip";
import { timeAgo, exactDateTime } from "@/utils/timeAgo";

/** Extract up to 2 initials from a display name. */
function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

/** Statuses visible to all users */
const PRIMARY_STATUSES = ["published", "closed", "archived"];
/** Authoring pipeline statuses visible only to admin/author */
const AUTHORING_STATUSES = ["draft", "proposed", "in_review"];

type ViewMode = "list" | "kanban";

function KanbanCard({ q, hoverBorder }: { q: Question; hoverBorder: string }) {
  return (
    <Link
      to={`/questions/${q.id}`}
      className={`block bg-background p-3 rounded-lg border border-border ${hoverBorder} hover:shadow-md hover:-translate-y-[2px] transition-all duration-200 shadow-sm`}
    >
      <h4 className="font-medium text-sm leading-snug">{q.title}</h4>
      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{q.body}</p>
      <div className="flex items-center gap-2 mt-2">
        {q.category && <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{q.category}</span>}
        {q.quality_score != null && <span className="text-[10px] text-muted-foreground">{q.quality_score.toFixed(1)}</span>}
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-[10px] text-muted-foreground">{q.created_by.display_name}</span>
        <Tooltip text={exactDateTime(q.created_at)}>
          <span className="text-[10px] text-muted-foreground">{timeAgo(q.created_at)}</span>
        </Tooltip>
      </div>
    </Link>
  );
}

function ColumnHeader({ status, count }: { status: string; count: number }) {
  const hint = WORKFLOW_HINTS[`q:${status}`];
  const token = STATUS_COLOR_TOKEN[status];
  const countClasses = token
    ? `${badgeColor(token)} rounded-full px-1.5 text-[10px] font-medium`
    : "text-xs text-muted-foreground";
  return (
    <div className="flex items-center gap-2 mb-3 px-1">
      {hint ? (
        <Tooltip text={hint}>
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(status)}`}>
            {statusLabel(status)}
          </span>
        </Tooltip>
      ) : (
        <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(status)}`}>
          {statusLabel(status)}
        </span>
      )}
      <span className={countClasses}>{count}</span>
    </div>
  );
}

function KanbanColumn({ status, questions }: { status: string; questions: Question[] }) {
  const token = STATUS_COLOR_TOKEN[status];
  const border = token ? borderColor(token) : "border-border";
  const hoverBorder = token ? hoverBorderColor(token) : "hover:border-primary/30";
  return (
    <div className="flex-shrink-0 w-64">
      <ColumnHeader status={status} count={questions.length} />
      <div className={`space-y-2 p-2 rounded-lg bg-muted/50 border ${border} min-h-[200px]`}>
        {questions.map((q) => <KanbanCard key={q.id} q={q} hoverBorder={hoverBorder} />)}
        {questions.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 border-dashed border-2 border-border/50 rounded-lg">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground/40 mb-2">
              <path d="M9 2h6l3 3v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5l3-3z" />
              <path d="M9 2v3H6" />
              <path d="M15 2v3h3" />
              <line x1="9" y1="12" x2="15" y2="12" />
              <line x1="9" y1="16" x2="13" y2="16" />
            </svg>
            <span className="text-xs text-muted-foreground/60">No items</span>
          </div>
        )}
      </div>
    </div>
  );
}

function KanbanBoard({ questions, showAuthoring }: { questions: Question[]; showAuthoring: boolean }) {
  const allStatuses = showAuthoring ? [...PRIMARY_STATUSES, ...AUTHORING_STATUSES] : PRIMARY_STATUSES;
  const grouped = allStatuses.reduce<Record<string, Question[]>>((acc, status) => {
    acc[status] = questions.filter((q) => q.status === status);
    return acc;
  }, {});

  return (
    <div style={{ minHeight: "calc(100vh - 220px)" }}>
      {/* Primary row: published, closed, archived */}
      <div className="flex gap-4 overflow-x-auto pb-4">
        {PRIMARY_STATUSES.map((status) => (
          <KanbanColumn key={status} status={status} questions={grouped[status]} />
        ))}
      </div>

      {/* Authoring pipeline row: draft, proposed, in_review (admin/author only) */}
      {showAuthoring && (
        <div className="mt-6">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Authoring Pipeline</h3>
          <div className="flex gap-4 overflow-x-auto pb-4">
            {AUTHORING_STATUSES.map((status) => (
              <KanbanColumn key={status} status={status} questions={grouped[status]} />
            ))}
          </div>
        </div>
      )}
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

  const isAuthorOrAdmin = hasRole("author") || hasRole("admin");

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
          {isAuthorOrAdmin && (
            <Link to="/questions/new" className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium">New Question</Link>
          )}
        </div>
        <div className="flex items-center gap-3">
          {viewMode === "list" && (
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="border border-border rounded-md px-3 py-2 text-sm bg-background">
              <option value="">All statuses</option>
              <option value="published">Published</option>
              <option value="closed">Closed</option>
              <option value="archived">Archived</option>
              {isAuthorOrAdmin && <option value="draft">Draft</option>}
              {isAuthorOrAdmin && <option value="proposed">Proposed</option>}
              {isAuthorOrAdmin && <option value="in_review">In Review</option>}
            </select>
          )}
          <div className="flex border border-border rounded-md overflow-hidden">
            <button onClick={() => handleViewChange("list")} className={`px-3 py-2 text-sm ${viewMode === "list" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>List</button>
            <button onClick={() => handleViewChange("kanban")} className={`px-3 py-2 text-sm ${viewMode === "kanban" ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:bg-muted"}`}>Board</button>
          </div>
        </div>
      </div>

      {viewMode === "kanban" ? (
        <KanbanBoard questions={questions} showAuthoring={isAuthorOrAdmin} />
      ) : (
        <div className="space-y-3">
          {questions.map((q) => {
            const token = STATUS_COLOR_TOKEN[q.status];
            const hoverBorder = token ? hoverBorderColor(token) : "hover:border-primary/30";
            return (
            <Link key={q.id} to={`/questions/${q.id}`} className={`block bg-background p-4 rounded-lg border border-border ${hoverBorder} hover:shadow-sm hover:-translate-y-[1px] transition-all duration-200`}>
              <div className="flex items-center gap-3 mb-2">
                <StatusBadge status={q.status} />
                {q.category && <span className="text-xs text-muted-foreground">{q.category}</span>}
                {q.quality_score && <span className="text-xs text-muted-foreground">Score: {q.quality_score.toFixed(1)}</span>}
              </div>
              <h3 className="font-semibold">{q.title}</h3>
              <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{q.body}</p>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-2">
                <span className="w-5 h-5 bg-primary/10 text-primary text-[10px] font-semibold rounded-full flex items-center justify-center">{getInitials(q.created_by.display_name)}</span>
                <span>by {q.created_by.display_name}</span>
                <span>&middot;</span>
                <Tooltip text={exactDateTime(q.created_at)}>
                  <span>{timeAgo(q.created_at)}</span>
                </Tooltip>
              </div>
            </Link>
            );
          })}
          {questions.length === 0 && <p className="text-center text-muted-foreground py-8">No questions found.</p>}
        </div>
      )}
    </div>
  );
}
