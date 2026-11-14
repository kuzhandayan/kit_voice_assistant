import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { isSignedIn, useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { me, login } = useAuth();
  const navigate = useNavigate();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (isSignedIn(me)) return <Navigate to="/assistant" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(loginId, password);
      navigate("/assistant");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="login">
      <h1>Log in</h1>
      <p className="muted">Students and teachers sign in with their college login to check attendance, apply for leave and more.</p>
      <form onSubmit={submit} className="form">
        <label>
          Login ID
          <input value={loginId} onChange={(e) => setLoginId(e.target.value)} autoComplete="username" required autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn" disabled={busy}>
          {busy ? "Logging in…" : "Log in"}
        </button>
      </form>
    </section>
  );
}
