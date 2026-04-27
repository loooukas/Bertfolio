"use client"

import { type ReactNode } from "react"
import { AlertTriangle, CheckCircle2, Clock, Cpu, Database, FileSearch, Info, Shield, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"

interface TaskBreakdown {
  key: string
  label: string
  status: "done" | "error" | "skipped"
  duration_ms: number
  detail: string
}

interface TranscriptDiscovery {
  pages_scanned: number
  candidates_total: number
  transcript_like_count: number
  match_filtered_count: number
  selected_count: number
  discarded_near_matches: string[]
  fetch_failures: string[]
  playwright_fallback_used: boolean
}

interface FundamentalsValidation {
  yahoo_source_used: boolean
  alpha_source_used: boolean
  compared_fields: string[]
  notes: string[]
  mismatches: Array<{
    key: string
    yahoo_value: string
    alpha_value: string
    relative_diff_pct: number
    severity: "low" | "medium" | "high"
    note: string
  }>
}

interface DataAuditData {
  confidence_note: string
  normalization_mode: "openai" | "deterministic_degraded"
  warnings: string[]
  notices: string[]
  diagnostics: string[]
  missing_items: string[]
  parsing_warnings?: string[]
  source_counts: {
    transcripts: number
    news: number
    social: number
  }
  dedupe_counts: {
    pool: number
    deduped: number
  }
  transcript_discovery: TranscriptDiscovery
  task_breakdown: TaskBreakdown[]
  fundamentals_validation: FundamentalsValidation
}

interface DataAuditSectionProps {
  data: DataAuditData
}

const severityBadgeClass: Record<"low" | "medium" | "high", string> = {
  low: "border-border bg-secondary/40 text-muted-foreground",
  medium: "border-warning/30 bg-warning/10 text-warning",
  high: "border-destructive/30 bg-destructive/10 text-destructive",
}

const severityDiffClass: Record<"low" | "medium" | "high", string> = {
  low: "text-muted-foreground",
  medium: "text-warning",
  high: "text-destructive",
}

const severityLabel: Record<"low" | "medium" | "high", string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
}

function getStatusIcon(status: string) {
  switch (status) {
    case "done":
      return <CheckCircle2 className="w-4 h-4 text-bullish" />
    case "error":
      return <XCircle className="w-4 h-4 text-destructive" />
    case "skipped":
      return <AlertTriangle className="w-4 h-4 text-warning" />
    default:
      return null
  }
}

function Bucket({
  icon,
  title,
  items,
  emptyLabel,
  variant,
}: {
  icon: ReactNode
  title: string
  items: string[]
  emptyLabel: string
  variant: "warning" | "notice" | "diagnostic"
}) {
  const style =
    variant === "warning"
      ? "border-warning/25 bg-warning/5"
      : variant === "notice"
        ? "border-border bg-secondary/20"
        : "border-border bg-muted/35"

  return (
    <div className={`rounded-xl border p-4 ${style}`}>
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <h4 className="text-sm font-medium text-foreground">{title}</h4>
      </div>
      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((item, index) => (
            <li
              key={`${title}-${index}-${item.slice(0, 12)}`}
              className={`text-sm ${variant === "diagnostic" ? "font-mono text-xs" : ""} text-muted-foreground`}
            >
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-sm text-muted-foreground">{emptyLabel}</div>
      )}
    </div>
  )
}

export function DataAuditSection({ data }: DataAuditSectionProps) {
  const totalDuration = data.task_breakdown.reduce((sum, task) => sum + task.duration_ms, 0)
  const successCount = data.task_breakdown.filter((task) => task.status === "done").length
  const errorCount = data.task_breakdown.filter((task) => task.status === "error").length

  const dedupeRate = data.dedupe_counts.pool > 0
    ? ((data.dedupe_counts.pool - data.dedupe_counts.deduped) / data.dedupe_counts.pool) * 100
    : 0

  const diagnostics = Array.from(
    new Set(
      [...(data.diagnostics || []), ...(data.parsing_warnings || [])]
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  )

  const hasBlockingIssues = data.warnings.length > 0 || errorCount > 0

  return (
    <div className="space-y-8">
      <div className={`rounded-xl border p-6 ${hasBlockingIssues ? "border-warning/25 bg-warning/5" : "border-bullish/20 bg-bullish/5"}`}>
        <div className="flex items-start gap-4">
          <div className={`rounded-lg p-3 ${hasBlockingIssues ? "bg-warning/10" : "bg-bullish/10"}`}>
            <Shield className={`w-6 h-6 ${hasBlockingIssues ? "text-warning" : "text-bullish"}`} />
          </div>
          <div className="flex-1">
            <h3 className="mb-2 text-base font-semibold text-foreground">Data Quality Assessment</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">{data.confidence_note}</p>
          </div>
          <Badge className={data.normalization_mode === "openai" ? "border-bullish/20 bg-bullish/10 text-bullish" : "border-warning/20 bg-warning/10 text-warning"}>
            {data.normalization_mode === "openai" ? "OpenAI Mode" : "Degraded Mode"}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <Database className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Sources</span>
          </div>
          <div className="text-2xl font-bold text-foreground">
            {data.source_counts.transcripts + data.source_counts.news + data.source_counts.social}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {data.source_counts.transcripts}T / {data.source_counts.news}N / {data.source_counts.social}S
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <FileSearch className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Dedupe Rate</span>
          </div>
          <div className="text-2xl font-bold text-foreground">{dedupeRate.toFixed(0)}%</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {data.dedupe_counts.pool} → {data.dedupe_counts.deduped}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <Clock className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Total Time</span>
          </div>
          <div className="text-2xl font-bold text-foreground">{(totalDuration / 1000).toFixed(1)}s</div>
          <div className="mt-1 text-xs text-muted-foreground">{data.task_breakdown.length} stages</div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Success Rate</span>
          </div>
          <div className={`text-2xl font-bold ${successCount === data.task_breakdown.length ? "text-bullish" : "text-warning"}`}>
            {Math.round((successCount / Math.max(1, data.task_breakdown.length)) * 100)}%
          </div>
          <div className="mt-1 text-xs text-muted-foreground">{successCount}/{data.task_breakdown.length} tasks</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Bucket
          icon={<AlertTriangle className="w-4 h-4 text-warning" />}
          title="Warnings"
          items={data.warnings}
          emptyLabel="No actionable warnings."
          variant="warning"
        />
        <Bucket
          icon={<Info className="w-4 h-4 text-muted-foreground" />}
          title="Notices"
          items={data.notices}
          emptyLabel="No non-blocking notices."
          variant="notice"
        />
        <Bucket
          icon={<FileSearch className="w-4 h-4 text-muted-foreground" />}
          title="Diagnostics"
          items={diagnostics}
          emptyLabel="No diagnostics captured."
          variant="diagnostic"
        />
      </div>

      {data.missing_items.length > 0 && (
        <div className="rounded-xl border border-border bg-muted p-4">
          <div className="mb-3 flex items-center gap-2">
            <XCircle className="w-4 h-4 text-muted-foreground" />
            <h4 className="text-sm font-medium text-foreground">Missing Items</h4>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.missing_items.map((item, index) => (
              <Badge key={`${item}-${index}`} variant="outline" className="text-xs">
                {item}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-muted-foreground">Task Breakdown</h3>
        <div className="space-y-3">
          {data.task_breakdown.map((task) => (
            <div key={task.key} className="flex items-center gap-4 rounded-lg bg-secondary/30 p-3">
              <div className="flex-shrink-0">{getStatusIcon(task.status)}</div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">{task.label}</span>
                  <span className="text-xs text-muted-foreground">• {task.detail}</span>
                </div>
              </div>
              <div className="flex-shrink-0 font-mono text-xs text-muted-foreground">{(task.duration_ms / 1000).toFixed(2)}s</div>
              <div className="w-24 flex-shrink-0">
                <Progress value={totalDuration > 0 ? (task.duration_ms / totalDuration) * 100 : 0} className="h-1.5" />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-muted-foreground">Transcript Discovery</h3>
        <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
          <div className="rounded-lg bg-secondary/50 p-3 text-center">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.pages_scanned}</div>
            <div className="text-xs text-muted-foreground">Pages Scanned</div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-3 text-center">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.candidates_total}</div>
            <div className="text-xs text-muted-foreground">Candidates</div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-3 text-center">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.transcript_like_count}</div>
            <div className="text-xs text-muted-foreground">Transcript-like</div>
          </div>
          <div className="rounded-lg bg-secondary/50 p-3 text-center">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.match_filtered_count}</div>
            <div className="text-xs text-muted-foreground">Filtered</div>
          </div>
          <div className="rounded-lg bg-bullish/10 p-3 text-center">
            <div className="text-xl font-bold text-bullish">{data.transcript_discovery.selected_count}</div>
            <div className="text-xs text-muted-foreground">Selected</div>
          </div>
        </div>

        {data.transcript_discovery.playwright_fallback_used && (
          <Badge variant="outline" className="text-xs">
            Playwright Fallback Used
          </Badge>
        )}

        {data.transcript_discovery.fetch_failures.length > 0 && (
          <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
            <div className="mb-1 text-xs font-medium text-destructive">Fetch Failures</div>
            <div className="text-xs text-muted-foreground">{data.transcript_discovery.fetch_failures.join(", ")}</div>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-muted-foreground">Fundamentals Validation</h3>
        <div className="mb-4 flex flex-wrap gap-2">
          {data.fundamentals_validation.yahoo_source_used && (
            <Badge variant="outline" className="text-xs">Yahoo Finance</Badge>
          )}
          {data.fundamentals_validation.alpha_source_used && (
            <Badge variant="outline" className="text-xs">Alpha Vantage</Badge>
          )}
        </div>

        <div className="mb-4">
          <div className="mb-2 text-xs text-muted-foreground">Compared Fields</div>
          <div className="flex flex-wrap gap-1">
            {data.fundamentals_validation.compared_fields.map((field) => (
              <Badge key={field} variant="secondary" className="text-xs font-mono">
                {field}
              </Badge>
            ))}
          </div>
        </div>

        {data.fundamentals_validation.notes.length > 0 && (
          <div className="rounded-lg border border-bullish/20 bg-bullish/5 p-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-bullish" />
              <span className="text-sm text-foreground">{data.fundamentals_validation.notes.join(" ")}</span>
            </div>
          </div>
        )}

        {data.fundamentals_validation.mismatches.length > 0 && (
          <div className="mt-4 overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-secondary/50">
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Field</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Yahoo</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Alpha</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Diff</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Severity</th>
                </tr>
              </thead>
              <tbody>
                {data.fundamentals_validation.mismatches.map((mismatch) => (
                  <tr key={mismatch.key} className="border-t border-border">
                    <td className="px-3 py-2 font-mono text-foreground">{mismatch.key}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{mismatch.yahoo_value}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{mismatch.alpha_value}</td>
                    <td className={`px-3 py-2 text-right font-mono ${severityDiffClass[mismatch.severity]}`}>
                      {mismatch.relative_diff_pct.toFixed(1)}%
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Badge variant="outline" className={`text-[11px] ${severityBadgeClass[mismatch.severity]}`}>
                        {severityLabel[mismatch.severity]}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
