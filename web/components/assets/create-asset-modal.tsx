"use client";

import { useState } from "react";

import { AssetModal } from "@/components/assets/asset-modal";
import { Button, Input, Select } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { ASSET_TYPE_OPTIONS, ENVIRONMENT_OPTIONS, LIFECYCLE_OPTIONS } from "@/lib/asset-labels";
import type { Asset, AssetType, Environment, LifecycleState } from "@/lib/types";

export interface CreateAssetModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (asset: Asset) => void;
}

interface FormState {
  name: string;
  asset_type: AssetType;
  environment: Environment;
  lifecycle_state: LifecycleState;
  location: string;
}

const INITIAL: FormState = {
  name: "",
  asset_type: "host",
  environment: "prod",
  lifecycle_state: "active",
  location: "",
};

export function CreateAssetModal({ open, onClose, onCreated }: CreateAssetModalProps) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function close() {
    setForm(INITIAL);
    setError(null);
    onClose();
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.name.trim()) {
      setError("Name is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const asset = await api.post<Asset>("/assets", {
        name: form.name.trim(),
        asset_type: form.asset_type,
        environment: form.environment,
        lifecycle_state: form.lifecycle_state,
        location: form.location.trim() || null,
      });
      onCreated(asset);
      close();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create asset.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AssetModal
      open={open}
      onClose={close}
      title="New asset"
      description="Register a configuration item in the CMDB."
      footer={
        <>
          <Button type="button" variant="ghost" size="sm" onClick={close} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="create-asset-form" size="sm" disabled={submitting}>
            {submitting ? "Creating…" : "Create asset"}
          </Button>
        </>
      }
    >
      <form id="create-asset-form" onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wider text-text-dim">Name</span>
          <Input
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            placeholder="e.g. edge-router-01"
            autoFocus
            required
          />
        </label>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wider text-text-dim">Type</span>
            <Select
              value={form.asset_type}
              onChange={(e) => update("asset_type", e.target.value as AssetType)}
            >
              {ASSET_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
              Environment
            </span>
            <Select
              value={form.environment}
              onChange={(e) => update("environment", e.target.value as Environment)}
            >
              {ENVIRONMENT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
              Lifecycle
            </span>
            <Select
              value={form.lifecycle_state}
              onChange={(e) => update("lifecycle_state", e.target.value as LifecycleState)}
            >
              {LIFECYCLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
              Location
            </span>
            <Input
              value={form.location}
              onChange={(e) => update("location", e.target.value)}
              placeholder="Optional"
            />
          </label>
        </div>

        {error ? (
          <p className="border-danger/40 bg-danger/10 rounded-md border px-3 py-2 text-sm text-danger">
            {error}
          </p>
        ) : null}
      </form>
    </AssetModal>
  );
}
