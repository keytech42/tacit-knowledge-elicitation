import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, User } from "@/api/client";

interface AuthConfig {
  google_client_id: string;
  dev_login_enabled: boolean;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  authConfig: AuthConfig | null;
  login: (code: string) => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
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
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);

  // Fetch auth config on mount
  useEffect(() => {
    api.get<AuthConfig>("/auth/config").then(setAuthConfig).catch(() => {});
  }, []);

  const loginWithToken = async (token: string) => {
    api.setToken(token);
    const userInfo = await api.get<User>("/users/me");
    setUser(userInfo);
    localStorage.setItem("user", JSON.stringify(userInfo));
  };

  const login = async (code: string) => {
    setLoading(true);
    try {
      const endpoint = code === "test" ? "/auth/dev-login" : "/auth/google";
      const body = code === "test" ? undefined : { code };
      const response = await api.post<{
        access_token: string;
        user_id: string;
        email: string;
        display_name: string;
        roles: string[];
      }>(endpoint, body);

      await loginWithToken(response.access_token);
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

  // Refresh user profile on mount — picks up role changes without re-login
  useEffect(() => {
    const token = api.getToken();
    if (token) {
      api.get<User>("/users/me")
        .then((u) => {
          setUser(u);
          localStorage.setItem("user", JSON.stringify(u));
        })
        .catch(() => {
          api.clearToken();
          setUser(null);
          localStorage.removeItem("user");
        });
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, authConfig, login, loginWithToken, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
