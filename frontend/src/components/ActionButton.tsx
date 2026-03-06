const VARIANT_CLASSES: Record<string, string> = {
  primary: "bg-primary text-primary-foreground",
  secondary: "bg-secondary text-secondary-foreground",
  danger: "bg-status-red text-white",
  green: "bg-status-green text-white",
  blue: "bg-status-blue text-white",
  purple: "bg-status-blue text-white",
  gray: "bg-muted text-muted-foreground",
};

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
}

export function ActionButton({
  label,
  onClick,
  enabled,
  disabledReason,
  disabledHint,
  variant = "secondary",
  className = "",
}: ActionButtonProps) {
  if (enabled) {
    return (
      <button
        onClick={onClick}
        className={`px-3 py-1.5 rounded text-sm font-medium ${VARIANT_CLASSES[variant]} ${className}`}
      >
        {label}
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
