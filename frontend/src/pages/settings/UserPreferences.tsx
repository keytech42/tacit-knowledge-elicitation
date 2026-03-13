import { useTimestampFormat, TimestampFormat } from "@/hooks/useTimestampFormat";

const FORMAT_OPTIONS: { value: TimestampFormat; label: string; example: string }[] = [
  { value: "24h", label: "24-hour", example: "2026-03-12 14:34 · 2d ago" },
  { value: "12h", label: "12-hour", example: "Mar 12, 2026 2:34 PM · 2d ago" },
  { value: "relative", label: "Relative only", example: "2 days ago" },
];

export function UserPreferences() {
  const { format, setFormat } = useTimestampFormat();

  return (
    <div className="max-w-xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Preferences</h1>

      <div className="bg-background p-6 rounded-lg border border-border">
        <h2 className="text-sm font-semibold mb-3">Timestamp Format</h2>
        <div className="space-y-2">
          {FORMAT_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`flex items-center gap-3 p-3 rounded-md border cursor-pointer transition-colors ${
                format === opt.value
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              <input
                type="radio"
                name="timestamp-format"
                value={opt.value}
                checked={format === opt.value}
                onChange={() => setFormat(opt.value)}
                className="accent-primary"
              />
              <div>
                <p className="text-sm font-medium">{opt.label}</p>
                <p className="text-xs text-muted-foreground font-mono">{opt.example}</p>
              </div>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
