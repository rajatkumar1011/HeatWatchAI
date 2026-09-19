import { useCallback, useEffect, useState } from "react";
import { api, downloadFile, errorMessage } from "../api/client";
import type { Location, ReportRecord } from "../types";
import { Button, Card, EmptyState, PageHeader, Select, Skeleton, useToast } from "../components/ui";
import { DownloadIcon, DocIcon } from "../components/icons";
import { formatTime } from "../utils/format";

export function ReportsPage() {
  const toast = useToast();
  const [locations, setLocations] = useState<Location[]>([]);
  const [form, setForm] = useState({ locationId: "", start: "", end: "" });
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<{ data: Location[] }>("/locations")
      .then((r) => {
        setLocations(r.data.data);
        if (r.data.data.length) setForm((f) => ({ ...f, locationId: String(r.data.data[0].id) }));
      })
      .catch((err) => setError(errorMessage(err)));
    const weekAgo = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    const today = new Date().toISOString().slice(0, 10);
    setForm((f) => ({ ...f, start: f.start || weekAgo, end: f.end || today }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/reports?per_page=50");
      setReports(r.data.data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const generate = async (format: "pdf" | "csv") => {
    setBusy(true);
    try {
      const r = await api.post("/reports/generate", {
        location_id: Number(form.locationId),
        start_date: form.start,
        end_date: form.end,
        format,
      });
      await downloadFile(`/reports/${r.data.data.id}/download`);
      toast("success", `${format.toUpperCase()} report generated and downloaded.`);
      await load();
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Historical Reports"
        description="Branded PDF and CSV exports built from the actual database records for the selected location and period, including data provenance and methodology notes."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(280px,360px)_1fr]">
        {/* Parameter panel */}
        <Card title="New report" subtitle="Select filters, then choose a format">
          <div className="space-y-3.5">
            <div>
              <label htmlFor="report-location" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                Location
              </label>
              <Select
                ariaLabel="Report location"
                value={form.locationId}
                onChange={(v) => setForm((f) => ({ ...f, locationId: v }))}
                options={locations.map((l) => ({ value: l.id, label: l.display_name }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="report-start" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                  Start date
                </label>
                <input
                  id="report-start"
                  type="date"
                  value={form.start}
                  max={form.end}
                  onChange={(e) => setForm((f) => ({ ...f, start: e.target.value }))}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm shadow-sm focus:border-brand focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="report-end" className="mb-1 block text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                  End date
                </label>
                <input
                  id="report-end"
                  type="date"
                  value={form.end}
                  min={form.start}
                  onChange={(e) => setForm((f) => ({ ...f, end: e.target.value }))}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm shadow-sm focus:border-brand focus:outline-none"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 pt-1">
              <Button onClick={() => generate("pdf")} disabled={busy} icon={<DownloadIcon className="h-4 w-4" />}>
                PDF
              </Button>
              <Button variant="secondary" onClick={() => generate("csv")} disabled={busy} icon={<DownloadIcon className="h-4 w-4" />}>
                CSV
              </Button>
            </div>
            {error && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>
            )}
            <p className="text-[11px] leading-relaxed text-slate-400">
              Reports include weather statistics, risk analysis, sentiment summary, alerts, charts, and the exact
              methodology behind every number. Empty ranges are rejected with a clear message.
            </p>
          </div>
        </Card>

        {/* History */}
        <Card title="Generated reports" subtitle="Your reports; administrators see all" bodyClassName="p-0">
          {loading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-11 w-full" />
              ))}
            </div>
          ) : reports.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="No reports generated yet"
                hint="Choose a location and date range on the left, then download your first PDF or CSV report."
              />
            </div>
          ) : (
            <div className="max-h-[560px] overflow-auto">
              <table className="w-full text-left text-[13px]">
                <thead className="sticky top-0 bg-slate-50/95 text-[10.5px] uppercase tracking-wider text-slate-500 backdrop-blur">
                  <tr>
                    <th className="px-3.5 py-2.5 font-semibold">Report</th>
                    <th className="px-3.5 py-2.5 font-semibold">Period</th>
                    <th className="px-3.5 py-2.5 font-semibold">Generated</th>
                    <th className="px-3.5 py-2.5 font-semibold">Provenance</th>
                    <th className="px-3.5 py-2.5 text-right font-semibold">File</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {reports.map((r) => (
                    <tr key={r.id} className="transition-colors hover:bg-slate-50/80">
                      <td className="px-3.5 py-2.5">
                        <p className="flex items-center gap-2 font-semibold text-slate-800">
                          <DocIcon className="h-4 w-4 shrink-0 text-slate-400" />
                          {r.location_name}
                        </p>
                        <p className="mt-0.5 text-[11px] text-slate-400">
                          {r.format.toUpperCase()} · by {r.username ?? "—"}
                        </p>
                      </td>
                      <td className="tnum whitespace-nowrap px-3.5 py-2.5 text-slate-600">
                        {r.start_date} → {r.end_date}
                      </td>
                      <td className="tnum whitespace-nowrap px-3.5 py-2.5 text-slate-600">{formatTime(r.generated_at)}</td>
                      <td className="px-3.5 py-2.5">
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                            r.data_mode === "demo"
                              ? "border-violet-200 bg-violet-50 text-violet-700"
                              : "border-emerald-200 bg-emerald-50 text-emerald-700"
                          }`}
                        >
                          {r.data_mode}
                        </span>
                      </td>
                      <td className="px-3.5 py-2.5 text-right">
                        <button
                          onClick={() => downloadFile(`/reports/${r.id}/download`).catch((err) => toast("error", errorMessage(err)))}
                          className="text-xs font-bold text-brand hover:underline"
                        >
                          Download
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
