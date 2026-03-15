import { useState } from "react";
import { useAuth } from "./AuthContext";
import { useNavigate } from "react-router-dom";
import { GoogleOAuthProvider, useGoogleLogin } from "@react-oauth/google";

function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function LogoMark() {
  return (
    <svg
      width="48"
      height="48"
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="mx-auto mb-4"
    >
      <rect width="48" height="48" rx="12" fill="#0D4994" />
      <path
        d="M24 12C17.373 12 12 17.373 12 24C12 28.418 14.578 32.242 18.348 34.125V36.75C18.348 37.44 18.908 38 19.598 38H28.402C29.092 38 29.652 37.44 29.652 36.75V34.125C33.422 32.242 36 28.418 36 24C36 17.373 30.627 12 24 12Z"
        fill="white"
        opacity="0.95"
      />
      <circle cx="24" cy="23" r="4" fill="#0D4994" />
    </svg>
  );
}

function GoogleLoginButton({ onSuccess, onError }: { onSuccess: (code: string) => void; onError: () => void }) {
  const googleLogin = useGoogleLogin({
    flow: "auth-code",
    onSuccess: (response) => onSuccess(response.code),
    onError: () => onError(),
  });

  return (
    <button
      onClick={() => googleLogin()}
      className="w-full flex items-center justify-center gap-3 bg-white text-gray-700 border border-gray-300 py-3 px-4 rounded-md font-medium hover:bg-gray-50 transition-colors shadow-sm"
    >
      <GoogleIcon />
      Sign in with Google
    </button>
  );
}

export function LoginPage() {
  const { login, user, authConfig } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [loggingIn, setLoggingIn] = useState(false);

  if (user) {
    navigate("/");
    return null;
  }

  const handleGoogleSuccess = async (code: string) => {
    setError(null);
    setLoggingIn(true);
    try {
      await login(code);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Google login failed");
    } finally {
      setLoggingIn(false);
    }
  };

  const handleDevLogin = async (email?: string) => {
    setError(null);
    setLoggingIn(true);
    try {
      await login("test", email);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Dev login failed");
    } finally {
      setLoggingIn(false);
    }
  };

  const seedUsers = [
    { email: "admin@example.com", label: "Alex Admin", roles: "Admin + Author" },
    { email: "author@example.com", label: "Jordan Author", roles: "Author" },
    { email: "respondent1@example.com", label: "Sam Respondent", roles: "Respondent" },
    { email: "respondent2@example.com", label: "Taylor Respondent", roles: "Respondent" },
    { email: "reviewer@example.com", label: "Casey Reviewer", roles: "Reviewer" },
    { email: "respondent-reviewer@example.com", label: "Riley Test", roles: "Respondent + Reviewer" },
  ];

  const googleClientId = authConfig?.google_client_id;
  const devLoginEnabled = authConfig?.dev_login_enabled ?? !googleClientId;

  return (
    <div
      className="flex items-center justify-center min-h-screen bg-muted"
      style={{
        backgroundImage:
          "radial-gradient(circle, #d4d4d4 1px, transparent 1px)",
        backgroundSize: "24px 24px",
      }}
    >
      <div className="bg-background p-8 rounded-lg shadow-lg max-w-md w-full text-center">
        <LogoMark />
        <h1 className="text-2xl font-bold mb-2">Knowledge Elicitation Platform</h1>
        <p className="text-muted-foreground mb-8">
          Sign in to contribute to organizational knowledge
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-md text-sm">
            {error}
          </div>
        )}

        <div className="space-y-3">
          {googleClientId && (
            <GoogleOAuthProvider clientId={googleClientId}>
              <GoogleLoginButton
                onSuccess={handleGoogleSuccess}
                onError={() => setError("Google login was cancelled or failed")}
              />
            </GoogleOAuthProvider>
          )}

          {devLoginEnabled && (
            <>
              {googleClientId && (
                <div className="flex items-center gap-3 my-2">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-xs text-muted-foreground">or</span>
                  <div className="flex-1 h-px bg-border" />
                </div>
              )}
              <button
                onClick={() => handleDevLogin()}
                disabled={loggingIn}
                className="w-full bg-secondary text-secondary-foreground py-3 px-4 rounded-md font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {loggingIn ? "Signing in..." : "Sign in as Test User (all roles)"}
              </button>
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-xs text-muted-foreground mb-2">Or sign in as a seed user:</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {seedUsers.map((u) => (
                    <button
                      key={u.email}
                      onClick={() => handleDevLogin(u.email)}
                      disabled={loggingIn}
                      className="text-left px-2.5 py-1.5 rounded border border-border text-xs hover:bg-muted transition-colors disabled:opacity-50"
                    >
                      <span className="font-medium block truncate">{u.label}</span>
                      <span className="text-muted-foreground">{u.roles}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {!authConfig && (
            <div className="text-muted-foreground text-sm">Loading...</div>
          )}
        </div>
      </div>
    </div>
  );
}
