"use client";

import { Share2 } from "lucide-react";
import useSWR from "swr";

import { DependencyGraph } from "@/components/assets/dependency-graph";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { DependencyTree } from "@/lib/types";

export interface DependencyPanelProps {
  assetId: string;
}

export function DependencyPanel({ assetId }: DependencyPanelProps) {
  const upstream = useSWR<DependencyTree>(`/dependencies/upstream/${assetId}`, fetcher);
  const downstream = useSWR<DependencyTree>(`/dependencies/downstream/${assetId}`, fetcher);

  const loading = upstream.isLoading || downstream.isLoading;
  const errored = upstream.error || downstream.error;

  const upNodes = (upstream.data?.nodes.length ?? 1) - 1; // exclude focus node
  const downNodes = (downstream.data?.nodes.length ?? 1) - 1;
  const empty = !loading && !errored && upNodes <= 0 && downNodes <= 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Dependencies</CardTitle>
        <CardDescription>
          Upstream services this asset relies on and the assets that depend on it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {errored ? (
          <p className="text-sm text-danger">Couldn’t load the dependency graph.</p>
        ) : loading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : empty ? (
          <EmptyState
            icon={<Share2 />}
            title="No dependencies mapped"
            description="This asset has no upstream or downstream edges yet."
          />
        ) : (
          <DependencyGraph upstream={upstream.data} downstream={downstream.data} />
        )}
      </CardContent>
    </Card>
  );
}
