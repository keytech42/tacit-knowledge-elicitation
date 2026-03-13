import { useEffect, useState } from "react";
import { api, mlExport, type MLExportParams } from "@/api/client";
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

const ENTITY_TYPES = [
  { value: "", label: "All entities" },
  { value: "question", label: "Questions" },
  { value: "answer", label: "Answers" },
];

const VERDICTS = [
  { value: "", label: "All verdicts" },
  { value: "approved", label: "Approved" },
  { value: "changes_requested", label: "Changes Requested" },
  { value: "rejected", label: "Rejected" },
  { value: "superseded", label: "Superseded" },
];

function Spinner() {
  return (
    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function todayStamp(): string {
  return new Date().toISOString().slice(0, 10);
}

function triggerDownload(blob: Blob, filename: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function DateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background"
      />
    </div>
  );
}

function DownloadButton({
  downloading,
  onClick,
}: {
  downloading: boolean;
  onClick: () => void;
}) {
  return (
    <div className="flex justify-end pt-2">
      <button
        onClick={onClick}
        disabled={downloading}
        className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 disabled:opacity-50 active:scale-[0.97] transition-all duration-150"
      >
        {downloading ? (
          <span className="inline-flex items-center gap-1.5">
            <Spinner />
            Downloading...
          </span>
        ) : (
          "Download JSONL"
        )}
      </button>
    </div>
  );
}

function TrainingDataCard({ categories }: { categories: string[] }) {
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [downloading, setDownloading] = useState(false);
  const { info, error: showError } = useToast();

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const params: MLExportParams = {};
      if (status) params.question_status = status;
      if (category) params.category = category;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const blob = await mlExport.trainingData(params);
      if (blob.size === 0) {
        info("No records matched filters");
        return;
      }
      triggerDownload(blob, `training-data-${todayStamp()}.jsonl`);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setDownloading(false);
    }
  };

  const categoryOptions = [
    { value: "", label: "All categories" },
    ...categories.map((c) => ({ value: c, label: c })),
  ];

  return (
    <section className="bg-background border border-border rounded-lg p-6">
      <h2 className="text-lg font-semibold mb-1">Training Data</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Export question-answer pairs as JSONL for fine-tuning or supervised learning.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <SelectField label="Question status" value={status} onChange={setStatus} options={QUESTION_STATUSES} />
        <SelectField label="Category" value={category} onChange={setCategory} options={categoryOptions} />
        <DateField label="Date from" value={dateFrom} onChange={setDateFrom} />
        <DateField label="Date to" value={dateTo} onChange={setDateTo} />
      </div>
      <DownloadButton downloading={downloading} onClick={handleDownload} />
    </section>
  );
}

function EmbeddingsCard() {
  const [entityType, setEntityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [downloading, setDownloading] = useState(false);
  const { info, error: showError } = useToast();

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const params: MLExportParams = {};
      if (entityType) params.entity_type = entityType;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const blob = await mlExport.embeddings(params);
      if (blob.size === 0) {
        info("No records matched filters");
        return;
      }
      triggerDownload(blob, `embeddings-${todayStamp()}.jsonl`);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <section className="bg-background border border-border rounded-lg p-6">
      <h2 className="text-lg font-semibold mb-1">Embeddings</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Export entity embeddings as JSONL for similarity search, clustering, or visualization.
      </p>
      <div className="grid grid-cols-3 gap-3">
        <SelectField label="Entity type" value={entityType} onChange={setEntityType} options={ENTITY_TYPES} />
        <DateField label="Date from" value={dateFrom} onChange={setDateFrom} />
        <DateField label="Date to" value={dateTo} onChange={setDateTo} />
      </div>
      <DownloadButton downloading={downloading} onClick={handleDownload} />
    </section>
  );
}

function ReviewPairsCard() {
  const [verdict, setVerdict] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [downloading, setDownloading] = useState(false);
  const { info, error: showError } = useToast();

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const params: MLExportParams = {};
      if (verdict) params.verdict = verdict;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const blob = await mlExport.reviewPairs(params);
      if (blob.size === 0) {
        info("No records matched filters");
        return;
      }
      triggerDownload(blob, `review-pairs-${todayStamp()}.jsonl`);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <section className="bg-background border border-border rounded-lg p-6">
      <h2 className="text-lg font-semibold mb-1">Review Pairs</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Export answer-review pairs as JSONL for RLHF or reward model training.
      </p>
      <div className="grid grid-cols-3 gap-3">
        <SelectField label="Verdict" value={verdict} onChange={setVerdict} options={VERDICTS} />
        <DateField label="Date from" value={dateFrom} onChange={setDateFrom} />
        <DateField label="Date to" value={dateTo} onChange={setDateTo} />
      </div>
      <DownloadButton downloading={downloading} onClick={handleDownload} />
    </section>
  );
}

export function MLExport() {
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    api.get<string[]>("/questions/categories").then(setCategories).catch(() => {});
  }, []);

  return (
    <div className="space-y-6 max-w-5xl">
      <header>
        <h1 className="text-2xl font-bold">ML Data Export</h1>
        <p className="text-muted-foreground mt-1">
          Download datasets for machine learning workflows.
        </p>
      </header>
      <TrainingDataCard categories={categories} />
      <EmbeddingsCard />
      <ReviewPairsCard />
    </div>
  );
}
