import { useAuth } from "./AuthContext";
import { useNavigate } from "react-router-dom";

export function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();

  if (user) {
    navigate("/");
    return null;
  }

  const handleGoogleLogin = () => {
    // In production, this would redirect to Google OAuth
    // For development, you can use the API directly with a test code
    const code = prompt("Enter Google OAuth code (or 'test' for dev mode):");
    if (code) {
      login(code)
        .then(() => navigate("/"))
        .catch((err) => alert("Login failed: " + err.message));
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-muted">
      <div className="bg-background p-8 rounded-lg shadow-lg max-w-md w-full text-center">
        <h1 className="text-2xl font-bold mb-2">Knowledge Elicitation Platform</h1>
        <p className="text-muted-foreground mb-8">
          Sign in to contribute to organizational knowledge
        </p>
        <button
          onClick={handleGoogleLogin}
          className="w-full bg-primary text-primary-foreground py-3 px-4 rounded-md font-medium hover:opacity-90 transition-opacity"
        >
          Sign in with Google
        </button>
      </div>
    </div>
  );
}
