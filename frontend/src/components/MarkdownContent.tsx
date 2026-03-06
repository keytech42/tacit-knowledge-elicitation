import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-lg font-bold mt-4 mb-2 text-foreground">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-semibold mt-3 mb-1.5 text-foreground">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold mt-2 mb-1 text-foreground">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="mb-2 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="text-foreground/80">{children}</li>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-border pl-3 my-2 text-muted-foreground italic">{children}</blockquote>
  ),
  code: ({ children, className }) => {
    const isBlock = className?.startsWith("language-");
    if (isBlock) {
      return (
        <code className={`text-sm ${className}`}>{children}</code>
      );
    }
    return (
      <code className="bg-muted px-1 py-0.5 rounded text-sm font-mono">{children}</code>
    );
  },
  pre: ({ children }) => (
    <pre className="bg-muted rounded-md p-3 my-2 overflow-x-auto text-sm font-mono border border-border">{children}</pre>
  ),
  a: ({ href, children }) => (
    <a href={href} className="text-primary underline hover:opacity-80" target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-2">
      <table className="w-full text-sm border border-border">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-muted">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="border border-border px-3 py-1.5 text-left text-xs font-medium">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border border-border px-3 py-1.5">{children}</td>
  ),
  hr: () => <hr className="border-border my-3" />,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  del: ({ children }) => <del className="text-muted-foreground">{children}</del>,
};

/**
 * Preprocesses content for markdown rendering:
 * - Converts literal `\n` strings (from AI-generated content) to actual newlines
 */
function preprocessContent(content: string): string {
  return content.replace(/\\n/g, "\n");
}

interface MarkdownContentProps {
  children: string;
  className?: string;
}

export function MarkdownContent({ children, className }: MarkdownContentProps) {
  const processed = preprocessContent(children);
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {processed}
      </ReactMarkdown>
    </div>
  );
}
