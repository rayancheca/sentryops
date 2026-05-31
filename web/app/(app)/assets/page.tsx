"use client";

import { Boxes, Plus, Upload } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { ImportCsvModal } from "@/components/assets/import-csv-modal";
import { CreateAssetModal } from "@/components/assets/create-asset-modal";
import {
  Badge,
  Button,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import { fetcher, ApiError } from "@/lib/api";
import {
  ASSET_TYPE_LABEL,
  ASSET_TYPE_OPTIONS,
  ENVIRONMENT_LABEL,
  ENVIRONMENT_OPTIONS,
  ENVIRONMENT_VARIANT,
  LIFECYCLE_LABEL,
  LIFECYCLE_OPTIONS,
  LIFECYCLE_VARIANT,
} from "@/lib/asset-labels";
import { useAuth } from "@/lib/auth";
import type { AssetListItem, Page } from "@/lib/types";

const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;

function buildQuery(params: Record<string, string>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export default function AssetsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { hasRole } = useAuth();
  const canMutate = hasRole("operator");

  // URL is the source of truth for filters + pagination (shareable, back-button safe).
  const type = searchParams.get("type") ?? "";
  const environment = searchParams.get("environment") ?? "";
  const lifecycle = searchParams.get("lifecycle_state") ?? "";
  const q = searchParams.get("q") ?? "";
  const offset = Math.max(0, Number.parseInt(searchParams.get("offset") ?? "0", 10) || 0);

  const [searchDraft, setSearchDraft] = useState(q);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  // Keep the local search box in sync when the URL changes externally.
  useEffect(() => setSearchDraft(q), [q]);

  const setParams = useCallback(
    (next: Record<string, string>, resetOffset = true) => {
      const merged: Record<string, string> = {
        type,
        environment,
        lifecycle_state: lifecycle,
        q,
        offset: String(offset),
        ...next,
      };
      if (resetOffset && !("offset" in next)) merged.offset = "0";
      router.replace(`/assets${buildQuery(merged)}`, { scroll: false });
    },
    [router, type, environment, lifecycle, q, offset],
  );

  // Debounce search input into the URL.
  useEffect(() => {
    if (searchDraft === q) return;
    const timer = setTimeout(() => setParams({ q: searchDraft }), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchDraft, q, setParams]);

  const apiPath = useMemo(() => {
    return `/assets${buildQuery({
      asset_type: type,
      environment,
      lifecycle_state: lifecycle,
      q,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    })}`;
  }, [type, environment, lifecycle, q, offset]);

  const { data, error, isLoading, mutate } = useSWR<Page<AssetListItem>>(apiPath, fetcher, {
    keepPreviousData: true,
  });

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;
  const hasActiveFilters = Boolean(type || environment || lifecycle || q);

  function clearFilters() {
    setSearchDraft("");
    router.replace("/assets", { scroll: false });
  }

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <PageHeader
        title="Asset inventory"
        description="Configuration items tracked in the CMDB — hosts, services, network, cloud, and licenses."
        actions={
          canMutate ? (
            <>
              <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                <Upload />
                Import CSV
              </Button>
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus />
                New asset
              </Button>
            </>
          ) : null
        }
      />

      {/* Filter bar */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="lg:w-72">
          <Input
            type="search"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            placeholder="Search by name or short code…"
            aria-label="Search assets"
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:flex lg:items-center">
          <Select
            value={type}
            onChange={(e) => setParams({ type: e.target.value })}
            aria-label="Filter by type"
            className="lg:w-40"
          >
            <option value="">All types</option>
            {ASSET_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select
            value={environment}
            onChange={(e) => setParams({ environment: e.target.value })}
            aria-label="Filter by environment"
            className="lg:w-40"
          >
            <option value="">All environments</option>
            {ENVIRONMENT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select
            value={lifecycle}
            onChange={(e) => setParams({ lifecycle_state: e.target.value })}
            aria-label="Filter by lifecycle state"
            className="lg:w-44"
          >
            <option value="">All lifecycles</option>
            {LIFECYCLE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        {hasActiveFilters ? (
          <Button variant="ghost" size="sm" onClick={clearFilters} className="lg:ml-auto">
            Clear filters
          </Button>
        ) : null}
      </div>

      {/* Results */}
      {error ? (
        <EmptyState
          icon={<Boxes />}
          title="Couldn’t load assets"
          description={error instanceof ApiError ? error.message : "Unexpected error."}
          action={
            <Button variant="outline" size="sm" onClick={() => mutate()}>
              Retry
            </Button>
          }
        />
      ) : isLoading && items.length === 0 ? (
        <div className="rounded-card border border-border bg-surface shadow-panel">
          <div className="flex flex-col gap-3 p-5">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Boxes />}
          title={hasActiveFilters ? "No matching assets" : "No assets yet"}
          description={
            hasActiveFilters
              ? "Try widening your filters or clearing the search."
              : canMutate
                ? "Create your first asset or import an existing inventory from CSV."
                : "No configuration items have been registered yet."
          }
          action={
            hasActiveFilters ? (
              <Button variant="outline" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
            ) : canMutate ? (
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus />
                New asset
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="overflow-hidden rounded-card border border-border bg-surface shadow-panel">
          <Table>
            <THead sticky>
              <TR className="hover:bg-transparent">
                <TH className="w-36">Short code</TH>
                <TH>Name</TH>
                <TH className="w-32">Type</TH>
                <TH className="w-32">Environment</TH>
                <TH className="w-40">Lifecycle</TH>
                <TH className="w-44">Owner</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((asset) => (
                <TR
                  key={asset.id}
                  tabIndex={0}
                  role="link"
                  aria-label={`Open ${asset.name}`}
                  onClick={() => router.push(`/assets/${asset.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      router.push(`/assets/${asset.id}`);
                    }
                  }}
                  className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
                >
                  <TD>
                    <span className="tabular text-accent">{asset.short_code}</span>
                  </TD>
                  <TD className="font-medium text-text">{asset.name}</TD>
                  <TD className="text-text-dim">
                    {ASSET_TYPE_LABEL[asset.asset_type] ?? asset.asset_type}
                  </TD>
                  <TD>
                    <Badge variant={ENVIRONMENT_VARIANT[asset.environment]}>
                      {ENVIRONMENT_LABEL[asset.environment]}
                    </Badge>
                  </TD>
                  <TD>
                    <Badge variant={LIFECYCLE_VARIANT[asset.lifecycle_state]}>
                      {LIFECYCLE_LABEL[asset.lifecycle_state]}
                    </Badge>
                  </TD>
                  <TD className="tabular text-xs text-text-dim">
                    {asset.owner_id ? asset.owner_id.slice(0, 8) : "—"}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>

          {/* Pagination */}
          <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3">
            <p className="tabular text-xs text-text-dim">
              {pageStart}–{pageEnd} of {total}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!hasPrev}
                onClick={() =>
                  setParams({ offset: String(Math.max(0, offset - PAGE_SIZE)) }, false)
                }
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!hasNext}
                onClick={() => setParams({ offset: String(offset + PAGE_SIZE) }, false)}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      )}

      {canMutate ? (
        <>
          <CreateAssetModal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            onCreated={(asset) => {
              mutate();
              router.push(`/assets/${asset.id}`);
            }}
          />
          <ImportCsvModal
            open={importOpen}
            onClose={() => setImportOpen(false)}
            onImported={() => mutate()}
          />
        </>
      ) : null}
    </div>
  );
}
