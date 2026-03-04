import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, Answer, AnswerRevision, Review } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

export function AnswerDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, hasRole } = useAuth();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [revisions, setRevisions] = useState<AnswerRevision[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [editing, setEditing] = useState(false);
  const [editBody, setEditBody] = useState("");

  useEffect(() => {
    if (!id) return;
    api.get<Answer>(`/answers/${id}`).then((a) => { setAnswer(a); setEditBody(a.body); });
    api.get<AnswerRevision[]>(`/answers/${id}/versions`).then(setRevisions);
    api.get<Review[]>(`/reviews?target_type=answer&target_id=${id}`).then(setReviews);
  }, [id]);

  const handleSave = async () => {
    if (!id) return;
    const updated = await api.patch<Answer>(`/answers/${id}`, { body: editBody });
    setAnswer(updated);
    setEditing(false);
  };

  const handleRevise = async () => {
    if (!id) return;
    const updated = await api.post<Answer>(`/answers/${id}/revise`);
    setAnswer(updated);
  };

  if (!answer) return <p className="text-center py-8 text-muted-foreground">Loading...</p>;

  const isAuthor = user?.id === answer.author.id;
  const canEdit = isAuthor && (answer.status === "draft" || answer.status === "revision_requested") || hasRole("admin");
  const canRevise = isAuthor && answer.status === "approved";

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-xs px-2 py-1 rounded-full bg-primary/10 font-medium">{answer.status}</span>
          <span className="text-xs text-muted-foreground">Version {answer.current_version}</span>
          <Link to={`/questions/${answer.question_id}`} className="text-xs text-blue-600 hover:underline ml-auto">Back to question</Link>
        </div>

        {editing ? (
          <>
            <textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} className="w-full border border-border rounded-md p-3 min-h-[200px] bg-background text-sm" />
            <div className="flex gap-2 mt-3">
              <button onClick={handleSave} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm">Save</button>
              <button onClick={() => setEditing(false)} className="border border-border px-4 py-2 rounded-md text-sm">Cancel</button>
            </div>
          </>
        ) : (
          <>
            <p className="whitespace-pre-wrap text-foreground/80">{answer.body}</p>
            <div className="text-sm text-muted-foreground mt-4">
              by {answer.author.display_name} &middot; {new Date(answer.created_at).toLocaleDateString()}
            </div>
            <div className="flex gap-2 mt-4 pt-4 border-t border-border">
              {canEdit && <button onClick={() => setEditing(true)} className="bg-secondary text-secondary-foreground px-3 py-1.5 rounded text-sm">Edit</button>}
              {canRevise && <button onClick={handleRevise} className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm">Revise (new version)</button>}
            </div>
          </>
        )}
      </div>

      {/* Version History */}
      <h2 className="font-semibold text-lg mb-3">Version History</h2>
      <div className="space-y-2 mb-6">
        {revisions.map((rev) => (
          <div key={rev.id} className="bg-background p-3 rounded border border-border text-sm">
            <div className="flex items-center gap-3">
              <span className="font-mono font-medium">v{rev.version}</span>
              <span className="text-xs bg-secondary px-2 py-0.5 rounded">{rev.trigger.replace(/_/g, " ")}</span>
              <span className="text-xs text-muted-foreground">{rev.created_by.display_name}</span>
              <span className="text-xs text-muted-foreground ml-auto">{new Date(rev.created_at).toLocaleString()}</span>
            </div>
          </div>
        ))}
        {revisions.length === 0 && <p className="text-sm text-muted-foreground">No revisions yet.</p>}
      </div>

      {/* Reviews */}
      <h2 className="font-semibold text-lg mb-3">Reviews</h2>
      <div className="space-y-2">
        {reviews.map((rev) => (
          <Link key={rev.id} to={`/reviews/${rev.id}`} className="block bg-background p-3 rounded border border-border text-sm hover:border-primary/30">
            <div className="flex items-center gap-3">
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                rev.verdict === "approved" ? "bg-green-100 text-green-800" :
                rev.verdict === "changes_requested" ? "bg-yellow-100 text-yellow-800" :
                rev.verdict === "rejected" ? "bg-red-100 text-red-800" : "bg-gray-100"
              }`}>{rev.verdict}</span>
              <span className="text-muted-foreground">{rev.reviewer.display_name}</span>
              {rev.comment && <span className="text-muted-foreground truncate ml-auto max-w-[200px]">{rev.comment}</span>}
            </div>
          </Link>
        ))}
        {reviews.length === 0 && <p className="text-sm text-muted-foreground">No reviews yet.</p>}
      </div>
    </div>
  );
}
