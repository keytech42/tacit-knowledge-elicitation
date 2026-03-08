const VARIANT_CLASSES: Record<string, string> = {
  primary: "bg-primary text-primary-foreground hover:bg-primary/90",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  danger: "bg-status-red/85 text-white hover:bg-status-red",
  green: "bg-status-green text-white hover:bg-status-green/90",
  blue: "bg-status-blue text-white hover:bg-status-blue/90",
  purple: "bg-status-blue text-white hover:bg-status-blue/90",
  gray: "bg-muted text-muted-foreground hover:bg-muted/80",
};

function Spinner() {
  return (
    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

interface ActionButtonProps {
  label: string;
  onClick: () => void;
  enabled: boolean;
  /** Why the action is unavailable */
  disabledReason?: string;
  /** What the user can do instead */
  disabledHint?: string;
  variant?: keyof typeof VARIANT_CLASSES;
  className?: string;
  loading?: boolean;
}

export function ActionButton({
  label,
  onClick,
  enabled,
  disabledReason,
  disabledHint,
  variant = "secondary",
  className = "",
  loading = false,
}: ActionButtonProps) {
  if (enabled) {
    return (
      <button
        onClick={onClick}
        disabled={loading}
        className={`px-3 py-1.5 rounded text-sm font-medium active:scale-[0.97] transition-all duration-150 ${VARIANT_CLASSES[variant]} ${loading ? "opacity-75 cursor-wait" : ""} ${className}`}
      >
        {loading ? (
          <span className="inline-flex items-center gap-1.5">
            <Spinner />
            {label}
          </span>
        ) : (
          label
        )}
      </button>
    );
  }

  return (
    <span className={`relative group inline-block ${className}`}>
      <button
        disabled
        className={`px-3 py-1.5 rounded text-sm font-medium bg-muted text-muted-foreground/50 cursor-not-allowed border border-border`}
        aria-disabled="true"
        aria-describedby={disabledReason ? undefined : undefined}
      >
        {label}
      </button>
      {disabledReason && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-50 pointer-events-none">
          <div className="bg-foreground text-background text-xs rounded-lg px-3 py-2 shadow-lg w-56 text-center leading-relaxed">
            <p className="font-medium">{disabledReason}</p>
            {disabledHint && <p className="mt-1 opacity-80">{disabledHint}</p>}
          </div>
          <div className="w-2 h-2 bg-foreground rotate-45 mx-auto -mt-1" />
        </div>
      )}
    </span>
  );
}
