import { useTimestampFormat } from "@/hooks/useTimestampFormat";

interface TimestampProps {
  iso: string;
  className?: string;
}

export function Timestamp({ iso, className }: TimestampProps) {
  const { formatTimestamp } = useTimestampFormat();
  const { display, title } = formatTimestamp(iso);

  return (
    <time dateTime={iso} title={title} className={className}>
      {display}
    </time>
  );
}
