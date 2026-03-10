import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { ai, ApiError, respondentPool, RespondentPool, RespondentPoolMember, User } from "@/api/client";

const MAX_POOL_SIZE = 5;

export interface RespondentPoolEditorHandle {
  addUser: (user: User) => void;
  hasUser: (userId: string) => boolean;
}

interface RespondentPoolEditorProps {
  questionId: string;
  questionStatus: string;
  initialPool: RespondentPoolMember[];
  initialVersion: number;
  onPoolUpdated: (pool: RespondentPool) => void;
  disabled?: boolean;
}

export const RespondentPoolEditor = forwardRef<RespondentPoolEditorHandle, RespondentPoolEditorProps>(function RespondentPoolEditor({
  questionId,
  questionStatus,
  initialPool,
  initialVersion,
  onPoolUpdated,
  disabled = false,
}: RespondentPoolEditorProps, ref) {
  // Server state
  const [serverPool, setServerPool] = useState<RespondentPoolMember[]>(initialPool);
  const [serverVersion, setServerVersion] = useState(initialVersion);

  // Local draft state
  const [draftUsers, setDraftUsers] = useState<User[]>(() => initialPool.map((m) => m.user));

  // Search state
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<User[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Confirm state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Conflict dialog state
  const [conflict, setConflict] = useState<RespondentPool | null>(null);

  const draftIds = useMemo(() => new Set(draftUsers.map((u) => u.id)), [draftUsers]);
  const serverIds = useMemo(() => new Set(serverPool.map((m) => m.user.id)), [serverPool]);

  useImperativeHandle(ref, () => ({
    addUser: (user: User) => {
      setDraftUsers((prev) => {
        if (prev.length >= MAX_POOL_SIZE || prev.some((u) => u.id === user.id)) return prev;
        return [...prev, user];
      });
      setError("");
    },
    hasUser: (userId: string) => draftIds.has(userId),
  }), [draftIds]);

  // Sync when parent re-renders with new data
  useEffect(() => {
    setServerPool(initialPool);
    setServerVersion(initialVersion);
    setDraftUsers(initialPool.map((m) => m.user));
  }, [initialPool, initialVersion]);

  const hasChanges = useMemo(() => {
    if (draftUsers.length !== serverPool.length) return true;
    for (const u of draftUsers) {
      if (!serverIds.has(u.id)) return true;
    }
    return false;
  }, [draftUsers, serverPool, serverIds]);

  const added = useMemo(() => draftUsers.filter((u) => !serverIds.has(u.id)), [draftUsers, serverIds]);
  const removed = useMemo(() => serverPool.filter((m) => !draftIds.has(m.user.id)), [serverPool, draftIds]);

  // Debounced search
  useEffect(() => {
    if (!searchOpen) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const data = await ai.searchUsers(query, "respondent");
        setResults(data.users);
      } catch {
        setResults([]);
      }
      setSearchLoading(false);
    }, 200);
    return () => clearTimeout(debounceRef.current);
  }, [query, searchOpen]);

  useEffect(() => {
    setHighlightIndex(0);
  }, [results.length, query]);

  useEffect(() => {
    if (!searchOpen || !listRef.current) return;
    const el = listRef.current.children[highlightIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex, searchOpen]);

  // Click outside to close search
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const addUser = (user: User) => {
    if (draftIds.has(user.id) || draftUsers.length >= MAX_POOL_SIZE) return;
    setDraftUsers((prev) => [...prev, user]);
    setQuery("");
    setSearchOpen(false);
    setError("");
  };

  const removeUser = (userId: string) => {
    setDraftUsers((prev) => prev.filter((u) => u.id !== userId));
    setError("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!searchOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        e.preventDefault();
        setSearchOpen(true);
      }
      return;
    }
    const selectableResults = results.filter((u) => !draftIds.has(u.id));
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIndex((i) => Math.min(i + 1, selectableResults.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (selectableResults[highlightIndex]) {
          addUser(selectableResults[highlightIndex]);
        }
        break;
      case "Escape":
        e.preventDefault();
        setSearchOpen(false);
        break;
    }
  };

  const handleConfirm = async () => {
    setSaving(true);
    setError("");
    try {
      const pool = await respondentPool.update(
        questionId,
        draftUsers.map((u) => u.id),
        serverVersion,
      );
      setServerPool(pool.respondents);
      setServerVersion(pool.version);
      setDraftUsers(pool.respondents.map((m) => m.user));
      onPoolUpdated(pool);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 409) {
        // Version conflict - fetch current state
        try {
          const current = await respondentPool.get(questionId);
          setConflict(current);
        } catch {
          setError("Version conflict, but failed to fetch current state.");
        }
      } else {
        setError(e instanceof Error ? e.message : "Failed to update pool");
      }
    }
    setSaving(false);
  };

  const handleConflictReload = () => {
    if (!conflict) return;
    setServerPool(conflict.respondents);
    setServerVersion(conflict.version);
    setDraftUsers(conflict.respondents.map((m) => m.user));
    setConflict(null);
  };

  const handleConflictOverride = async () => {
    if (!conflict) return;
    setConflict(null);
    setServerVersion(conflict.version);
    setSaving(true);
    setError("");
    try {
      const pool = await respondentPool.update(
        questionId,
        draftUsers.map((u) => u.id),
        conflict.version,
      );
      setServerPool(pool.respondents);
      setServerVersion(pool.version);
      setDraftUsers(pool.respondents.map((m) => m.user));
      onPoolUpdated(pool);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Override failed");
    }
    setSaving(false);
  };

  const isDisabled = disabled || questionStatus !== "published";

  return (
    <div>
      <label className="block text-sm font-medium mb-1">Respondent Pool</label>

      {/* Current pool display */}
      <div className="flex items-center gap-1 mb-2">
        <span className="text-xs text-muted-foreground">
          {draftUsers.length}/{MAX_POOL_SIZE} respondents
        </span>
      </div>

      {draftUsers.length === 0 ? (
        <p className="text-xs text-muted-foreground mb-2">No respondents assigned</p>
      ) : (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {draftUsers.map((user) => {
            const isNew = !serverIds.has(user.id);
            return (
              <span
                key={user.id}
                className={`inline-flex items-center gap-1 px-2 py-0.5 text-sm rounded-full ${
                  isNew
                    ? "bg-primary/10 text-primary border border-primary/30"
                    : "bg-muted text-foreground"
                }`}
              >
                {user.display_name}
                {!isDisabled && (
                  <button
                    type="button"
                    onClick={() => removeUser(user.id)}
                    className="shrink-0 w-4 h-4 flex items-center justify-center rounded-full hover:bg-black/10 text-current transition-colors"
                    aria-label={`Remove ${user.display_name}`}
                  >
                    <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M3 3l6 6M9 3l-6 6" />
                    </svg>
                  </button>
                )}
              </span>
            );
          })}
        </div>
      )}

      {/* Search to add */}
      {!isDisabled && draftUsers.length < MAX_POOL_SIZE && (
        <div ref={containerRef} className="relative mb-2">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSearchOpen(true);
            }}
            onFocus={() => setSearchOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder="Search respondents to add..."
            className="w-full border border-border rounded-md px-3 py-1.5 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          {searchOpen && (
            <div
              ref={listRef}
              className="absolute z-50 mt-1 w-full max-h-[200px] overflow-y-auto border border-border rounded-md bg-background shadow-lg"
              role="listbox"
            >
              {searchLoading ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">Searching...</div>
              ) : results.length === 0 ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">
                  {query.trim() ? "No matches found" : "Type to search"}
                </div>
              ) : (
                results.map((user, i) => {
                  const alreadyAdded = draftIds.has(user.id);
                  return (
                    <div
                      key={user.id}
                      role="option"
                      aria-selected={i === highlightIndex}
                      aria-disabled={alreadyAdded}
                      className={`px-3 py-1.5 transition-colors ${
                        alreadyAdded
                          ? "opacity-50 cursor-default"
                          : `cursor-pointer ${i === highlightIndex ? "bg-muted" : "hover:bg-muted/50"}`
                      }`}
                      onMouseEnter={() => { if (!alreadyAdded) setHighlightIndex(i); }}
                      onClick={() => { if (!alreadyAdded) addUser(user); }}
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
                        {alreadyAdded && (
                          <span className="text-[10px] text-muted-foreground shrink-0">Already added</span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      )}

      {isDisabled && draftUsers.length < MAX_POOL_SIZE && questionStatus !== "published" && (
        <p className="text-xs text-muted-foreground mb-2">Pool editing is only available for published questions.</p>
      )}

      {/* Change summary + confirm */}
      {hasChanges && !isDisabled && (
        <div className="border border-border rounded-md p-2 mb-2">
          <div className="text-xs text-muted-foreground mb-1.5">
            {added.length > 0 && (
              <span>
                Adding: {added.map((u) => u.display_name).join(", ")}
                {removed.length > 0 && ". "}
              </span>
            )}
            {removed.length > 0 && (
              <span>Removing: {removed.map((m) => m.user.display_name).join(", ")}</span>
            )}
          </div>
          <button
            onClick={handleConfirm}
            disabled={saving}
            className="bg-primary text-primary-foreground px-3 py-1 rounded text-sm disabled:opacity-50 active:scale-[0.97] transition-all duration-150"
          >
            {saving ? "Saving..." : "Confirm Changes"}
          </button>
        </div>
      )}

      {error && <p className="text-destructive text-xs mt-1">{error}</p>}

      {/* Conflict dialog */}
      {conflict && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border border-border rounded-lg shadow-xl max-w-md w-full mx-4 p-5">
            <h3 className="font-semibold text-sm mb-3">Pool updated by another admin</h3>
            <p className="text-xs text-muted-foreground mb-3">
              The respondent pool was modified since you started editing. Choose how to proceed:
            </p>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <p className="text-xs font-medium mb-1">Current pool (server)</p>
                {conflict.respondents.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Empty</p>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {conflict.respondents.map((m) => (
                      <span key={m.id} className="inline-block px-1.5 py-0.5 text-[11px] bg-muted rounded-full">
                        {m.user.display_name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <p className="text-xs font-medium mb-1">Your selection</p>
                {draftUsers.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Empty</p>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {draftUsers.map((u) => (
                      <span key={u.id} className="inline-block px-1.5 py-0.5 text-[11px] bg-primary/10 text-primary rounded-full">
                        {u.display_name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleConflictReload}
                className="flex-1 border border-border px-3 py-1.5 rounded text-sm hover:bg-muted active:scale-[0.97] transition-all duration-150"
              >
                Edit my selection
              </button>
              <button
                onClick={handleConflictOverride}
                className="flex-1 bg-primary text-primary-foreground px-3 py-1.5 rounded text-sm active:scale-[0.97] transition-all duration-150"
              >
                Override
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
