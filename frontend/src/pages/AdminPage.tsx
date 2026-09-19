import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  PageHeader,
  Pill,
  Skeleton,
  Tabs,
  useToast,
} from "../components/ui";
import { formatTime } from "../utils/format";
import { DatabaseIcon, SearchIcon, ShieldIcon } from "../components/icons";

type Tab = "users" | "config" | "providers" | "logs" | "data";

interface AdminUserRow {
  id: number;
  username: string;
  email: string;
  role: string;
  role_label: string;
  is_active: boolean;
  is_demo: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

const ROLES = [
  { value: "admin", label: "System Administrator" },
  { value: "officer", label: "Disaster Management Officer" },
  { value: "authority", label: "Government Authority" },
  { value: "researcher", label: "Environmental Researcher" },
];

export function AdminPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("users");
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [search, setSearch] = useState("");
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [health, setHealth] = useState<Record<string, any> | null>(null);
  const [stats, setStats] = useState<Record<string, any> | null>(null);
  const [modelStatus, setModelStatus] = useState<Record<string, any> | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [logCategory, setLogCategory] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // pending destructive action
  const [confirm, setConfirm] = useState<{
    title: string;
    body: string;
    confirmLabel?: string;
    danger?: boolean;
    action: () => Promise<void>;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === "users") {
        const r = await api.get(`/admin/users?search=${encodeURIComponent(search)}&per_page=50`);
        setUsers(r.data.data);
      } else if (tab === "config") {
        const r = await api.get("/admin/settings");
        setSettings(r.data.data);
      } else if (tab === "providers") {
        const [h, m] = await Promise.all([api.get("/health/detailed"), api.get("/admin/model-status")]);
        setHealth(h.data.data);
        setModelStatus(m.data.data);
      } else if (tab === "logs") {
        const r = await api.get(`/admin/logs?per_page=60${logCategory ? `&category=${logCategory}` : ""}`);
        setLogs(r.data.data);
      } else if (tab === "data") {
        const s = await api.get("/admin/data-stats");
        setStats(s.data.data);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [tab, search, logCategory]);

  useEffect(() => {
    load();
  }, [load]);

  const updateUser = async (id: number, body: Record<string, unknown>, successMsg: string) => {
    setError(null);
    try {
      await api.put(`/admin/users/${id}`, body);
      toast("success", successMsg);
      await load();
    } catch (err) {
      toast("error", errorMessage(err));
    }
  };

  const saveSettings = async (key: string, value: unknown) => {
    setError(null);
    try {
      await api.put("/admin/settings", { [key]: value });
      toast("success", `Saved ${key.replace(/_/g, " ")}.`);
      await load();
    } catch (err) {
      toast("error", errorMessage(err));
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "users", label: "User management" },
    { id: "config", label: "System configuration" },
    { id: "providers", label: "Providers & model" },
    { id: "logs", label: "System logs" },
    { id: "data", label: "Data status" },
  ];

  return (
    <div>
      <PageHeader
        title="Administration"
        description="Restricted to authorised administrators. Every change is validated by the backend and recorded in the audit log."
      >
        <Pill text="RBAC ENFORCED" className="border-slate-200 bg-slate-50 text-slate-500" />
      </PageHeader>

      <div className="mb-4">
        <Tabs tabs={tabs} active={tab} onChange={setTab} />
      </div>

      {error && (
        <div className="mb-3">
          <ErrorState message={error} onRetry={load} />
        </div>
      )}

      {loading && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-11 w-full rounded-xl" />
          ))}
        </div>
      )}

      {/* ---------------------------------------------------------- Users */}
      {!loading && tab === "users" && (
        <Card title="Registered users" bodyClassName="p-0">
          <div className="border-b border-slate-100 p-3.5">
            <div className="relative w-full max-w-xs">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                placeholder="Search username or email…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search users"
                className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-8.5 pr-3 text-sm shadow-sm focus:border-brand focus:outline-none"
                style={{ paddingLeft: 34 }}
              />
            </div>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-slate-50/95 text-[10.5px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-3.5 py-2.5 font-semibold">User</th>
                  <th className="px-3.5 py-2.5 font-semibold">Role</th>
                  <th className="px-3.5 py-2.5 font-semibold">Status</th>
                  <th className="px-3.5 py-2.5 font-semibold">Last login</th>
                  <th className="px-3.5 py-2.5 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((u) => (
                  <tr key={u.id} className="transition-colors hover:bg-slate-50/80">
                    <td className="px-3.5 py-2.5">
                      <p className="flex items-center gap-2 font-semibold text-slate-800">
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-500">
                          {u.username.slice(0, 2).toUpperCase()}
                        </span>
                        {u.username}
                        {u.id === user?.id && <span className="text-[11px] font-normal text-slate-400">(you)</span>}
                        {u.is_demo && <Pill text="DEMO" className="border-violet-200 bg-violet-50 text-violet-600" />}
                      </p>
                      <p className="mt-0.5 pl-9 text-xs text-slate-400">{u.email}</p>
                    </td>
                    <td className="px-3.5 py-2.5">
                      <select
                        value={u.role}
                        onChange={(e) =>
                          updateUser(u.id, { role: e.target.value }, `${u.username} role updated to ${e.target.value}.`)
                        }
                        aria-label={`Role for ${u.username}`}
                        className="max-w-[190px] rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs font-semibold text-slate-700 shadow-sm focus:border-brand focus:outline-none"
                      >
                        {ROLES.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3.5 py-2.5">
                      <Pill
                        text={u.is_active ? "ACTIVE" : "DEACTIVATED"}
                        className={
                          u.is_active
                            ? "border-green-200 bg-green-50 text-green-700"
                            : "border-slate-200 bg-slate-100 text-slate-500"
                        }
                        dot={u.is_active ? "bg-green-500" : "bg-slate-400"}
                      />
                    </td>
                    <td className="tnum whitespace-nowrap px-3.5 py-2.5 text-slate-600">{formatTime(u.last_login_at)}</td>
                    <td className="px-3.5 py-2.5 text-right">
                      <Button
                        variant="subtle-danger"
                        small
                        onClick={() => {
                          const target = u.username;
                          setConfirm({
                            title: u.is_active ? "Deactivate account?" : "Reactivate account?",
                            body: u.is_active
                              ? `${target} will no longer be able to sign in. Their data is retained and the account can be reactivated.`
                              : `${target} will be able to sign in again.`,
                            confirmLabel: u.is_active ? "Deactivate" : "Reactivate",
                            danger: u.is_active,
                            action: async () => {
                              await updateUser(
                                u.id,
                                { is_active: !u.is_active },
                                `${target} ${u.is_active ? "deactivated" : "reactivated"}.`,
                              );
                            },
                          });
                        }}
                      >
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-slate-100 px-3.5 py-2.5 text-[11px] text-slate-400">
            The backend prevents deactivating or demoting the last active administrator.
          </p>
        </Card>
      )}

      {/* ------------------------------------------------------ Config */}
      {!loading && tab === "config" && settings && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card title="Alert thresholds" subtitle="Applied to new predictions immediately">
            <div className="space-y-3">
              {[
                { key: "alert_high_threshold", label: "High risk threshold (0–100)", type: "number" },
                { key: "alert_moderate_threshold", label: "Moderate risk threshold", type: "number" },
                { key: "alert_cooldown_minutes", label: "Alert cooldown (minutes)", type: "number" },
                { key: "alert_on_moderate", label: "Also alert on moderate risk", type: "bool" },
                { key: "alerts_enabled", label: "Alerts enabled", type: "bool" },
              ].map((f) => (
                <SettingRow key={f.key} field={f} value={settings[f.key]} onSave={saveSettings} />
              ))}
            </div>
          </Card>
          <Card title="Data collection" subtitle="Scheduler picks changes up on its next cycle">
            <div className="space-y-3">
              {[
                { key: "weather_collection_minutes", label: "Weather collection interval (minutes)", type: "number" },
                { key: "social_collection_minutes", label: "Social collection interval (minutes)", type: "number" },
              ].map((f) => (
                <SettingRow key={f.key} field={f} value={settings[f.key]} onSave={saveSettings} />
              ))}
              <KeywordEditor
                label="Social collection keywords"
                keywords={settings["social_keywords"] as string[] | undefined}
                onSave={(v) => saveSettings("social_keywords", v)}
              />
            </div>
          </Card>
        </div>
      )}

      {/* ---------------------------------------------------- Providers */}
      {!loading && tab === "providers" && health && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card title="Integration status" subtitle="Live providers require external credentials">
            <ul className="space-y-3 text-sm">
              <li className="flex items-center justify-between gap-3">
                <span className="text-slate-600">Database</span>
                <span className={`tnum font-semibold ${health.database.ok ? "text-green-700" : "text-red-600"}`}>
                  {health.database.ok ? "Connected" : "Down"} · {health.database.engine}
                </span>
              </li>
              <li className="flex items-center justify-between gap-3">
                <span className="text-slate-600">Weather provider</span>
                <span className="font-semibold text-slate-800">
                  {health.providers.weather.active_provider}{" "}
                  <Pill
                    text={health.providers.weather.configured ? "CONFIGURED" : "NOT CONFIGURED"}
                    className={
                      health.providers.weather.configured
                        ? "border-green-200 bg-green-50 text-green-700"
                        : "border-slate-200 bg-slate-100 text-slate-500"
                    }
                  />
                </span>
              </li>
              <li className="flex items-center justify-between gap-3">
                <span className="text-slate-600">Social provider</span>
                <span className="font-semibold text-slate-800">
                  {health.providers.social.active_provider} · requested: {health.providers.social.requested}
                </span>
              </li>
              <li className="flex items-center justify-between gap-3">
                <span className="text-slate-600">Operational mode</span>
                <span className="font-bold uppercase text-slate-800">{health.data_mode}</span>
              </li>
            </ul>
            <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
              Without credentials the clearly-labelled demonstration providers are used. Live outages surface cached data
              with a stale indicator — synthetic data is never substituted silently.
            </p>
          </Card>
          {modelStatus && (
            <Card title="Severity model" subtitle="Registered artifact & evaluation">
              <p className="text-sm">
                Status:{" "}
                <b className={modelStatus.severity_model.loaded ? "text-green-700" : "text-amber-700"}>
                  {modelStatus.severity_model.loaded ? "loaded" : "rule-based fallback"}
                </b>{" "}
                · version <b>{modelStatus.severity_model.version}</b>
              </p>
              {modelStatus.severity_model.evaluation && (
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  {Object.entries(modelStatus.severity_model.evaluation)
                    .filter(([k, v]) => typeof v === "number")
                    .map(([k, v]) => (
                      <div key={k} className="rounded-lg bg-slate-50 px-2.5 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          {k.replace(/_/g, " ")}
                        </p>
                        <p className="tnum mt-0.5 text-sm font-bold text-slate-800">{String(v)}</p>
                      </div>
                    ))}
                </div>
              )}
              <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                <p className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">Documented limitations</p>
                <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-slate-500">
                  {(modelStatus.severity_model.limitations ?? []).map((l: string, i: number) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* --------------------------------------------------------- Logs */}
      {!loading && tab === "logs" && (
        <Card title="Operational logs" subtitle="Structured system events (system_logs)" bodyClassName="p-0">
          <div className="flex flex-wrap gap-1.5 border-b border-slate-100 p-3">
            {["", "auth", "weather", "social", "sentiment", "prediction", "alert", "report", "admin", "system", "scheduler"].map((c) => (
              <button
                key={c || "all"}
                onClick={() => setLogCategory(c)}
                className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                  logCategory === c ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {c || "all"}
              </button>
            ))}
          </div>
          {logs.length === 0 ? (
            <div className="p-4">
              <EmptyState compact title="No log entries for this filter" />
            </div>
          ) : (
            <ul className="max-h-[480px] space-y-1 overflow-y-auto p-3 font-mono text-[11.5px]">
              {logs.map((l) => (
                <li key={l.id} className="rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2">
                  <span
                    className={`font-bold ${
                      l.level === "error" ? "text-red-600" : l.level === "warning" ? "text-amber-600" : "text-slate-500"
                    }`}
                  >
                    [{l.level}]
                  </span>{" "}
                  <span className="text-slate-400">{formatTime(l.created_at, true)}</span>{" "}
                  <span className="font-semibold text-slate-700">{l.category}</span>
                  <span className="text-slate-600"> — {l.message}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* --------------------------------------------------------- Data */}
      {!loading && tab === "data" && stats && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {Object.entries(stats.counts).map(([k, v]) => (
              <div key={k} className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-card">
                <p className="tnum text-2xl font-semibold tracking-tight text-slate-900">{String(v)}</p>
                <p className="mt-0.5 text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                  {k.replace(/_/g, " ")}
                </p>
              </div>
            ))}
          </div>
          <Card
            title={
              <span className="inline-flex items-center gap-1.5">
                <DatabaseIcon className="h-3.5 w-3.5 text-slate-400" /> Records by data mode
              </span>
            }
            subtitle="Provenance accounting for every stored record"
          >
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(stats.by_data_mode).map(([k, v]) => (
                <span key={k} className="tnum rounded-full border border-slate-200 bg-slate-50 px-3 py-1 font-semibold text-slate-700">
                  {k.replace("_", ": ")} — {String(v)}
                </span>
              ))}
            </div>
          </Card>
        </div>
      )}

      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.title ?? ""}
        body={confirm?.body ?? ""}
        confirmLabel={confirm?.confirmLabel}
        danger={confirm?.danger}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          const action = confirm?.action;
          setConfirm(null);
          if (action) await action();
        }}
      />
    </div>
  );
}

function SettingRow({
  field,
  value,
  onSave,
}: {
  field: { key: string; label: string; type: string };
  value: unknown;
  onSave: (k: string, v: unknown) => void;
}) {
  const [draft, setDraft] = useState<string>(String(value ?? ""));
  useEffect(() => setDraft(String(value ?? "")), [value]);
  return (
    <div className="flex items-center justify-between gap-3">
      <label className="text-sm text-slate-600">{field.label}</label>
      {field.type === "bool" ? (
        <input
          type="checkbox"
          checked={value === true}
          onChange={(e) => onSave(field.key, e.target.checked)}
          aria-label={field.label}
          className="h-5 w-5 accent-brand"
        />
      ) : (
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label={field.label}
            className="tnum w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-sm shadow-sm focus:border-brand focus:outline-none"
          />
          <button
            onClick={() => onSave(field.key, Number(draft))}
            className="rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-bold text-white transition-colors hover:bg-slate-700"
          >
            Save
          </button>
        </div>
      )}
    </div>
  );
}

function KeywordEditor({
  label,
  keywords,
  onSave,
}: {
  label: string;
  keywords?: string[];
  onSave: (v: string[]) => void;
}) {
  const [text, setText] = useState((keywords ?? []).join(", "));
  useEffect(() => setText((keywords ?? []).join(", ")), [keywords]);
  return (
    <div>
      <label className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">{label}</label>
      <textarea
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label={label}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand focus:outline-none"
        placeholder="heatwave, extreme heat, dehydration…"
      />
      <button
        onClick={() => onSave(text.split(",").map((k) => k.trim()).filter(Boolean))}
        className="mt-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-slate-700"
      >
        Save keywords
      </button>
    </div>
  );
}
