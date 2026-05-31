"use client";

import { ArrowLeft, Boxes, MapPin } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";

import { AttributesPanel } from "@/components/assets/attributes-panel";
import { AuditPanel } from "@/components/assets/audit-panel";
import { CompliancePanel } from "@/components/assets/compliance-panel";
import { DependencyPanel } from "@/components/assets/dependency-panel";
import { AssetQr } from "@/components/assets/asset-qr";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from "@/components/ui";
import { ApiError, fetcher } from "@/lib/api";
import {
  ASSET_TYPE_LABEL,
  ENVIRONMENT_LABEL,
  ENVIRONMENT_VARIANT,
  LIFECYCLE_LABEL,
  LIFECYCLE_VARIANT,
} from "@/lib/asset-labels";
import { formatDateTime, formatRelative } from "@/lib/format";
import type { Asset } from "@/lib/types";

export default function AssetDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const { data: asset, error, isLoading, mutate } = useSWR<Asset>(`/assets/${id}`, fetcher);

  if (isLoading) {
    return (
      <div className="flex animate-fade-in flex-col gap-6">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-40 w-full" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Skeleton className="h-72 w-full lg:col-span-2" />
          <Skeleton className="h-72 w-full" />
        </div>
      </div>
    );
  }

  if (error || !asset) {
    return (
      <EmptyState
        icon={<Boxes />}
        title="Asset not found"
        description={
          error instanceof ApiError ? error.message : "This asset may have been removed."
        }
        action={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => mutate()}>
              Retry
            </Button>
            <Button asChild size="sm">
              <Link href="/assets">Back to inventory</Link>
            </Button>
          </div>
        }
      />
    );
  }

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      {/* Breadcrumb + header */}
      <div className="flex flex-col gap-4">
        <Link
          href="/assets"
          className="inline-flex w-fit items-center gap-1.5 rounded text-sm text-text-dim transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Inventory
        </Link>

        <div className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-text">{asset.name}</h1>
              <span className="tabular rounded-md border border-border bg-surface-2 px-2 py-0.5 text-sm text-accent">
                {asset.short_code}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">
                {ASSET_TYPE_LABEL[asset.asset_type] ?? asset.asset_type}
              </Badge>
              <Badge variant={ENVIRONMENT_VARIANT[asset.environment]}>
                {ENVIRONMENT_LABEL[asset.environment]}
              </Badge>
              <Badge variant={LIFECYCLE_VARIANT[asset.lifecycle_state]}>
                {LIFECYCLE_LABEL[asset.lifecycle_state]}
              </Badge>
              {asset.location ? (
                <span className="inline-flex items-center gap-1 text-xs text-text-dim">
                  <MapPin className="size-3.5" aria-hidden="true" />
                  {asset.location}
                </span>
              ) : null}
            </div>
          </div>
          <p className="tabular text-xs text-text-dim">
            Updated{" "}
            <time dateTime={asset.updated_at} title={formatDateTime(asset.updated_at)}>
              {formatRelative(asset.updated_at)}
            </time>
          </p>
        </div>

        {asset.description ? (
          <p className="max-w-3xl text-sm text-text-dim">{asset.description}</p>
        ) : null}
      </div>

      {/* Top row: identity (QR + tags) and attributes */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Label</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <AssetQr assetId={asset.id} shortCode={asset.short_code} />
            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-text-dim">Tags</p>
              {asset.tags.length === 0 ? (
                <p className="text-sm text-muted">No tags</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {asset.tags.map((tag) => (
                    <span
                      key={tag.id}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2 py-0.5 text-xs text-text"
                    >
                      <span
                        className="size-2 rounded-full"
                        style={{ backgroundColor: tag.color }}
                        aria-hidden="true"
                      />
                      {tag.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="lg:col-span-2">
          <AttributesPanel asset={asset} />
        </div>
      </div>

      {/* Dependency graph spans full width */}
      <DependencyPanel assetId={asset.id} />

      {/* Compliance + audit side by side */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CompliancePanel assetId={asset.id} />
        <AuditPanel assetId={asset.id} />
      </div>
    </div>
  );
}
