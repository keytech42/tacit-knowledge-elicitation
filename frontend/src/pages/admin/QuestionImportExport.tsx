import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, questionTransfer } from "@/api/client";
import { useToast } from "@/components/ToastContext";

const QUESTION_STATUSES = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "proposed", label: "Proposed" },
  { value: "in_review", label: "In Review" },
  { value: "published", label: "Published" },
  { value: "closed", label: "Closed" },
  { value: "archived", label: "Archived" },
];

interface ImportPreviewRow {
  title: string;
  category: string | null;
  optionCount: number;
  errors: string[];
}

function parseAndValidate(raw: unknown): { rows: ImportPreviewRow[]; payload: { version: string; questions: unknown[] } | null; globalError: string | null } {
  if (!raw || typeof raw !== "object") {
    return { rows: [], payload: null, globalError: "Invalid JSON: expected an object" };
  }

  const obj = raw as Record<string, unknown>;

  if (obj.version && obj.version !== "1.0") {
    return { rows: [], payload: null, globalError: `Unsupported schema version "${obj.version}". Expected "1.0"` };
  }

  const questions = obj.questions;
  if (!Array.isArray(questions) || questions.length === 0) {
    return { rows: [], payload: null, globalError: "No questions found in file" };
  }

  if (questions.length > 500) {
    return { rows: [], payload: null, globalError: `Too many questions (${questions.length}). Maximum is 500` };
  }

  const rows: ImportPreviewRow[] = [];
  for (const q of questions) {
    const errors: string[] = [];
    if (!q || typeof q !== "object") {
      rows.push({ title: "(invalid)", category: null, optionCount: 0, errors: ["Not an object"] });
      continue;
    }

    const item = q as Record<string, unknown>;
    const title = typeof item.title === "string" ? item.title : "";
    const body = typeof item.body === "string" ? item.body : "";
    const category = typeof item.category === "string" ? item.category : null;
    const options = Array.isArray(item.answer_options) ? item.answer_options : [];

    if (!title.trim()) errors.push("Missing title");
    if (title.length > 500) errors.push("Title too long (max 500)");
    if (!body.trim()) errors.push("Missing body");
    if (category && category.length > 255) errors.push("Category too long (max 255)");

    rows.push({
      title: title || "(no title)",
      category,
      optionCount: options.length,
      errors,
    });
  }

  const hasErrors = rows.some((r) => r.errors.length > 0);
  const payload = hasErrors
    ? null
    : { version: (obj.version as string) || "1.0", questions };

  return { rows, payload, globalError: null };
}

function Spinner() {
  return (
    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function ExportModal({ onClose }: { onClose: () => void }) {
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [matchCount, setMatchCount] = useState<number | null>(null);
  const [countLoading, setCountLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const { error: showError } = useToast();

  useEffect(() => {
    api.get<string[]>("/questions/categories").then(setCategories).catch(() => {});
  }, []);

  useEffect(() => {
    setCountLoading(true);
    const params: { status?: string; category?: string } = {};
    if (statusFilter) params.status = statusFilter;
    if (categoryFilter) params.category = categoryFilter;
    questionTransfer.count(params)
      .then(setMatchCount)
      .catch(() => setMatchCount(null))
      .finally(() => setCountLoading(false));
  }, [statusFilter, categoryFilter]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const params: { status?: string; category?: string } = {};
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.category = categoryFilter;
      const blob = await questionTransfer.exportBlob(params);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `questions-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      onClose();
    } catch (err) {
      showError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-background p-6 rounded-lg border border-border shadow-xl w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold text-lg mb-4">Export Questions</h3>

        <div className="space-y-3 mb-5">
          <div>
            <label className="block text-sm font-medium mb-1">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background"
            >
              {QUESTION_STATUSES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Category</label>
            {categories.length > 0 ? (
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background"
              >
                <option value="">All categories</option>
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                placeholder="Filter by category..."
                className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background"
              />
            )}
          </div>
        </div>

        <p className="text-sm text-muted-foreground mb-5">
          {countLoading ? (
            <span className="inline-flex items-center gap-1.5"><Spinner /> Counting...</span>
          ) : matchCount !== null ? (
            <span className="font-medium">{matchCount} question{matchCount !== 1 ? "s" : ""} match</span>
          ) : (
            "Unable to count questions"
          )}
        </p>

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-md text-sm active:scale-[0.97] transition-all duration-150"
          >
            Cancel
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading || matchCount === 0}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 disabled:opacity-50 active:scale-[0.97] transition-all duration-150"
          >
            {downloading ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner />
                Downloading...
              </span>
            ) : (
              "Download JSON"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function ImportModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [previewRows, setPreviewRows] = useState<ImportPreviewRow[]>([]);
  const [payload, setPayload] = useState<{ version: string; questions: unknown[] } | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { success: showSuccess, error: showError } = useToast();

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setImportError(null);
    setGlobalError(null);

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const raw = JSON.parse(reader.result as string);
        const result = parseAndValidate(raw);
        setPreviewRows(result.rows);
        setPayload(result.payload);
        setGlobalError(result.globalError);
      } catch {
        setPreviewRows([]);
        setPayload(null);
        setGlobalError("Could not parse file as JSON");
      }
    };
    reader.readAsText(file);
  }, []);

  const handleImport = async () => {
    if (!payload) return;
    setImporting(true);
    setImportError(null);
    try {
      const result = await questionTransfer.import(payload);
      showSuccess(`Created ${result.created} question${result.created !== 1 ? "s" : ""} in draft status`);
      onSuccess();
      onClose();
    } catch (err) {
      let msg = "Import failed";
      if (err instanceof ApiError && Array.isArray((err.body as Record<string, unknown>)?.detail)) {
        const details = (err.body as Record<string, unknown>).detail as Array<{ msg: string }>;
        msg = details.map((d) => d.msg).join("; ");
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setImportError(msg);
      showError(msg);
    } finally {
      setImporting(false);
    }
  };

  const validCount = previewRows.filter((r) => r.errors.length === 0).length;
  const errorCount = previewRows.filter((r) => r.errors.length > 0).length;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-background p-6 rounded-lg border border-border shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-semibold text-lg mb-4">Import Questions</h3>

        {/* File picker */}
        <div className="mb-4">
          <input
            ref={fileRef}
            type="file"
            accept=".json"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            onClick={() => fileRef.current?.click()}
            className="px-4 py-2 border border-border rounded-md text-sm hover:bg-muted active:scale-[0.97] transition-all duration-150"
          >
            {fileName ? `Selected: ${fileName}` : "Choose JSON file..."}
          </button>
        </div>

        {/* Global error */}
        {globalError && (
          <p className="text-destructive text-sm mb-4 p-3 bg-destructive/5 rounded-md border border-destructive/20">
            {globalError}
          </p>
        )}

        {/* Import error */}
        {importError && (
          <p className="text-destructive text-sm mb-4 p-3 bg-destructive/5 rounded-md border border-destructive/20">
            {importError}
          </p>
        )}

        {/* Preview table */}
        {previewRows.length > 0 && (
          <>
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-medium">{previewRows.length} question{previewRows.length !== 1 ? "s" : ""} found</span>
              {errorCount > 0 && (
                <span className="text-xs text-destructive bg-destructive/10 px-2 py-0.5 rounded-full">
                  {errorCount} with errors
                </span>
              )}
              {validCount > 0 && (
                <span className="text-xs text-status-green bg-status-green/10 px-2 py-0.5 rounded-full">
                  {validCount} valid
                </span>
              )}
            </div>
            <div className="overflow-auto flex-1 border border-border rounded-md mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-3 py-2 font-medium">#</th>
                    <th className="text-left px-3 py-2 font-medium">Title</th>
                    <th className="text-left px-3 py-2 font-medium">Category</th>
                    <th className="text-left px-3 py-2 font-medium">Options</th>
                    <th className="text-left px-3 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, i) => (
                    <tr key={i} className={`border-b border-border last:border-0 ${row.errors.length > 0 ? "bg-destructive/5" : ""}`}>
                      <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
                      <td className="px-3 py-2 max-w-[250px] truncate" title={row.title}>
                        {row.title}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{row.category || "--"}</td>
                      <td className="px-3 py-2 text-muted-foreground">{row.optionCount}</td>
                      <td className="px-3 py-2">
                        {row.errors.length > 0 ? (
                          <span className="text-destructive text-xs">{row.errors.join(", ")}</span>
                        ) : (
                          <span className="text-status-green text-xs">Valid</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-md text-sm active:scale-[0.97] transition-all duration-150"
          >
            Cancel
          </button>
          <button
            onClick={handleImport}
            disabled={!payload || importing}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 disabled:opacity-50 active:scale-[0.97] transition-all duration-150"
          >
            {importing ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner />
                Importing...
              </span>
            ) : errorCount > 0 ? (
              `Fix ${errorCount} error${errorCount !== 1 ? "s" : ""} to import`
            ) : (
              `Import ${validCount} Question${validCount !== 1 ? "s" : ""} as Draft`
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export function QuestionImportExport({ onRefresh }: { onRefresh: () => void }) {
  const [showExport, setShowExport] = useState(false);
  const [showImport, setShowImport] = useState(false);

  return (
    <>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowExport(true)}
          className="text-sm px-3 py-1.5 border border-border rounded-md hover:bg-muted active:scale-[0.97] transition-all duration-150"
        >
          Export
        </button>
        <button
          onClick={() => setShowImport(true)}
          className="text-sm px-3 py-1.5 border border-border rounded-md hover:bg-muted active:scale-[0.97] transition-all duration-150"
        >
          Import
        </button>
      </div>

      {showExport && <ExportModal onClose={() => setShowExport(false)} />}
      {showImport && (
        <ImportModal
          onClose={() => setShowImport(false)}
          onSuccess={onRefresh}
        />
      )}
    </>
  );
}
