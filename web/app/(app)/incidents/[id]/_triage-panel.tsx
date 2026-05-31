"use client";

import {
  BrainCircuit,
  Check,
  Copy,
  KeyRound,
  ListOrdered,
  Megaphone,
  Sparkles,
  Target,
} from "lucide-react";
import { useState } from "react";
import type { KeyedMutator } from "swr";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  SeverityBadge,
  Spinner,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { formatDateTime, formatPercent } from "@/lib/format";
import type { RemediationStep, TriageResult } from "@/lib/types";

interface TriagePanelProps {
  triage: TriageResult | null;
  // 404 from the triage endpoint = "never run" rather than an error state.
  notRun: boolean;
  loading: boolean;
  canOperate: boolean;
  running: boolean;
  onRun: () => void;
  mutate: KeyedMutator<TriageResult>;
}

/**
 * The AI triage showcase. Four states: loading, disabled (feature flag off),
 * never-run, and a populated result with root-cause, confidence, remediation,
 * and a copyable stakeholder comms draft.
 */
export function TriagePanel({
  triage,
  notRun,
  loading,
  canOperate,
  running,
  onRun,
}: TriagePanelProps) {
  const disabled = triage?.status === "disabled";
  const failed = triage?.status === "failed";
  const hasResult = triage != null && triage.status === "success";

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="bg-accent/15 flex size-7 items-center justify-center rounded-md text-accent [&_svg]:size-4">
            <BrainCircuit aria-hidden="true" />
          </span>
          <div className="flex flex-col gap-0.5">
            <CardTitle className="text-text">AI Triage</CardTitle>
            <span className="text-xs font-normal normal-case tracking-normal text-text-dim">
              Advisory · human-in-the-loop
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {triage?.is_seeded ? (
            <Badge variant="info" title="Illustrative seeded result">
              <Sparkles className="size-3" /> illustrative
            </Badge>
          ) : null}
          {canOperate ? (
            <Button variant="outline" size="sm" onClick={onRun} disabled={running || disabled}>
              {running ? <Spinner size={14} label="Running triage" /> : <Sparkles />}
              {hasResult ? "Re-run" : "Run triage"}
            </Button>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-text-dim">
            <Spinner size={16} /> Loading triage…
          </div>
        ) : disabled ? (
          <DisabledState />
        ) : failed ? (
          <FailedState model={triage?.model ?? null} />
        ) : notRun || !triage ? (
          <NeverRunState canOperate={canOperate} running={running} onRun={onRun} />
        ) : (
          <TriageResultView result={triage} />
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// Empty / degraded states
// --------------------------------------------------------------------------- //
function DisabledState() {
  return (
    <div className="border-warn/40 bg-warn/5 flex flex-col items-center gap-3 rounded-card border border-dashed px-6 py-10 text-center">
      <span className="bg-warn/10 flex size-12 items-center justify-center rounded-full text-warn [&_svg]:size-6">
        <KeyRound aria-hidden="true" />
      </span>
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-text">AI triage is disabled</p>
        <p className="max-w-sm text-sm text-text-dim">
          Set{" "}
          <code className="tabular rounded bg-surface-2 px-1.5 py-0.5 text-xs text-warn">
            ANTHROPIC_API_KEY
          </code>{" "}
          and{" "}
          <code className="tabular rounded bg-surface-2 px-1.5 py-0.5 text-xs text-warn">
            AI_TRIAGE_ENABLED=1
          </code>{" "}
          on the backend to enable root-cause analysis and drafted comms.
        </p>
      </div>
    </div>
  );
}

function FailedState({ model }: { model: string | null }) {
  return (
    <EmptyState
      icon={<BrainCircuit />}
      title="Triage run failed"
      description={
        model
          ? `The model (${model}) returned no usable result. Try re-running.`
          : "The last run returned no usable result. Try re-running."
      }
    />
  );
}

function NeverRunState({
  canOperate,
  running,
  onRun,
}: {
  canOperate: boolean;
  running: boolean;
  onRun: () => void;
}) {
  return (
    <EmptyState
      icon={<BrainCircuit />}
      title="No triage yet"
      description="Run AI triage to generate a root-cause hypothesis, ranked remediation steps, and a draft stakeholder update."
      action={
        canOperate ? (
          <Button variant="primary" size="sm" onClick={onRun} disabled={running}>
            {running ? <Spinner size={14} label="Running triage" /> : <Sparkles />}
            Run AI triage
          </Button>
        ) : (
          <span className="text-xs text-text-dim">Operator role required to run triage.</span>
        )
      }
    />
  );
}

// --------------------------------------------------------------------------- //
// Populated result
// --------------------------------------------------------------------------- //
function TriageResultView({ result }: { result: TriageResult }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_auto]">
        <section className="space-y-2" aria-label="Root cause hypothesis">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-dim">
            <Target className="size-3.5 text-accent" aria-hidden="true" /> Root-cause hypothesis
          </h4>
          <p className="text-sm leading-relaxed text-text">
            {result.root_cause_hypothesis ?? "No hypothesis returned."}
          </p>
          {result.severity_assessment ? (
            <div className="flex items-center gap-2 pt-1 text-xs text-text-dim">
              <span className="uppercase tracking-wider">Assessed severity</span>
              <SeverityBadge severity={result.severity_assessment} />
            </div>
          ) : null}
        </section>

        {result.confidence != null ? <ConfidenceMeter confidence={result.confidence} /> : null}
      </div>

      {result.remediation_steps && result.remediation_steps.length > 0 ? (
        <RemediationList steps={result.remediation_steps} />
      ) : null}

      {result.stakeholder_comms_draft ? (
        <CommsDraft draft={result.stakeholder_comms_draft} />
      ) : null}

      <TriageFooter result={result} />
    </div>
  );
}

const CONFIDENCE_HIGH = 0.75;
const CONFIDENCE_MED = 0.5;

function ConfidenceMeter({ confidence }: { confidence: number }) {
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  const clamped = Math.min(100, Math.max(0, pct));
  const fraction = clamped / 100;
  const tone = fraction >= CONFIDENCE_HIGH ? "ok" : fraction >= CONFIDENCE_MED ? "warn" : "danger";
  const toneText = { ok: "text-ok", warn: "text-warn", danger: "text-danger" }[tone];
  const toneStroke = {
    ok: "var(--color-ok)",
    warn: "var(--color-warn)",
    danger: "var(--color-danger)",
  }[tone];

  const size = 88;
  const stroke = 7;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - fraction);

  return (
    <div className="bg-bg/40 flex flex-col items-center justify-center gap-1.5 rounded-card border border-border px-5 py-3">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
        Confidence
      </span>
      <div
        className="relative inline-flex"
        style={{ width: size, height: size }}
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Triage confidence"
      >
        <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={toneStroke}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-[stroke-dashoffset] duration-[280ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
          />
        </svg>
        <span
          className={cn(
            "tabular absolute inset-0 flex items-center justify-center text-lg font-semibold",
            toneText,
          )}
        >
          {formatPercent(fraction, 0)}
        </span>
      </div>
    </div>
  );
}

function RemediationList({ steps }: { steps: RemediationStep[] }) {
  const ordered = [...steps].sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99));
  return (
    <section className="space-y-2" aria-label="Remediation steps">
      <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-dim">
        <ListOrdered className="size-3.5 text-accent" aria-hidden="true" /> Remediation steps
      </h4>
      <ol className="space-y-2">
        {ordered.map((step, index) => (
          <li
            key={index}
            className="bg-bg/40 flex gap-3 rounded-md border border-border px-3 py-2.5"
          >
            <span className="tabular bg-accent/15 flex size-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold text-accent">
              {step.priority ?? index + 1}
            </span>
            <div className="flex flex-col gap-0.5">
              <span className="text-sm text-text">{step.step}</span>
              {step.rationale ? (
                <span className="text-xs text-text-dim">{step.rationale}</span>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CommsDraft({ draft }: { draft: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="space-y-2" aria-label="Stakeholder communications draft">
      <div className="flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-dim">
          <Megaphone className="size-3.5 text-accent" aria-hidden="true" /> Draft stakeholder comms
        </h4>
        <Button variant="ghost" size="sm" onClick={copy} aria-label="Copy comms draft">
          {copied ? <Check className="text-ok" /> : <Copy />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="tabular bg-bg/60 max-h-72 overflow-auto whitespace-pre-wrap rounded-card border border-border px-4 py-3 font-mono text-xs leading-relaxed text-text">
        {draft}
      </pre>
    </section>
  );
}

function TriageFooter({ result }: { result: TriageResult }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 text-[11px] text-muted">
      {result.model ? <span className="tabular">model · {result.model}</span> : null}
      <span className="tabular">
        tokens · {result.input_tokens.toLocaleString()} in / {result.output_tokens.toLocaleString()}{" "}
        out
      </span>
      <span className="tabular">cost · ${result.estimated_cost_usd.toFixed(4)}</span>
      <span className="tabular ml-auto">{formatDateTime(result.created_at)}</span>
    </div>
  );
}
