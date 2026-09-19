import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { errorMessage } from "../api/client";
import { Button } from "../components/ui";

export function BrandMark({ size = "lg" }: { size?: "lg" | "sm" }) {
  const dim = size === "lg" ? "h-14 w-14" : "h-10 w-10";
  return (
    <div className={`flex ${dim} items-center justify-center rounded-2xl bg-brand text-white shadow-lg`}>
      <svg className={size === "lg" ? "h-8 w-8" : "h-6 w-6"} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.362 5.214A8.252 8.252 0 0112 21 8.25 8.25 0 016.038 7.048 8.287 8.287 0 009 9.6a8.983 8.983 0 013.361-6.867 8.21 8.21 0 003 2.48z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18a3.75 3.75 0 00.495-7.467 5.99 5.99 0 00-1.925 3.546 5.974 5.974 0 01-2.133-1A3.75 3.75 0 0012 18z" />
      </svg>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(identifier, password);
      navigate("/dashboard");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy p-6">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute -left-32 -top-32 h-96 w-96 rounded-full bg-brand/10 blur-3xl" />
        <div className="absolute -bottom-40 -right-24 h-[28rem] w-[28rem] rounded-full bg-sky-500/5 blur-3xl" />
      </div>
      <div className="relative w-full max-w-md rounded-2xl border border-slate-200/60 bg-white p-8 shadow-pop">
        <div className="mb-6 flex flex-col items-center text-center">
          <BrandMark />
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">HeatWatch AI</h1>
          <p className="mt-1 text-sm leading-relaxed text-slate-500">
            AI-Based Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning
          </p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="identifier" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
              Username or email
            </label>
            <input
              id="identifier"
              type="text"
              required
              autoComplete="username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm transition-colors focus:border-brand focus:outline-none"
              placeholder="e.g. admin"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm transition-colors focus:border-brand focus:outline-none"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-relaxed text-red-700">
              {error}
            </p>
          )}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-slate-500">
          Need an account?{" "}
          <Link to="/register" className="font-semibold text-brand hover:underline">
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await register(form.username, form.email, form.password, form.confirm);
      navigate("/login?registered=1");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy p-6">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute -left-32 -top-32 h-96 w-96 rounded-full bg-brand/10 blur-3xl" />
      </div>
      <div className="relative w-full max-w-md rounded-2xl border border-slate-200/60 bg-white p-8 shadow-pop">
        <div className="mb-6 flex flex-col items-center text-center">
          <BrandMark size="sm" />
          <h1 className="mt-3 text-xl font-semibold tracking-tight text-slate-900">Create your HeatWatch AI account</h1>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            New accounts are created with researcher-level access. Administrative roles are assigned by system administrators.
          </p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          {[
            { id: "username", label: "Username", type: "text", hint: "3–64 characters: letters, digits, . _ -" },
            { id: "email", label: "Email address", type: "email", hint: "" },
            { id: "password", label: "Password", type: "password", hint: "Minimum 8 characters with letters and numbers" },
            { id: "confirm", label: "Confirm password", type: "password", hint: "" },
          ].map((f) => (
            <div key={f.id}>
              <label htmlFor={f.id} className="mb-1 block text-xs font-bold uppercase tracking-wide text-slate-500">
                {f.label}
              </label>
              <input
                id={f.id}
                type={f.type}
                required
                value={form[f.id as keyof typeof form]}
                onChange={set(f.id as keyof typeof form)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand focus:outline-none"
              />
              {f.hint && <p className="mt-1 text-[11px] text-slate-400">{f.hint}</p>}
            </div>
          ))}
          {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Creating account…" : "Register"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-slate-500">
          Already registered?{" "}
          <Link to="/login" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
