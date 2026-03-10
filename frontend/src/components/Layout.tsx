import { useState, useRef, useEffect } from "react";
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

const adminLinks = [
  { to: "/admin/questions", label: "Admin Queue" },
  { to: "/admin/service-accounts", label: "Service Accounts" },
  { to: "/admin/ai-logs", label: "AI Logs" },
  { to: "/admin/ai", label: "AI Controls" },
  { to: "/admin/source-documents", label: "Documents" },
];

function AdminDropdown() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const isAdminActive = adminLinks.some(
    (l) => pathname === l.to || pathname.startsWith(l.to + "/")
  );

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className={`text-sm px-3 py-1.5 rounded-md transition-colors flex items-center gap-1 ${
          isAdminActive
            ? "bg-primary text-primary-foreground font-medium"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
      >
        Admin
        <svg
          className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 mt-1 w-48 bg-background border border-border rounded-lg shadow-lg py-1 z-50">
          {adminLinks.map((link) => {
            const isActive = pathname === link.to || pathname.startsWith(link.to + "/");
            return (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setOpen(false)}
                className={`block px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-foreground hover:bg-muted"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { user, logout, hasRole } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!user) return null;

  const initials = user.display_name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-muted transition-colors"
      >
        <div className="w-7 h-7 rounded-full bg-primary/10 text-primary text-xs font-semibold flex items-center justify-center">
          {initials}
        </div>
        <span className="text-sm text-muted-foreground">{user.display_name}</span>
        <svg className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute right-0 mt-1 w-48 bg-background border border-border rounded-lg shadow-lg py-1 z-50"
          style={{
            animation: "userMenuIn 100ms ease-out",
          }}
        >
          <style>{`
            @keyframes userMenuIn {
              from { opacity: 0; transform: translateY(-4px); }
              to { opacity: 1; transform: translateY(0); }
            }
          `}</style>
          <div className="px-3 py-2 border-b border-border">
            <p className="text-sm font-medium truncate">{user.display_name}</p>
            {user.email && <p className="text-xs text-muted-foreground truncate">{user.email}</p>}
            <div className="flex flex-wrap gap-1 mt-1">
              {user.roles.map((r) => (
                <span key={r.id} className="text-[10px] px-1.5 py-0.5 bg-muted rounded-full text-muted-foreground capitalize">
                  {r.name}
                </span>
              ))}
            </div>
          </div>
          {hasRole("admin") && (
            <button
              onClick={() => { setOpen(false); navigate("/settings"); }}
              className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Settings
            </button>
          )}
          <button
            onClick={() => { setOpen(false); logout(); navigate("/login"); }}
            className="w-full text-left px-3 py-2 text-sm text-destructive hover:bg-muted transition-colors"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const { hasRole } = useAuth();
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen bg-muted">
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
      <nav className="bg-background border-b border-border">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Link to="/" className="font-bold text-lg mr-4">KEP</Link>
            <NavLink to="/questions">Questions</NavLink>
            {(hasRole("reviewer") || hasRole("admin")) && (
              <NavLink to="/reviews">Reviews</NavLink>
            )}
            {hasRole("admin") && <AdminDropdown />}
          </div>
          <UserMenu />
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div key={pathname} style={{ animation: "fadeIn 150ms ease-out" }}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
