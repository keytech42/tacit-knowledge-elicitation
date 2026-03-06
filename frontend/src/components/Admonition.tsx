const VARIANT_TOKEN: Record<string, string> = {
  warning: "status-amber",
  success: "status-green",
  error: "status-red",
  info: "status-blue",
};

interface AdmonitionProps {
  variant: keyof typeof VARIANT_TOKEN;
  title?: string;
  children: React.ReactNode;
  size?: "sm" | "xs";
}

export function Admonition({ variant, title, children, size = "sm" }: AdmonitionProps) {
  const token = VARIANT_TOKEN[variant];
  const textSize = size === "sm" ? "text-sm" : "text-xs";
  const titleSize = size === "sm" ? "text-sm" : "text-xs";

  return (
    <div className={`p-3 rounded-md border border-${token}/20 bg-${token}/5 ${textSize}`}>
      {title && <p className={`font-medium text-${token} ${titleSize} mb-0.5`}>{title}</p>}
      <div className="text-muted-foreground">{children}</div>
    </div>
  );
}
