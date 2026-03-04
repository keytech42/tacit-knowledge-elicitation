import { Navigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { ReactNode } from "react";

export function ProtectedRoute({ children, requiredRole }: { children: ReactNode; requiredRole?: string }) {
  const { user, hasRole } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && !hasRole(requiredRole)) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold text-destructive">Access Denied</h2>
        <p className="text-muted-foreground mt-2">You don't have permission to view this page.</p>
      </div>
    );
  }

  return <>{children}</>;
}
