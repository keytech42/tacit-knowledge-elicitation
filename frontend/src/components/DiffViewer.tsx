interface DiffViewerProps {
  diff: string;
  className?: string;
}

export function DiffViewer({ diff, className = "" }: DiffViewerProps) {
  return (
    <div className={`bg-muted rounded text-xs overflow-x-auto font-mono border border-border ${className}`}>
      {diff.split("\n").map((line, i) => {
        let bg = "";
        let fg = "text-foreground/70";
        if (line.startsWith("+++") || line.startsWith("---")) {
          bg = "bg-muted";
          fg = "text-muted-foreground font-semibold";
        } else if (line.startsWith("@@")) {
          bg = "bg-blue-500/10";
          fg = "text-blue-600 dark:text-blue-400";
        } else if (line.startsWith("+")) {
          bg = "bg-green-500/15";
          fg = "text-green-700 dark:text-green-400";
        } else if (line.startsWith("-")) {
          bg = "bg-red-500/15";
          fg = "text-red-700 dark:text-red-400";
        }
        return (
          <div key={i} className={`px-3 py-0.5 ${bg} ${fg} whitespace-pre-wrap`}>
            {line || "\u00a0"}
          </div>
        );
      })}
    </div>
  );
}
