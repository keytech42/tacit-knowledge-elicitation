import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { api, ai, Question, Answer, User, TaskStatus, Recommendation } from "@/api/client";
import { Admonition } from "@/components/Admonition";
import { StatusBadge } from "@/components/StatusBadge";

// ---------------------------------------------------------------------------
// Task status badge (for AI task polling status: accepted/running/completed/failed)
// ---------------------------------------------------------------------------

function TaskStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    accepted: "bg-muted text-muted-foreground",
    running: "bg-muted text-foreground",
    completed: "bg-muted text-foreground border border-border",
    failed: "bg-destructive/10 text-destructive",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[status] || "bg-muted text-muted-foreground"}`}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// EntitySearch<T> — reusable searchable dropdown picker
// ---------------------------------------------------------------------------

interface EntitySearchProps<T> {
  items: T[];
  loading: boolean;
  placeholder: string;
  searchFields: (item: T) => string;
  renderItem: (item: T, highlighted: boolean) => React.ReactNode;
  renderSelected: (item: T) => React.ReactNode;
  selected: T | null;
  onSelect: (item: T | null) => void;
  label: string;
}

function EntitySearch<T extends { id: string }>({
  items,
  loading,
  placeholder,
  searchFields,
  renderItem,
  renderSelected,
  selected,
  onSelect,
  label,
}: EntitySearchProps<T>) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const lower = query.toLowerCase();
    return items.filter((item) => searchFields(item).toLowerCase().includes(lower));
  }, [items, query, searchFields]);

  // Reset highlight when filtered list changes
  useEffect(() => {
    setHighlightIndex(0);
  }, [filtered.length, query]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.children[highlightIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex, open]);

  // Click outside closes dropdown
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIndex((i) => Math.min(i + 1, filtered.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (filtered[highlightIndex]) {
          onSelect(filtered[highlightIndex]);
          setOpen(false);
          setQuery("");
        }
        break;
      case "Escape":
        e.preventDefault();
        setOpen(false);
        break;
    }
  };

  if (selected) {
    return (
      <div>
        <label className="block text-sm font-medium mb-1">{label}</label>
        <div className="flex items-center gap-2 border border-primary rounded-md px-3 py-2 bg-background">
          <div className="flex-1 min-w-0">{renderSelected(selected)}</div>
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="shrink-0 w-5 h-5 flex items-center justify-center rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Clear selection"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l6 6M9 3l-6 6" />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <label className="block text-sm font-medium mb-1">{label}</label>
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={loading ? "Loading..." : placeholder}
        disabled={loading}
        className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
      />
      {open && !loading && (
        <div
          ref={listRef}
          className="absolute z-50 mt-1 w-full max-h-[240px] overflow-y-auto border border-border rounded-md bg-background shadow-lg"
          role="listbox"
        >
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">
              {items.length === 0 ? "No items available" : "No matches found"}
            </div>
          ) : (
            filtered.map((item, i) => (
              <div
                key={item.id}
                role="option"
                aria-selected={i === highlightIndex}
                className={`cursor-pointer px-3 py-2 transition-colors ${
                  i === highlightIndex ? "bg-muted" : "hover:bg-muted/50"
                }`}
                onMouseEnter={() => setHighlightIndex(i)}
                onClick={() => {
                  onSelect(item);
                  setOpen(false);
                  setQuery("");
                }}
              >
                {renderItem(item, i === highlightIndex)}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// UserSearch — multi-select user search with chips
// ---------------------------------------------------------------------------

interface UserSearchProps {
  users: User[];
  loading: boolean;
  selected: User[];
  onChange: (users: User[]) => void;
  error: string | null;
}

function UserSearch({ users, loading, selected, onChange, error }: UserSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const selectedIds = useMemo(() => new Set(selected.map((u) => u.id)), [selected]);

  const humanUsers = useMemo(
    () => users.filter((u) => u.user_type === "human"),
    [users]
  );

  const filtered = useMemo(() => {
    const available = humanUsers.filter((u) => !selectedIds.has(u.id));
    if (!query.trim()) return available;
    const lower = query.toLowerCase();
    return available.filter(
      (u) =>
        u.display_name.toLowerCase().includes(lower) ||
        (u.email && u.email.toLowerCase().includes(lower))
    );
  }, [humanUsers, selectedIds, query]);

  useEffect(() => {
    setHighlightIndex(0);
  }, [filtered.length, query]);

  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.children[highlightIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex, open]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIndex((i) => Math.min(i + 1, filtered.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (filtered[highlightIndex]) {
          onChange([...selected, filtered[highlightIndex]]);
          setQuery("");
        }
        break;
      case "Escape":
        e.preventDefault();
        setOpen(false);
        break;
      case "Backspace":
        if (query === "" && selected.length > 0) {
          onChange(selected.slice(0, -1));
        }
        break;
    }
  };

  const removeUser = (userId: string) => {
    onChange(selected.filter((u) => u.id !== userId));
  };

  return (
    <div ref={containerRef} className="relative">
      <label className="block text-sm font-medium mb-1">Or manually select respondents</label>

      {/* Selected chips */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selected.map((user) => (
            <span
              key={user.id}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-muted text-sm text-foreground"
            >
              <span className="truncate max-w-[160px]">{user.display_name}</span>
              <button
                type="button"
                onClick={() => removeUser(user.id)}
                className="shrink-0 w-4 h-4 flex items-center justify-center rounded-full hover:bg-border text-muted-foreground hover:text-foreground transition-colors"
                aria-label={`Remove ${user.display_name}`}
              >
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M3 3l6 6M9 3l-6 6" />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}

      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={loading ? "Loading users..." : "Search by name or email..."}
        disabled={loading || !!error}
        className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
      />

      {error && (
        <p className="mt-1 text-xs text-destructive">{error}</p>
      )}

      {open && !loading && !error && (
        <div
          ref={listRef}
          className="absolute z-50 mt-1 w-full max-h-[240px] overflow-y-auto border border-border rounded-md bg-background shadow-lg"
          role="listbox"
        >
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">
              {humanUsers.length === 0 ? "No users available" : "No matches found"}
            </div>
          ) : (
            filtered.map((user, i) => (
              <div
                key={user.id}
                role="option"
                aria-selected={i === highlightIndex}
                className={`cursor-pointer px-3 py-2 transition-colors ${
                  i === highlightIndex ? "bg-muted" : "hover:bg-muted/50"
                }`}
                onMouseEnter={() => setHighlightIndex(i)}
                onClick={() => {
                  onChange([...selected, user]);
                  setQuery("");
                  inputRef.current?.focus();
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground truncate">
                      {user.display_name}
                    </div>
                    {user.email && (
                      <div className="text-xs text-muted-foreground truncate">{user.email}</div>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {user.roles.map((r) => (
                      <span
                        key={r.id}
                        className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-medium"
                      >
                        {r.name}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Render helpers for entity search items
// ---------------------------------------------------------------------------

function QuestionItem({ question }: { question: Question }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-foreground truncate">{question.title}</div>
        <div className="text-xs text-muted-foreground truncate">
          by {question.created_by.display_name}
          {question.category && <span> &middot; {question.category}</span>}
        </div>
      </div>
      <div className="shrink-0">
        <StatusBadge status={question.status} />
      </div>
    </div>
  );
}

function QuestionSelected({ question }: { question: Question }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm font-medium text-foreground truncate">{question.title}</span>
      <StatusBadge status={question.status} />
    </div>
  );
}

function AnswerItem({ answer }: { answer: Answer }) {
  const bodyPreview = answer.body.length > 80 ? answer.body.slice(0, 80) + "..." : answer.body;
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0 flex-1">
        <div className="text-sm text-foreground truncate">{bodyPreview}</div>
        <div className="text-xs text-muted-foreground">
          by {answer.author.display_name} &middot; v{answer.current_version}
        </div>
      </div>
      <div className="shrink-0">
        <StatusBadge status={answer.status} />
      </div>
    </div>
  );
}

function AnswerSelected({ answer }: { answer: Answer }) {
  const bodyPreview = answer.body.length > 60 ? answer.body.slice(0, 60) + "..." : answer.body;
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-foreground truncate">{bodyPreview}</span>
      <StatusBadge status={answer.status} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Combined respondent entry type for unified list
// ---------------------------------------------------------------------------

interface CombinedRespondent {
  user_id: string;
  display_name: string;
  email?: string | null;
  aiRecommended: boolean;
  manuallySelected: boolean;
  score?: number;
  reasoning?: string;
}

function buildCombinedList(
  recommendations: Recommendation[],
  manualSelections: User[]
): CombinedRespondent[] {
  const map = new Map<string, CombinedRespondent>();

  // Add AI recommendations first
  for (const rec of recommendations) {
    map.set(rec.user_id, {
      user_id: rec.user_id,
      display_name: rec.display_name,
      aiRecommended: true,
      manuallySelected: false,
      score: rec.score,
      reasoning: rec.reasoning,
    });
  }

  // Merge in manual selections
  for (const user of manualSelections) {
    const existing = map.get(user.id);
    if (existing) {
      existing.manuallySelected = true;
      existing.email = user.email;
    } else {
      map.set(user.id, {
        user_id: user.id,
        display_name: user.display_name,
        email: user.email,
        aiRecommended: false,
        manuallySelected: true,
      });
    }
  }

  return Array.from(map.values());
}

// ---------------------------------------------------------------------------
// Main AIControls page
// ---------------------------------------------------------------------------

export function AIControls() {
  // ---- Shared data (questions, users) ----
  const [questions, setQuestions] = useState<Question[]>([]);
  const [questionsLoading, setQuestionsLoading] = useState(true);
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<{ questions: Question[]; total: number }>("/questions");
        if (!cancelled) setQuestions(data.questions);
      } catch {
        // silently fail — empty list
      } finally {
        if (!cancelled) setQuestionsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<{ users: User[]; total: number }>("/users");
        if (!cancelled) setUsers(data.users);
      } catch (e: unknown) {
        if (!cancelled) {
          setUsersError(
            e instanceof Error ? e.message : "Failed to load users"
          );
        }
      } finally {
        if (!cancelled) setUsersLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const publishedQuestions = useMemo(
    () => questions.filter((q) => q.status === "published"),
    [questions]
  );

  // ---- Question generation state ----
  const [topic, setTopic] = useState("");
  const [domain, setDomain] = useState("");
  const [count, setCount] = useState(3);
  const [genContext, setGenContext] = useState("");
  const [genTask, setGenTask] = useState<TaskStatus | null>(null);
  const [genLoading, setGenLoading] = useState(false);

  // ---- Scaffold options state ----
  const [scaffoldQuestion, setScaffoldQuestion] = useState<Question | null>(null);
  const [scaffoldTask, setScaffoldTask] = useState<TaskStatus | null>(null);
  const [scaffoldLoading, setScaffoldLoading] = useState(false);

  // ---- Review assist state ----
  const [reviewQuestion, setReviewQuestion] = useState<Question | null>(null);
  const [reviewAnswer, setReviewAnswer] = useState<Answer | null>(null);
  const [reviewAnswers, setReviewAnswers] = useState<Answer[]>([]);
  const [reviewAnswersLoading, setReviewAnswersLoading] = useState(false);
  const [reviewTask, setReviewTask] = useState<TaskStatus | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);

  // Load answers when a question is selected for review
  useEffect(() => {
    if (!reviewQuestion) {
      setReviewAnswers([]);
      setReviewAnswer(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setReviewAnswersLoading(true);
      try {
        const data = await api.get<{ answers: Answer[]; total: number }>(
          `/questions/${reviewQuestion.id}/answers`
        );
        if (!cancelled) setReviewAnswers(data.answers);
      } catch {
        if (!cancelled) setReviewAnswers([]);
      } finally {
        if (!cancelled) setReviewAnswersLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [reviewQuestion]);

  // ---- Recommendation state ----
  const [recQuestion, setRecQuestion] = useState<Question | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recReason, setRecReason] = useState<string | null>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [selectedRespondents, setSelectedRespondents] = useState<User[]>([]);

  // ---- Combined respondent list ----
  const combinedRespondents = useMemo(
    () => buildCombinedList(recommendations, selectedRespondents),
    [recommendations, selectedRespondents]
  );

  // ---- Task polling ----
  const pollTask = useCallback(
    async (taskId: string, setter: (t: TaskStatus) => void) => {
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
    },
    []
  );

  // ---- Handlers ----
  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setGenLoading(true);
    try {
      const result = await ai.generateQuestions(topic, domain, count, genContext || undefined);
      setGenTask({ task_id: result.task_id, status: result.status });
      pollTask(result.task_id, setGenTask);
    } catch (e: unknown) {
      setGenTask({
        task_id: "",
        status: "failed",
        error: e instanceof Error ? e.message : "Unknown error",
      });
    }
    setGenLoading(false);
  };

  const handleScaffold = async () => {
    if (!scaffoldQuestion) return;
    setScaffoldLoading(true);
    try {
      const result = await ai.scaffoldOptions(scaffoldQuestion.id);
      setScaffoldTask({ task_id: result.task_id, status: result.status });
      pollTask(result.task_id, setScaffoldTask);
    } catch (e: unknown) {
      setScaffoldTask({
        task_id: "",
        status: "failed",
        error: e instanceof Error ? e.message : "Unknown error",
      });
    }
    setScaffoldLoading(false);
  };

  const handleReviewAssist = async () => {
    if (!reviewAnswer) return;
    setReviewLoading(true);
    try {
      const result = await ai.reviewAssist(reviewAnswer.id);
      setReviewTask({ task_id: result.task_id, status: result.status });
      pollTask(result.task_id, setReviewTask);
    } catch (e: unknown) {
      setReviewTask({
        task_id: "",
        status: "failed",
        error: e instanceof Error ? e.message : "Unknown error",
      });
    }
    setReviewLoading(false);
  };

  const handleRecommend = async () => {
    if (!recQuestion) return;
    setRecLoading(true);
    setRecReason(null);
    try {
      const resp = await ai.recommend(recQuestion.id);
      setRecommendations(resp.items);
      setRecReason(resp.reason);
    } catch (e: unknown) {
      setRecommendations([]);
      setRecReason(e instanceof Error ? e.message : "Failed to get recommendations.");
    }
    setRecLoading(false);
  };

  // ---- Search field extractors (stable references) ----
  const questionSearchFields = useCallback(
    (q: Question) => `${q.title} ${q.category || ""} ${q.created_by.display_name}`,
    []
  );
  const answerSearchFields = useCallback(
    (a: Answer) => `${a.body} ${a.author.display_name} ${a.status}`,
    []
  );

  // ---- Render helpers for EntitySearch (stable references) ----
  const renderQuestionItem = useCallback(
    (q: Question) => <QuestionItem question={q} />,
    []
  );
  const renderQuestionSelected = useCallback(
    (q: Question) => <QuestionSelected question={q} />,
    []
  );
  const renderAnswerItem = useCallback(
    (a: Answer) => <AnswerItem answer={a} />,
    []
  );
  const renderAnswerSelected = useCallback(
    (a: Answer) => <AnswerSelected answer={a} />,
    []
  );

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-foreground">AI Controls</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Trigger AI tasks and view recommendations
        </p>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Question Generation */}
      {/* ---------------------------------------------------------------- */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-1">Generate Questions</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Use AI to generate elicitation questions for a given topic.
        </p>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium mb-1">Topic *</label>
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. engineering trade-offs"
              className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Domain</label>
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="e.g. software architecture"
              className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Count</label>
            <input
              type="number"
              min={1}
              max={10}
              value={count}
              onChange={(e) => setCount(parseInt(e.target.value) || 3)}
              className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Additional Context</label>
            <input
              value={genContext}
              onChange={(e) => setGenContext(e.target.value)}
              placeholder="Optional context..."
              className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>
        <button
          onClick={handleGenerate}
          disabled={genLoading || !topic.trim()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50 transition-opacity"
        >
          {genLoading ? "Submitting..." : "Generate Questions"}
        </button>
        {genTask && (
          <div className="mt-3 p-3 bg-muted rounded-md text-sm">
            <div className="flex items-center gap-2">
              <TaskStatusBadge status={genTask.status} />
              {genTask.task_id && (
                <span className="text-muted-foreground text-xs font-mono">
                  {genTask.task_id.slice(0, 8)}
                </span>
              )}
            </div>
            {genTask.error && <p className="text-destructive mt-1">{genTask.error}</p>}
            {genTask.result && (
              <p className="mt-1 text-muted-foreground">
                Created {String((genTask.result as Record<string, unknown>).count)} questions
              </p>
            )}
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Scaffold Answer Options */}
      {/* ---------------------------------------------------------------- */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-1">Scaffold Answer Options</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Generate suggested answer options for a published question.
        </p>
        <div className="mb-4">
          <EntitySearch<Question>
            items={publishedQuestions}
            loading={questionsLoading}
            placeholder="Search published questions..."
            searchFields={questionSearchFields}
            renderItem={renderQuestionItem}
            renderSelected={renderQuestionSelected}
            selected={scaffoldQuestion}
            onSelect={setScaffoldQuestion}
            label="Question *"
          />
        </div>
        <button
          onClick={handleScaffold}
          disabled={scaffoldLoading || !scaffoldQuestion}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50 transition-opacity"
        >
          {scaffoldLoading ? "Submitting..." : "Generate Options"}
        </button>
        {scaffoldTask && (
          <div className="mt-3 p-3 bg-muted rounded-md text-sm">
            <div className="flex items-center gap-2">
              <TaskStatusBadge status={scaffoldTask.status} />
              {scaffoldTask.task_id && (
                <span className="text-muted-foreground text-xs font-mono">
                  {scaffoldTask.task_id.slice(0, 8)}
                </span>
              )}
            </div>
            {scaffoldTask.error && <p className="text-destructive mt-1">{scaffoldTask.error}</p>}
            {scaffoldTask.result && (
              <p className="mt-1 text-muted-foreground">Options created</p>
            )}
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Review Assist */}
      {/* ---------------------------------------------------------------- */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-1">AI Review Assist</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Run an AI-assisted preliminary review on an answer.
        </p>
        <div className="space-y-4 mb-4">
          {/* Step 1: Pick a question */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Step 1
              </span>
            </div>
            <EntitySearch<Question>
              items={publishedQuestions}
              loading={questionsLoading}
              placeholder="Search published questions..."
              searchFields={questionSearchFields}
              renderItem={renderQuestionItem}
              renderSelected={renderQuestionSelected}
              selected={reviewQuestion}
              onSelect={(q) => {
                setReviewQuestion(q);
                setReviewAnswer(null);
              }}
              label="Select a question"
            />
          </div>

          {/* Step 2: Pick an answer from that question */}
          {reviewQuestion && (
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Step 2
                </span>
              </div>
              <EntitySearch<Answer>
                items={reviewAnswers}
                loading={reviewAnswersLoading}
                placeholder="Search answers for this question..."
                searchFields={answerSearchFields}
                renderItem={renderAnswerItem}
                renderSelected={renderAnswerSelected}
                selected={reviewAnswer}
                onSelect={setReviewAnswer}
                label="Select an answer"
              />
            </div>
          )}
        </div>
        <button
          onClick={handleReviewAssist}
          disabled={reviewLoading || !reviewAnswer}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50 transition-opacity"
        >
          {reviewLoading ? "Submitting..." : "Run AI Review"}
        </button>
        {reviewTask && (
          <div className="mt-3 p-3 bg-muted rounded-md text-sm">
            <div className="flex items-center gap-2">
              <TaskStatusBadge status={reviewTask.status} />
              {reviewTask.task_id && (
                <span className="text-muted-foreground text-xs font-mono">
                  {reviewTask.task_id.slice(0, 8)}
                </span>
              )}
            </div>
            {reviewTask.error && <p className="text-destructive mt-1">{reviewTask.error}</p>}
            {reviewTask.result && (
              <div className="mt-2 grid grid-cols-3 gap-3">
                <div className="p-2 bg-background rounded border border-border">
                  <div className="text-xs text-muted-foreground">Verdict</div>
                  <div className="text-sm font-medium">
                    {String((reviewTask.result as Record<string, unknown>).verdict)}
                  </div>
                </div>
                <div className="p-2 bg-background rounded border border-border">
                  <div className="text-xs text-muted-foreground">Confidence</div>
                  <div className="text-sm font-medium">
                    {(
                      Number((reviewTask.result as Record<string, unknown>).confidence) * 100
                    ).toFixed(0)}
                    %
                  </div>
                </div>
                <div className="p-2 bg-background rounded border border-border">
                  <div className="text-xs text-muted-foreground">Submitted</div>
                  <div className="text-sm font-medium">
                    {String((reviewTask.result as Record<string, unknown>).submitted)}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Respondent Recommendations */}
      {/* ---------------------------------------------------------------- */}
      <section className="bg-background border border-border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-1">Respondent Recommendations</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Find the best respondents for a published question using AI embeddings,
          or manually select users. Combine both to build a notification list.
        </p>
        <div className="space-y-4 mb-4">
          <EntitySearch<Question>
            items={publishedQuestions}
            loading={questionsLoading}
            placeholder="Search published questions..."
            searchFields={questionSearchFields}
            renderItem={renderQuestionItem}
            renderSelected={renderQuestionSelected}
            selected={recQuestion}
            onSelect={setRecQuestion}
            label="Question *"
          />

          <button
            onClick={handleRecommend}
            disabled={recLoading || !recQuestion}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium disabled:opacity-50 transition-opacity"
          >
            {recLoading ? "Loading..." : "Get Recommendations"}
          </button>

          {recReason && recommendations.length === 0 && (
            <Admonition variant="warning" title="No recommendations available">
              {recReason}
            </Admonition>
          )}

          {recommendations.length > 0 && (
            <Admonition variant="success">
              {recommendations.length} respondent{recommendations.length !== 1 ? "s" : ""} recommended
            </Admonition>
          )}

          <div className="border-t border-border pt-4">
            <UserSearch
              users={users}
              loading={usersLoading}
              selected={selectedRespondents}
              onChange={setSelectedRespondents}
              error={usersError}
            />
          </div>
        </div>

        {/* Combined respondent list */}
        {combinedRespondents.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-foreground">
                Selected Respondents ({combinedRespondents.length})
              </h3>
              <div className="relative group">
                <button
                  disabled
                  className="px-3 py-1.5 bg-muted text-muted-foreground rounded-md text-sm font-medium cursor-not-allowed opacity-60"
                >
                  Notify Selected
                </button>
                <div className="absolute bottom-full right-0 mb-2 px-3 py-1.5 bg-foreground text-background text-xs rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                  Slack integration coming soon
                </div>
              </div>
            </div>
            <div className="border border-border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium text-foreground">Respondent</th>
                    <th className="text-left px-3 py-2 font-medium text-foreground">Source</th>
                    <th className="text-left px-3 py-2 font-medium text-foreground">Score</th>
                    <th className="text-left px-3 py-2 font-medium text-foreground">Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {combinedRespondents.map((r) => (
                    <tr key={r.user_id} className="border-t border-border">
                      <td className="px-3 py-2">
                        <div className="text-foreground">{r.display_name}</div>
                        {r.email && (
                          <div className="text-xs text-muted-foreground">{r.email}</div>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {r.aiRecommended && (
                            <span className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded-full bg-accent text-accent-foreground font-medium border border-border">
                              AI recommended
                            </span>
                          )}
                          {r.manuallySelected && (
                            <span className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded-full bg-secondary text-secondary-foreground font-medium border border-border">
                              Manual
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-foreground">
                        {r.score != null ? `${(r.score * 100).toFixed(0)}%` : "\u2014"}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {r.reasoning || "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
