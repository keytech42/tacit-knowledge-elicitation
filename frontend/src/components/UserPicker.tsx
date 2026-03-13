import { useEffect, useMemo, useRef, useState } from "react";
import { ai, User } from "@/api/client";

interface UserPickerProps {
  /** Optional role filter (e.g. "reviewer", "respondent") */
  role?: string;
  /** Currently selected user */
  selected: User | null;
  /** Called when user picks or clears selection */
  onSelect: (user: User | null) => void;
  /** Label above the picker */
  label?: string;
  /** Placeholder text */
  placeholder?: string;
  /** Disable the picker */
  disabled?: boolean;
  /** Exclude these user IDs from results */
  excludeIds?: string[];
  /** Show this user at the top of results with a "(you)" tag */
  prioritizeUser?: User | null;
}

export function UserPicker({
  role,
  selected,
  onSelect,
  label,
  placeholder = "Search by name or email...",
  disabled = false,
  excludeIds = [],
  prioritizeUser,
}: UserPickerProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const excludeSet = useMemo(() => new Set(excludeIds), [excludeIds]);

  const filtered = useMemo(() => {
    const base = results.filter((u) => !excludeSet.has(u.id));
    if (!prioritizeUser || excludeSet.has(prioritizeUser.id)) return base;
    // When searching, only promote prioritized user if they appear in results
    if (query.trim() && !base.some((u) => u.id === prioritizeUser.id)) return base;
    const withoutPriority = base.filter((u) => u.id !== prioritizeUser.id);
    return [prioritizeUser, ...withoutPriority];
  }, [results, excludeSet, prioritizeUser, query]);

  // Debounced search
  useEffect(() => {
    if (!open) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await ai.searchUsers(query, role);
        setResults(data.users);
      } catch {
        setResults([]);
      }
      setLoading(false);
    }, 200);
    return () => clearTimeout(debounceRef.current);
  }, [query, role, open]);

  useEffect(() => {
    setHighlightIndex(0);
  }, [filtered.length, query]);

  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.children[highlightIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex, open]);

  // Click outside
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
        {label && <label className="block text-sm font-medium mb-1">{label}</label>}
        <div className="flex items-center gap-2 border border-primary rounded-md px-3 py-2 bg-background">
          <div className="flex-1 min-w-0 flex items-center gap-2">
            <span className="text-sm font-medium truncate">{selected.display_name}</span>
            {selected.email && (
              <span className="text-xs text-muted-foreground truncate">{selected.email}</span>
            )}
          </div>
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
      {label && <label className="block text-sm font-medium mb-1">{label}</label>}
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
        placeholder={placeholder}
        disabled={disabled}
        className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
      />
      {open && (
        <div
          ref={listRef}
          className="absolute z-50 mt-1 w-full max-h-[240px] overflow-y-auto border border-border rounded-md bg-background shadow-lg"
          role="listbox"
        >
          {loading ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">Searching...</div>
          ) : filtered.length === 0 ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">
              {query.trim() ? "No matches found" : "Type to search"}
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
                  onSelect(user);
                  setOpen(false);
                  setQuery("");
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground truncate">
                      {user.display_name}
                      {prioritizeUser && user.id === prioritizeUser.id && (
                        <span className="text-xs text-muted-foreground ml-1.5">(you)</span>
                      )}
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
