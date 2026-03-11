import { useState, useEffect, useCallback } from "react";
import { sourceDocuments, SourceDocument, SourceDocumentDetail } from "@/api/client";

export function SourceDocuments() {
  const [docs, setDocs] = useState<SourceDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<SourceDocumentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const loadDocs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await sourceDocuments.list();
      setDocs(data.items);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleView = async (id: string) => {
    setDetailLoading(true);
    try {
      const detail = await sourceDocuments.get(id);
      setSelectedDoc(detail);
    } catch (e: unknown) {
      setToast(e instanceof Error ? e.message : "Failed to load document");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDownload = async (doc: SourceDocument | SourceDocumentDetail) => {
    try {
      let body: string;
      if ("body" in doc) {
        body = doc.body;
      } else {
        const detail = await sourceDocuments.get(doc.id);
        body = detail.body;
      }
      const blob = new Blob([body], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${doc.title}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setToast(e instanceof Error ? e.message : "Failed to download");
    }
  };

  const handleDelete = async (id: string) => {
    setDeleting(true);
    try {
      await sourceDocuments.delete(id);
      setDeleteConfirmId(null);
      setToast("Document deleted");
      await loadDocs();
    } catch (e: unknown) {
      setToast(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Source Documents</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Documents used for question extraction
        </p>
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-foreground text-background px-4 py-2 rounded-md text-sm shadow-lg">
          {toast}
        </div>
      )}

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
                <th className="text-right px-4 py-3 font-medium text-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id} className="border-t border-border hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleView(doc.id)}
                      className="text-left hover:underline"
                    >
                      <div className="font-medium text-foreground">{doc.title}</div>
                      {doc.document_summary && (
                        <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                          {doc.document_summary}
                        </div>
                      )}
                    </button>
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
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      onClick={() => handleDownload(doc)}
                      className="text-xs text-muted-foreground hover:text-foreground px-2 py-1"
                      title="Download"
                    >
                      Download
                    </button>
                    <button
                      onClick={() => setDeleteConfirmId(doc.id)}
                      className="text-xs text-destructive hover:text-destructive/80 px-2 py-1 ml-1"
                      title="Delete"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border border-border rounded-lg p-6 max-w-sm w-full mx-4 shadow-lg">
            <h3 className="text-lg font-semibold text-foreground">Delete Document</h3>
            <p className="text-sm text-muted-foreground mt-2">
              Are you sure? Linked questions will have their source reference removed.
            </p>
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="px-3 py-1.5 text-sm border border-border rounded-md hover:bg-muted"
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmId)}
                className="px-3 py-1.5 text-sm bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50"
                disabled={deleting}
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail modal */}
      {(selectedDoc || detailLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border border-border rounded-lg max-w-3xl w-full mx-4 shadow-lg max-h-[85vh] flex flex-col">
            {detailLoading ? (
              <div className="p-6">
                <p className="text-sm text-muted-foreground">Loading...</p>
              </div>
            ) : selectedDoc && (
              <>
                <div className="flex items-start justify-between p-6 border-b border-border">
                  <div>
                    <h2 className="text-lg font-semibold text-foreground">{selectedDoc.title}</h2>
                    <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
                      {selectedDoc.domain && <span>Domain: {selectedDoc.domain}</span>}
                      <span>Questions: {selectedDoc.question_count}</span>
                      <span>By: {selectedDoc.uploaded_by.display_name}</span>
                      <span>{new Date(selectedDoc.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedDoc(null)}
                    className="text-muted-foreground hover:text-foreground text-xl leading-none p-1"
                  >
                    x
                  </button>
                </div>
                {selectedDoc.document_summary && (
                  <div className="px-6 py-3 border-b border-border">
                    <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Summary</h3>
                    <p className="text-sm text-foreground">{selectedDoc.document_summary}</p>
                  </div>
                )}
                <div className="px-6 py-3 overflow-auto flex-1 min-h-0">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Document Body</h3>
                  <pre className="text-sm text-foreground whitespace-pre-wrap font-mono bg-muted p-4 rounded-md max-h-[50vh] overflow-auto">
                    {selectedDoc.body}
                  </pre>
                </div>
                <div className="px-6 py-3 border-t border-border flex justify-end">
                  <button
                    onClick={() => handleDownload(selectedDoc)}
                    className="px-3 py-1.5 text-sm border border-border rounded-md hover:bg-muted"
                  >
                    Download
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
