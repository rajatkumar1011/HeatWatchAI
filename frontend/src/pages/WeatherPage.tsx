import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { Location, WeatherObservation } from "../types";
import { Button, Card, EmptyState, ErrorState, PageHeader, Pill, Select, Skeleton, useToast } from "../components/ui";
import { StatusPill } from "../components/Risk";
import { CloudIcon, RefreshIcon, TempIcon, DropIcon, HeatIcon, WindIcon } from "../components/icons";
import { formatTime, modePill, relativeTime } from "../utils/format";

type SortKey = "observed_at" | "temperature_c" | "humidity_pct" | "heat_index_c" | "wind_speed_kph";

export function WeatherPage() {
  const toast = useToast();
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [rows, setRows] = useState<WeatherObservation[]>([]);
  const [latest, setLatest] = useState<(WeatherObservation & { available?: boolean }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("observed_at");
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    api
      .get<{ data: Location[] }>("/locations?monitored=true")
      .then((r) => {
        setLocations(r.data.data);
        if (r.data.data.length) setLocationId(r.data.data[0].id);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const load = useCallback(async () => {
    if (!locationId) return;
    setLoading(true);
    try {
      const start = new Date(Date.now() - 3 * 864e5).toISOString().slice(0, 10);
      const [hist, cur] = await Promise.all([
        api.get(`/weather/history?location_id=${locationId}&start=${start}`),
        api.get(`/weather/current?location_id=${locationId}`),
      ]);
      setRows(hist.data.data);
      setLatest(cur.data.data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [locationId]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    setBusy(true);
    try {
      await api.post("/weather/refresh", { location_id: locationId });
      await load();
      toast("success", "Weather data refreshed through the monitoring pipeline.");
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const sorted = useMemo(() => {
    const copy = [...rows].reverse();
    copy.sort((a, b) => {
      const av = a[sortKey] ?? (sortKey === "observed_at" ? "" : Number.NaN);
      const bv = b[sortKey] ?? (sortKey === "observed_at" ? "" : Number.NaN);
      const cmp =
        sortKey === "observed_at"
          ? new Date(String(av)).getTime() - new Date(String(bv)).getTime()
          : Number(av) - Number(bv);
      return sortAsc ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortAsc]);

  const columns: { key: SortKey | "condition" | "source"; label: string; numeric?: boolean; sortable?: boolean }[] = [
    { key: "observed_at", label: "Observed (IST)", sortable: true },
    { key: "temperature_c", label: "Temp °C", numeric: true, sortable: true },
    { key: "humidity_pct", label: "Humidity %", numeric: true, sortable: true },
    { key: "heat_index_c", label: "Heat idx °C", numeric: true, sortable: true },
    { key: "wind_speed_kph", label: "Wind km/h", numeric: true, sortable: true },
    { key: "condition", label: "Condition" },
    { key: "source", label: "Source" },
  ];

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((a) => !a);
    else {
      setSortKey(key);
      setSortAsc(key === "observed_at" ? false : true);
    }
  };

  const latestPill = latest && latest.available !== false ? modePill(latest.data_mode, latest.freshness) : null;

  return (
    <div>
      <PageHeader
        title="Weather Monitoring"
        description="Meteorological observations per location with provenance, freshness classification, and unit documentation (temperature °C · wind km/h · pressure hPa)."
      >
        <div className="w-48">
          <Select
            ariaLabel="Location"
            value={locationId ?? ""}
            onChange={(v) => setLocationId(Number(v))}
            options={locations.map((l) => ({ value: l.id, label: l.display_name }))}
          />
        </div>
        <Button
          variant="secondary"
          onClick={refresh}
          disabled={busy}
          icon={<RefreshIcon className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />}
        >
          Refresh
        </Button>
      </PageHeader>

      {/* Latest observation strip */}
      {latest && latest.available !== false ? (
        <div className="mb-4 grid grid-cols-2 gap-3 rounded-xl border border-slate-200/80 bg-white p-4 shadow-card md:grid-cols-5">
          {[
            { Icon: TempIcon, label: "Temperature", value: `${latest.temperature_c.toFixed(1)} °C` },
            { Icon: DropIcon, label: "Feels like", value: latest.feels_like_c != null ? `${latest.feels_like_c.toFixed(1)} °C` : "—" },
            { Icon: DropIcon, label: "Humidity", value: `${latest.humidity_pct.toFixed(0)} %` },
            { Icon: HeatIcon, label: "Heat index", value: latest.heat_index_c != null ? `${latest.heat_index_c.toFixed(1)} °C` : "N/A" },
            { Icon: WindIcon, label: "Wind", value: `${latest.wind_speed_kph.toFixed(0)} km/h` },
          ].map((m) => (
            <div key={m.label}>
              <p className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                <m.Icon className="h-3.5 w-3.5" /> {m.label}
              </p>
              <p className="tnum mt-1 text-lg font-semibold text-slate-900">{m.value}</p>
            </div>
          ))}
          <p className="col-span-2 text-[11px] text-slate-400 md:col-span-5">
            Observed {formatTime(latest.observed_at)} ({relativeTime(latest.observed_at)}) · provider {latest.provider}
            {latestPill && (
              <>
                {" · "}
                <StatusPill text={latestPill.text} className={latestPill.className} />
              </>
            )}
          </p>
        </div>
      ) : null}

      <Card
        title="Observation history"
        subtitle="Last 3 days · click a column header to sort"
        bodyClassName="p-0"
      >
        {loading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState message={error} onRetry={load} />
          </div>
        ) : sorted.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No observations stored" hint="Use Refresh to collect current conditions." />
          </div>
        ) : (
          <div className="max-h-[520px] overflow-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="sticky top-0 z-10 bg-slate-50/95 backdrop-blur text-[10.5px] uppercase tracking-wider text-slate-500">
                <tr>
                  {columns.map((c) => (
                    <th key={c.key} className={`px-3.5 py-2.5 font-semibold ${c.numeric ? "text-right" : ""}`}>
                      {c.sortable ? (
                        <button
                          onClick={() => toggleSort(c.key as SortKey)}
                          className="inline-flex items-center gap-1 hover:text-slate-800"
                          aria-label={`Sort by ${c.label}`}
                        >
                          {c.label}
                          <span className={sortKey === c.key ? "text-brand" : "text-slate-300"} aria-hidden>
                            {sortKey === c.key ? (sortAsc ? "▲" : "▼") : "↕"}
                          </span>
                        </button>
                      ) : (
                        c.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sorted.slice(0, 250).map((o) => {
                  const pill = modePill(o.data_mode, o.freshness);
                  return (
                    <tr key={o.id} className="transition-colors hover:bg-slate-50/80">
                      <td className="tnum whitespace-nowrap px-3.5 py-2 font-medium text-slate-700">
                        {formatTime(o.observed_at)}
                      </td>
                      <td className="tnum px-3.5 py-2 text-right text-slate-800">{o.temperature_c.toFixed(1)}</td>
                      <td className="tnum px-3.5 py-2 text-right text-slate-800">{o.humidity_pct.toFixed(0)}</td>
                      <td className="tnum px-3.5 py-2 text-right text-slate-800">
                        {o.heat_index_c != null ? (
                          o.heat_index_c.toFixed(1)
                        ) : (
                          <span className="text-slate-300">n/a</span>
                        )}
                      </td>
                      <td className="tnum px-3.5 py-2 text-right text-slate-800">{o.wind_speed_kph.toFixed(0)}</td>
                      <td className="px-3.5 py-2 text-slate-600">{o.condition_text}</td>
                      <td className="px-3.5 py-2">
                        {pill && <StatusPill text={pill.text} className={pill.className} />}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {sorted.length > 250 && (
              <p className="border-t border-slate-100 px-3.5 py-2 text-[11px] text-slate-400">
                Showing the 250 most recent of {sorted.length} observations. Use date-filtered reports for full exports.
              </p>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
