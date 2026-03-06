import { useEffect, useState } from "react";
import { api } from "@/api/client";

interface ServiceAccount {
  id: string;
  display_name: string;
  model_id: string | null;
  system_version: string | null;
  is_active: boolean;
  roles: { name: string }[];
  created_at: string;
}

export function ServiceAccounts() {
  const [accounts, setAccounts] = useState<ServiceAccount[]>([]);
  const [name, setName] = useState("");
  const [modelId, setModelId] = useState("");
  const [newKey, setNewKey] = useState("");

  const loadAccounts = () => {
    api.get<ServiceAccount[]>("/service-accounts").then(setAccounts);
  };

  useEffect(loadAccounts, []);

  const handleCreate = async () => {
    if (!name.trim()) return;
    const result = await api.post<ServiceAccount & { api_key: string }>("/service-accounts", {
      display_name: name, model_id: modelId || null,
    });
    setNewKey(result.api_key);
    setName("");
    setModelId("");
    loadAccounts();
  };

  const handleRotate = async (id: string) => {
    const result = await api.post<{ api_key: string }>(`/service-accounts/${id}/rotate-key`);
    setNewKey(result.api_key);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Service Accounts</h1>

      {/* Create form */}
      <div className="bg-background p-6 rounded-lg border border-border mb-6">
        <h2 className="font-semibold mb-3">Create Service Account</h2>
        <div className="flex gap-3">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Display name" className="flex-1 border border-border rounded-md px-3 py-2 text-sm bg-background" />
          <input value={modelId} onChange={(e) => setModelId(e.target.value)} placeholder="Model ID (optional)" className="flex-1 border border-border rounded-md px-3 py-2 text-sm bg-background" />
          <button onClick={handleCreate} disabled={!name.trim()} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm disabled:opacity-50">Create</button>
        </div>
      </div>

      {newKey && (
        <div className="bg-muted border border-border p-4 rounded-lg mb-6">
          <p className="text-sm font-medium text-foreground mb-1">API Key (shown once — save it now)</p>
          <code className="text-xs break-all bg-secondary p-2 rounded block">{newKey}</code>
          <button onClick={() => setNewKey("")} className="mt-2 text-xs text-muted-foreground hover:underline">Dismiss</button>
        </div>
      )}

      {/* List */}
      <div className="space-y-3">
        {accounts.map((acct) => (
          <div key={acct.id} className="bg-background p-4 rounded-lg border border-border">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-medium">{acct.display_name}</h3>
                <p className="text-xs text-muted-foreground mt-1">
                  {acct.model_id && `Model: ${acct.model_id}`}
                  {acct.system_version && ` · Version: ${acct.system_version}`}
                </p>
                <p className="text-xs text-muted-foreground">Roles: {acct.roles.map((r) => r.name).join(", ")}</p>
              </div>
              <button onClick={() => handleRotate(acct.id)} className="text-sm border border-border px-3 py-1.5 rounded hover:bg-muted">Rotate Key</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
