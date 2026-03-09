import { useState, useEffect } from "react";
import { sourceDocuments, SourceDocument } from "@/api/client";

export function SourceDocuments() {
  const [docs, setDocs] = useState<SourceDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await sourceDocuments.list();
        if (!cancelled) setDocs(data.items);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load documents");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Source Documents</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Documents used for question extraction
        </p>
      </div>

      {loading && (
        <p className="text-sm text-muted-foreground">Loading...</p>
      )}

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {!loading && !error && docs.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No source documents yet. Use the Extract Questions tool in AI Controls to create one.
        </p>
      )}

      {docs.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-foreground">Title</th>
                <th className="text-left px-4 py-3 font-medium text-foreground">Domain</th>
                <th className="text-left px-4 py-3 font-medium text-foreground">Questions</th>
                <th className="text-left px-4 py-3 font-medium text-foreground">Uploaded By</th>
                <th className="text-left px-4 py-3 font-medium text-foreground">Date</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id} className="border-t border-border">
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">{doc.title}</div>
                    {doc.document_summary && (
                      <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                        {doc.document_summary}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {doc.domain || "\u2014"}
                  </td>
                  <td className="px-4 py-3 text-foreground">
                    {doc.question_count}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {doc.uploaded_by.display_name}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
