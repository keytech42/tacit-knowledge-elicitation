import { useEffect, useState } from "react";
import { api, User } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

const ALL_ROLES = ["admin", "author", "reviewer", "respondent"];

const ROLE_DESCRIPTIONS: Record<string, string> = {
  admin: "Full system access, user management, question pipeline",
  author: "Create and manage questions",
  reviewer: "Review answers and questions",
  respondent: "Answer published questions",
};

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-status-red/10 text-status-red border border-status-red/20",
  author: "bg-status-blue/10 text-status-blue border border-status-blue/20",
  reviewer: "bg-status-amber/10 text-status-amber border border-status-amber/20",
  respondent: "bg-status-green/10 text-status-green border border-status-green/20",
};

interface UsersResponse {
  users: User[];
  total: number;
}

export function Settings() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const data = await api.get<UsersResponse>("/users?limit=200");
      setUsers(data.users);
      setTotal(data.total);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const toggleRole = async (userId: string, roleName: string, hasIt: boolean) => {
    // Warn if the current user is removing their own admin role
    if (hasIt && roleName === "admin" && currentUser && userId === currentUser.id) {
      const confirmed = window.confirm(
        "You are about to remove your own Admin role. " +
        "This will lock you out of Settings and all admin features. " +
        "Are you sure?"
      );
      if (!confirmed) return;
    }

    const key = `${userId}-${roleName}`;
    setPendingAction(key);
    setActionError(null);
    try {
      if (hasIt) {
        await api.delete(`/users/${userId}/roles/${roleName}`);
      } else {
        await api.post(`/users/${userId}/roles`, { role_name: roleName });
      }
      // Refresh user list to get updated roles
      await fetchUsers();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Failed to update role");
    } finally {
      setPendingAction(null);
    }
  };

  const filtered = users.filter(
    (u) =>
      u.user_type === "human" &&
      (search === "" ||
        u.display_name.toLowerCase().includes(search.toLowerCase()) ||
        (u.email && u.email.toLowerCase().includes(search.toLowerCase())))
  );

  if (loading) {
    return (
      <div className="text-center py-12 text-muted-foreground">Loading settings...</div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">{error}</div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      {/* Member Management Section */}
      <div className="bg-background border border-border rounded-lg">
        <div className="px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold">Member Management</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Manage organization members and their roles. {total} total users.
          </p>
        </div>

        {/* Role legend */}
        <div className="px-6 py-3 border-b border-border bg-muted/30">
          <div className="flex flex-wrap gap-3">
            {ALL_ROLES.map((role) => (
              <div key={role} className="flex items-center gap-1.5">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ROLE_COLORS[role]}`}>
                  {role}
                </span>
                <span className="text-xs text-muted-foreground">{ROLE_DESCRIPTIONS[role]}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-border">
          <input
            type="text"
            placeholder="Search members by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full max-w-sm px-3 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>

        {actionError && (
          <div className="mx-6 mt-3 px-3 py-2 bg-destructive/10 text-destructive text-sm rounded-md">
            {actionError}
          </div>
        )}

        {/* User table */}
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="px-6 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Member</th>
                {ALL_ROLES.map((role) => (
                  <th key={role} className="px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider text-center">
                    {role}
                  </th>
                ))}
                <th className="px-6 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((u) => {
                const userRoles = new Set(u.roles.map((r) => r.name));
                return (
                  <tr key={u.id} className="hover:bg-muted/50 transition-colors">
                    <td className="px-6 py-3">
                      <div>
                        <p className="text-sm font-medium">{u.display_name}</p>
                        {u.email && <p className="text-xs text-muted-foreground">{u.email}</p>}
                      </div>
                    </td>
                    {ALL_ROLES.map((role) => {
                      const has = userRoles.has(role);
                      const isPending = pendingAction === `${u.id}-${role}`;
                      return (
                        <td key={role} className="px-4 py-3 text-center">
                          <button
                            onClick={() => toggleRole(u.id, role, has)}
                            disabled={isPending}
                            className={`w-8 h-8 rounded-md border transition-all text-sm font-medium ${
                              has
                                ? `${ROLE_COLORS[role]} border-current`
                                : "bg-background border-border text-muted-foreground/40 hover:border-foreground/30 hover:text-foreground/60"
                            } ${isPending ? "opacity-50 cursor-wait" : "cursor-pointer"}`}
                            title={has ? `Remove ${role} role` : `Assign ${role} role`}
                          >
                            {isPending ? "..." : has ? "\u2713" : ""}
                          </button>
                        </td>
                      );
                    })}
                    <td className="px-6 py-3 text-xs text-muted-foreground">
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {filtered.length === 0 && (
          <div className="text-center py-8 text-muted-foreground text-sm">
            {search ? "No members match your search." : "No members found."}
          </div>
        )}
      </div>
    </div>
  );
}
