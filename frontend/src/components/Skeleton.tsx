/** Reusable skeleton loading placeholders */

function SkeletonLine({ width = "w-full" }: { width?: string }) {
  return (
    <div className={`h-4 ${width} animate-pulse bg-muted rounded`} />
  );
}

/** Matches the question list card shape — rectangle with 3 text lines */
function SkeletonCard() {
  return (
    <div className="bg-background rounded-lg border border-border p-5 space-y-3">
      <div className="h-5 w-3/4 animate-pulse bg-muted rounded" />
      <div className="h-4 w-full animate-pulse bg-muted rounded" />
      <div className="h-4 w-1/2 animate-pulse bg-muted rounded" />
    </div>
  );
}

/** Matches the detail page card shape — header area + body block */
function SkeletonDetail() {
  return (
    <div className="bg-background rounded-lg border border-border p-6 space-y-4">
      <div className="h-6 w-2/3 animate-pulse bg-muted rounded" />
      <div className="space-y-2">
        <div className="h-4 w-full animate-pulse bg-muted rounded" />
        <div className="h-4 w-full animate-pulse bg-muted rounded" />
        <div className="h-4 w-5/6 animate-pulse bg-muted rounded" />
      </div>
      <div className="flex gap-3 pt-2">
        <div className="h-8 w-20 animate-pulse bg-muted rounded" />
        <div className="h-8 w-20 animate-pulse bg-muted rounded" />
      </div>
    </div>
  );
}

export { SkeletonLine, SkeletonCard, SkeletonDetail };
