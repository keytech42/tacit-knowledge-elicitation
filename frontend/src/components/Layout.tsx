import { Link, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const { pathname } = useLocation();
  const isActive = pathname === to || pathname.startsWith(to + "/");
  return (
    <Link
      to={to}
      className={`text-sm px-3 py-1.5 rounded-md transition-colors ${
        isActive
          ? "bg-primary text-primary-foreground font-medium"
          : "text-muted-foreground hover:text-foreground hover:bg-muted"
      }`}
    >
      {children}
    </Link>
  );
}

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
          <div className="flex items-center gap-1">
            <Link to="/" className="font-bold text-lg mr-4">KEP</Link>
            <NavLink to="/questions">Questions</NavLink>
            {(hasRole("reviewer") || hasRole("admin")) && (
              <NavLink to="/reviews">Reviews</NavLink>
            )}
            {hasRole("admin") && (
              <>
                <NavLink to="/admin/questions">Admin Queue</NavLink>
                <NavLink to="/admin/service-accounts">Service Accounts</NavLink>
                <NavLink to="/admin/ai-logs">AI Logs</NavLink>
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
