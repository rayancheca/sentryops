"use client";

import { UploadCloud } from "lucide-react";
import { useState } from "react";

import { AssetModal } from "@/components/assets/asset-modal";
import { Button } from "@/components/ui";
import { API_BASE, getToken } from "@/lib/api";

export interface ImportCsvModalProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}

interface ImportSummary {
  created?: number;
  errors?: number;
  [key: string]: unknown;
}

// The import endpoint accepts a raw UTF-8 CSV body (text/csv), so this bypasses
// the JSON `api` helper and posts the file contents directly with the bearer token.
async function importCsv(csv: string): Promise<ImportSummary> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/v1/assets/import`, {
    method: "POST",
    headers: {
      "Content-Type": "text/csv",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: csv,
  });
  const body = (await res.json().catch(() => null)) as {
    success?: boolean;
    data?: ImportSummary | null;
    error?: { message?: string } | null;
  } | null;
  if (!res.ok || !body || body.success === false) {
    throw new Error(body?.error?.message ?? "CSV import failed.");
  }
  return body.data ?? {};
}

export function ImportCsvModal({ open, onClose, onImported }: ImportCsvModalProps) {
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  function close() {
    setCsv("");
    setFileName(null);
    setError(null);
    setSummary(null);
    onClose();
  }

  async function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setError(null);
    setCsv(await file.text());
  }

  async function submit() {
    if (!csv.trim()) {
      setError("Paste CSV content or choose a file first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await importCsv(csv);
      setSummary(result);
      onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : "CSV import failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AssetModal
      open={open}
      onClose={close}
      title="Import assets from CSV"
      description="Bulk-create configuration items. Header row required; UTF-8, max 1 MiB."
      footer={
        summary ? (
          <Button size="sm" onClick={close}>
            Done
          </Button>
        ) : (
          <>
            <Button variant="ghost" size="sm" onClick={close} disabled={submitting}>
              Cancel
            </Button>
            <Button size="sm" onClick={submit} disabled={submitting}>
              {submitting ? "Importing…" : "Import"}
            </Button>
          </>
        )
      }
    >
      {summary ? (
        <div className="border-ok/30 bg-ok/10 flex flex-col gap-2 rounded-md border px-4 py-3">
          <p className="text-sm font-medium text-ok">Import complete.</p>
          <p className="tabular text-sm text-text-dim">
            {typeof summary.created === "number" ? `${summary.created} created` : "Processed"}
            {typeof summary.errors === "number" && summary.errors > 0
              ? ` · ${summary.errors} skipped`
              : ""}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <label className="bg-surface/40 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border px-4 py-6 text-center transition-colors duration-[140ms] focus-within:ring-2 focus-within:ring-accent hover:border-accent-dim hover:bg-surface-2">
            <UploadCloud className="size-6 text-text-dim" aria-hidden="true" />
            <span className="text-sm text-text">{fileName ?? "Choose a .csv file"}</span>
            <span className="text-xs text-muted">or paste rows below</span>
            <input type="file" accept=".csv,text/csv" className="sr-only" onChange={onFile} />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
              CSV content
            </span>
            <textarea
              value={csv}
              onChange={(e) => {
                setCsv(e.target.value);
                setFileName(null);
              }}
              rows={6}
              spellCheck={false}
              placeholder="name,asset_type,environment,lifecycle_state&#10;edge-router-01,network_device,prod,active"
              className="tabular hover:border-accent-dim/60 focus-visible:ring-accent/40 w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-xs text-text transition-colors duration-[140ms] placeholder:text-muted focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2"
            />
          </label>

          {error ? (
            <p className="border-danger/40 bg-danger/10 rounded-md border px-3 py-2 text-sm text-danger">
              {error}
            </p>
          ) : null}
        </div>
      )}
    </AssetModal>
  );
}
