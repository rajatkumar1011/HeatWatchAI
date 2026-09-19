import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Button, Card, PageHeader, useToast } from "../components/ui";
import { formatTime } from "../utils/format";
import { LogoutIcon, ShieldIcon, UserIcon } from "../components/icons";

export function ProfilePage() {
  const { user, refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [email, setEmail] = useState(user?.email ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user?.email) setEmail(user.email);
  }, [user]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = {};
      if (email !== user?.email) body.email = email;
      if (newPassword) {
        body.current_password = currentPassword;
        body.new_password = newPassword;
      }
      await api.put("/auth/me", body);
      await refreshUser();
      toast("success", "Profile updated.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="User Profile" description="Manage your HeatWatch AI account details and credentials." />

      <div className="space-y-4">
        <Card title="Account">
          <div className="flex items-center gap-4">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-navy text-lg font-bold text-white">
              {user?.username?.slice(0, 2).toUpperCase()}
            </span>
            <dl className="grid flex-1 grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">Username</dt>
                <dd className="font-semibold text-slate-800">{user?.username}</dd>
              </div>
              <div>
                <dt className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">Role</dt>
                <dd className="font-semibold text-slate-800">{user?.role_label}</dd>
              </div>
              <div>
                <dt className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">Member since</dt>
                <dd className="tnum text-slate-600">{formatTime(user?.created_at)}</dd>
              </div>
              <div>
                <dt className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">Last login</dt>
                <dd className="tnum text-slate-600">{formatTime(user?.last_login_at)}</dd>
              </div>
            </dl>
          </div>
          <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
            <ShieldIcon className="h-3.5 w-3.5 shrink-0 text-slate-400" />
            Roles are assigned by administrators — public registration always creates researcher accounts.
          </p>
        </Card>

        <Card title="Update details">
          <div className="space-y-3.5">
            <div>
              <label htmlFor="profile-email" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                Email address
              </label>
              <input
                id="profile-email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand focus:outline-none"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label htmlFor="profile-current" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                  Current password
                </label>
                <input
                  id="profile-current"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  autoComplete="current-password"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="profile-new" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                  New password
                </label>
                <input
                  id="profile-new"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand focus:outline-none"
                />
              </div>
            </div>
            {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
            <div className="flex gap-2">
              <Button onClick={save} disabled={busy} icon={<UserIcon className="h-4 w-4" />}>
                {busy ? "Saving…" : "Save changes"}
              </Button>
              <Button
                variant="subtle-danger"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
                icon={<LogoutIcon className="h-4 w-4" />}
              >
                Sign out
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
