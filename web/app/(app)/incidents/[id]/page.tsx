"use client";

import { ArrowLeft, CheckCircle2, Clock, MessageSquarePlus, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  SeverityBadge,
  Skeleton,
  Spinner,
  StatusDot,
} from "@/components/ui";
import { api, ApiError, fetcher } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import type { Incident, IncidentEvent, TriageResult } from "@/lib/types";

import { STATUS_BADGE, STATUS_DOT, STATUS_LABEL } from "../_lib";
import { Timeline } from "./_timeline";
import { TriagePanel } from "./_triage-panel";

/** Incident detail = incident fields + ordered event timeline (backend join). */
interface IncidentDetail extends Incident {
  events: IncidentEvent[];
}

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { hasRole } = useAuth();
  const canOperate = hasRole("operator");

  const detail = useSWR<IncidentDetail>(`/incidents/${id}`, fetcher);
  const triage = useSWR<TriageResult>(`/incidents/${id}/triage`, fetcher, {
    shouldRetryOnError: false,
  });

  const [running, setRunning] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const incident = detail.data;
  // A 404 from /triage means "never run" — distinguish it from a real error.
  const triageNotRun = triage.error instanceof ApiError && triage.error.status === 404;
  const triageLoading = triage.isLoading && !triage.error;

  async function runAction(fn: () => Promise<unknown>) {
    setActionError(null);
    try {
      await fn();
      await detail.mutate();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Action failed.");
    }
  }

  async function runTriage() {
    setRunning(true);
    setActionError(null);
    try {
      await api.post<TriageResult>(`/incidents/${id}/triage/run`);
      await Promise.all([triage.mutate(), detail.mutate()]);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Triage failed to run.");
    } finally {
      setRunning(false);
    }
  }

  if (detail.isLoading) {
    return <DetailSkeleton />;
  }

  if (detail.error || !incident) {
    return (
      <div className="flex animate-fade-in flex-col gap-6">
        <BackLink />
        <EmptyState
          icon={<ShieldCheck />}
          title="Incident not found"
          description={
            detail.error instanceof ApiError
              ? detail.error.message
              : "This incident is unavailable."
          }
        />
      </div>
    );
  }

  const canAct = incident.status !== "resolved" && incident.status !== "closed";

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <BackLink />

      <IncidentHeader
        incident={incident}
        canOperate={canOperate}
        canAct={canAct}
        onAcknowledge={() => runAction(() => api.post<Incident>(`/incidents/${id}/acknowledge`))}
        onResolve={() => runAction(() => api.post<Incident>(`/incidents/${id}/resolve`))}
      />

      {actionError ? (
        <p className="border-danger/40 bg-danger/10 rounded-md border px-3 py-2 text-sm text-danger">
          {actionError}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex flex-col gap-6">
          <TriagePanel
            triage={triage.data ?? null}
            notRun={triageNotRun}
            loading={triageLoading}
            canOperate={canOperate}
            running={running}
            onRun={runTriage}
            mutate={triage.mutate}
          />
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <Timeline events={incident.events} />
            </CardContent>
          </Card>

          {canOperate ? (
            <CommentBox
              disabled={!canAct}
              onSubmit={(message) =>
                runAction(() => api.post<IncidentEvent>(`/incidents/${id}/comment`, { message }))
              }
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/incidents"
      className="inline-flex w-fit items-center gap-1.5 text-sm text-text-dim transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <ArrowLeft className="size-4" aria-hidden="true" /> Incidents
    </Link>
  );
}

// --------------------------------------------------------------------------- //
// Header: title, severity, status, lifecycle timeline + actions
// --------------------------------------------------------------------------- //
interface IncidentHeaderProps {
  incident: IncidentDetail;
  canOperate: boolean;
  canAct: boolean;
  onAcknowledge: () => void;
  onResolve: () => void;
}

function IncidentHeader({
  incident,
  canOperate,
  canAct,
  onAcknowledge,
  onResolve,
}: IncidentHeaderProps) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-5 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={incident.severity} />
              <span className="inline-flex items-center gap-2">
                <StatusDot
                  status={STATUS_DOT[incident.status]}
                  pulse={incident.status === "open"}
                />
                <Badge variant={STATUS_BADGE[incident.status]}>
                  {STATUS_LABEL[incident.status]}
                </Badge>
              </span>
              <span className="tabular text-xs text-muted">#{incident.id.slice(0, 8)}</span>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-text">{incident.title}</h1>
          </div>

          {canOperate ? (
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={onAcknowledge}
                disabled={!canAct || incident.status === "acknowledged"}
              >
                <ShieldCheck /> Acknowledge
              </Button>
              <Button variant="primary" size="sm" onClick={onResolve} disabled={!canAct}>
                <CheckCircle2 /> Resolve
              </Button>
            </div>
          ) : (
            <Badge variant="outline">Read-only · viewer</Badge>
          )}
        </div>

        <LifecycleTimeline incident={incident} />
      </CardContent>
    </Card>
  );
}

function LifecycleTimeline({ incident }: { incident: Incident }) {
  return (
    <div className="grid gap-3 border-t border-border pt-4 sm:grid-cols-3">
      <TimestampCell
        label="Opened"
        iso={incident.opened_at}
        tone="danger"
        icon={<Clock className="size-3.5" aria-hidden="true" />}
      />
      <TimestampCell
        label="Acknowledged"
        iso={incident.acknowledged_at}
        tone="warn"
        icon={<ShieldCheck className="size-3.5" aria-hidden="true" />}
      />
      <TimestampCell
        label="Resolved"
        iso={incident.resolved_at}
        tone="ok"
        icon={<CheckCircle2 className="size-3.5" aria-hidden="true" />}
      />
    </div>
  );
}

const TONE_TEXT = { danger: "text-danger", warn: "text-warn", ok: "text-ok" } as const;

function TimestampCell({
  label,
  iso,
  tone,
  icon,
}: {
  label: string;
  iso: string | null;
  tone: keyof typeof TONE_TEXT;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span
        className={cn(
          "flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider",
          iso ? TONE_TEXT[tone] : "text-muted",
        )}
      >
        {icon}
        {label}
      </span>
      {iso ? (
        <>
          <span className="tabular text-sm text-text">{formatDateTime(iso)}</span>
          <span className="tabular text-xs text-text-dim">{formatRelative(iso)}</span>
        </>
      ) : (
        <span className="tabular text-sm text-muted">—</span>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Comment box (operator+)
// --------------------------------------------------------------------------- //
function CommentBox({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (message: string) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    const trimmed = message.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await onSubmit(trimmed);
      setMessage("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <MessageSquarePlus className="size-3.5" aria-hidden="true" /> Add comment
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          disabled={disabled || submitting}
          rows={3}
          placeholder={disabled ? "Incident is resolved." : "Share an update or finding…"}
          className={cn(
            "w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm text-text",
            "transition-colors duration-[140ms] placeholder:text-muted",
            "hover:border-accent-dim/60",
            "focus-visible:ring-accent/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        />
        <div className="flex justify-end">
          <Button
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            disabled={disabled || submitting || message.trim().length === 0}
          >
            {submitting ? <Spinner size={14} label="Posting" /> : <Send />}
            Post comment
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-5 w-24" />
      <Card>
        <CardContent className="space-y-4 p-5">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-8 w-2/3" />
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <Skeleton className="h-80 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    </div>
  );
}
