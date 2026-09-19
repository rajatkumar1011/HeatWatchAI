import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { Alert, Location } from "../types";
import { Button, Card, EmptyState, ErrorState, PageHeader, SegmentedControl, Select, Skeleton, useToast } from "../components/ui";
import { RiskBadge } from "../components/Risk";
import { BellIcon, CheckIcon, ChevronDownIcon } from "../components/icons";
import { formatTime, relativeTime } from "../utils/format";

type StatusFilter = "active" | "acknowledged" | "resolved" | "any";

export function AlertsPage() {
  const toast = useToast();
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | "all">("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<{ data: Location[] }>("/locations?monitored=true")
      .then((r) => setLocations(r.data.data))
      .catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (locationId !== "all") params.set("location_id", String(locationId));
      if (statusFilter !== "any") params.set("status", statusFilter);
      const r = await api.get(`/alerts?${params.toString()}`);
      setAlerts(r.data.data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [locationId, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const acknowledge = async (id: number) => {
    setBusyId(id);
    try {
      await api.post(`/alerts/${id}/acknowledge`);
      toast("success", `Alert #${id} acknowledged.`);
      await load();
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const accent = (a: Alert) =>
    a.risk_level === "high" ? "bg-red-600" : a.risk_level === "moderate" ? "bg-amber-500" : "bg-green-600";

  const statusChip = (a: Alert) => {
    if (a.status === "active") return { text: "ACTIVE", cls: "border-red-200 bg-red-50 text-red-700" };
    if (a.status === "acknowledged") return { text: "ACKNOWLEDGED", cls: "border-sky-200 bg-sky-50 text-sky-700" };
    return { text: "RESOLVED", cls: "border-slate-200 bg-slate-50 text-slate-500" };
  };

  return (
    <div>
      <PageHeader
        title="Alerts"
        description="Application-generated early warnings with cooldown and escalation policy. HeatWatch AI alerts are distinct from official government advisories."
      >
        <div className="w-48">
          <Select
            ariaLabel="Location filter"
            value={String(locationId)}
            onChange={(v) => setLocationId(v === "all" ? "all" : Number(v))}
            options={[{ value: "all", label: "All locations" }, ...locations.map((l) => ({ value: l.id, label: l.display_name }))]}
          />
        </div>
      </PageHeader>

      <div className="mb-3">
        <SegmentedControl
          ariaLabel="Status filter"
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { value: "active", label: "Active" },
            { value: "acknowledged", label: "Acknowledged" },
            { value: "resolved", label: "Resolved" },
            { value: "any", label: "All" },
          ]}
        />
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : alerts.length === 0 ? (
        <Card>
          <EmptyState
            title="No alerts found"
            hint={
              statusFilter === "active"
                ? "No active heatwave alerts — risk is currently below the configured thresholds."
                : "No alerts match the current filters."
            }
            action={
              <Button small variant="secondary" onClick={() => setStatusFilter("any")}>
                Show all alerts
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {alerts.map((a) => {
            const chip = statusChip(a);
            const isOpen = expanded === a.id;
            return (
              <article
                key={a.id}
                className={`overflow-hidden rounded-xl border bg-white shadow-card transition-colors ${
                  a.status === "active" && a.risk_level === "high" ? "border-red-200" : "border-slate-200/80"
                }`}
              >
                <div className="flex items-center gap-3 px-4 py-3">
                  <span aria-hidden className={`h-9 w-1 shrink-0 rounded-full ${accent(a)}`} />
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
                    <BellIcon className="h-4 w-4" />
                  </div>
                  <button
                    onClick={() => setExpanded(isOpen ? null : a.id)}
                    aria-expanded={isOpen}
                    className="flex min-w-0 flex-1 flex-col items-start text-left"
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <RiskBadge category={a.risk_level} score={a.severity_score} />
                      <span className="text-sm font-semibold text-slate-800">
                        {a.location_name ?? `Location #${a.location_id}`}
                      </span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${chip.cls}`}>
                        {chip.text}
                      </span>
                    </span>
                    <span className="tnum mt-0.5 truncate text-xs text-slate-400">
                      {formatTime(a.generated_at)} · {relativeTime(a.generated_at)}
                      {a.data_mode === "demo" && " · demo data"}
                    </span>
                  </button>
                  {a.status === "active" ? (
                    <Button
                      variant="secondary"
                      small
                      disabled={busyId === a.id}
                      onClick={() => acknowledge(a.id)}
                      icon={<CheckIcon className="h-3.5 w-3.5" />}
                    >
                      {busyId === a.id ? "…" : "Acknowledge"}
                    </Button>
                  ) : (
                    <button
                      onClick={() => setExpanded(isOpen ? null : a.id)}
                      aria-label="Toggle alert details"
                      className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    >
                      <ChevronDownIcon className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                    </button>
                  )}
                </div>
                {isOpen && (
                  <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3 text-xs leading-relaxed text-slate-600">
                    <p>
                      <span className="font-semibold text-slate-700">Trigger:</span> {a.triggered_by}
                    </p>
                    <p className="mt-1">
                      <span className="font-semibold text-slate-700">Message:</span> {a.message}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-400">
                      Alert #{a.id} · linked prediction {a.prediction_id ?? "—"} · generated {formatTime(a.generated_at, true)}
                      {a.acknowledged_at && ` · acknowledged ${formatTime(a.acknowledged_at, true)}`}
                      {a.resolved_at && ` · resolved ${formatTime(a.resolved_at, true)}`}
                    </p>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
