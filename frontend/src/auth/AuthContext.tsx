import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, User } from "@/api/client";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (code: string) => Promise<void>;
  logout: () => void;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const stored = localStorage.getItem("user");
    return stored ? JSON.parse(stored) : null;
  });
  const [loading, setLoading] = useState(false);

  const login = async (code: string) => {
    setLoading(true);
    try {
      const response = await api.post<{
        access_token: string;
        user_id: string;
        email: string;
        display_name: string;
        roles: string[];
      }>("/auth/google", { code });

      api.setToken(response.access_token);

      // Fetch full user info
      const userInfo = await api.get<User>("/users/me");
      setUser(userInfo);
      localStorage.setItem("user", JSON.stringify(userInfo));
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    api.clearToken();
    setUser(null);
  };

  const hasRole = (role: string) => {
    if (!user) return false;
    return user.roles.some((r) => r.name === role);
  };

  // Verify token on mount
  useEffect(() => {
    const token = api.getToken();
    if (token && !user) {
      api.get<User>("/users/me")
        .then((u) => {
          setUser(u);
          localStorage.setItem("user", JSON.stringify(u));
        })
        .catch(() => {
          api.clearToken();
          setUser(null);
        });
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
