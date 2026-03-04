import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";

export function Layout() {
  const { user, logout, hasRole } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-muted">
      <nav className="bg-background border-b border-border">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="font-bold text-lg">KEP</Link>
            <Link to="/questions" className="text-sm text-muted-foreground hover:text-foreground">Questions</Link>
            {(hasRole("reviewer") || hasRole("admin")) && (
              <Link to="/reviews" className="text-sm text-muted-foreground hover:text-foreground">Reviews</Link>
            )}
            {hasRole("admin") && (
              <>
                <Link to="/admin/questions" className="text-sm text-muted-foreground hover:text-foreground">Admin Queue</Link>
                <Link to="/admin/service-accounts" className="text-sm text-muted-foreground hover:text-foreground">Service Accounts</Link>
                <Link to="/admin/ai-logs" className="text-sm text-muted-foreground hover:text-foreground">AI Logs</Link>
              </>
            )}
          </div>
          <div className="flex items-center gap-4">
            {user && (
              <>
                <span className="text-sm text-muted-foreground">{user.display_name}</span>
                <button onClick={handleLogout} className="text-sm text-destructive hover:underline">Sign out</button>
              </>
            )}
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
