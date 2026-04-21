"use client"

import { CheckCircle2, AlertTriangle, XCircle, Clock, Database, FileSearch, Cpu, Shield } from "lucide-react"
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
    note: string
  }>
}

interface DataAuditData {
  confidence_note: string
  normalization_mode: "openai" | "deterministic_degraded"
  warnings: string[]
  missing_items: string[]
  parsing_warnings: string[]
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

const getStatusIcon = (status: string) => {
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

export function DataAuditSection({ data }: DataAuditSectionProps) {
  const totalDuration = data.task_breakdown.reduce((sum, task) => sum + task.duration_ms, 0)
  const successCount = data.task_breakdown.filter((t) => t.status === "done").length
  const errorCount = data.task_breakdown.filter((t) => t.status === "error").length
  
  const dedupeRate = data.dedupe_counts.pool > 0
    ? ((data.dedupe_counts.pool - data.dedupe_counts.deduped) / data.dedupe_counts.pool) * 100
    : 0

  return (
    <div className="space-y-8">
      {/* Confidence Summary */}
      <div className={`p-6 rounded-xl border ${
        data.warnings.length === 0 && errorCount === 0 
          ? "bg-bullish/5 border-bullish/20" 
          : data.warnings.length > 0 || errorCount > 0 
          ? "bg-warning/5 border-warning/20" 
          : "bg-card border-border"
      }`}>
        <div className="flex items-start gap-4">
          <div className={`p-3 rounded-lg ${
            data.warnings.length === 0 && errorCount === 0 
              ? "bg-bullish/10" 
              : "bg-warning/10"
          }`}>
            <Shield className={`w-6 h-6 ${
              data.warnings.length === 0 && errorCount === 0 
                ? "text-bullish" 
                : "text-warning"
            }`} />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-foreground mb-2">
              Data Quality Assessment
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {data.confidence_note}
            </p>
          </div>
          <Badge className={`${
            data.normalization_mode === "openai" 
              ? "bg-bullish/10 text-bullish border-bullish/20" 
              : "bg-warning/10 text-warning border-warning/20"
          }`}>
            {data.normalization_mode === "openai" ? "OpenAI Mode" : "Degraded Mode"}
          </Badge>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-card border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Sources</span>
          </div>
          <div className="text-2xl font-bold text-foreground">
            {data.source_counts.transcripts + data.source_counts.news + data.source_counts.social}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {data.source_counts.transcripts}T / {data.source_counts.news}N / {data.source_counts.social}S
          </div>
        </div>

        <div className="p-4 rounded-xl bg-card border border-border">
          <div className="flex items-center gap-2 mb-2">
            <FileSearch className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Dedupe Rate</span>
          </div>
          <div className="text-2xl font-bold text-foreground">
            {dedupeRate.toFixed(0)}%
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {data.dedupe_counts.pool} → {data.dedupe_counts.deduped}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-card border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Total Time</span>
          </div>
          <div className="text-2xl font-bold text-foreground">
            {(totalDuration / 1000).toFixed(1)}s
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {data.task_breakdown.length} stages
          </div>
        </div>

        <div className="p-4 rounded-xl bg-card border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="w-4 h-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Success Rate</span>
          </div>
          <div className={`text-2xl font-bold ${
            successCount === data.task_breakdown.length ? "text-bullish" : "text-warning"
          }`}>
            {Math.round((successCount / data.task_breakdown.length) * 100)}%
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {successCount}/{data.task_breakdown.length} tasks
          </div>
        </div>
      </div>

      {/* Warnings & Issues */}
      {(data.warnings.length > 0 || data.missing_items.length > 0 || data.parsing_warnings.length > 0) && (
        <div className="space-y-4">
          {data.warnings.length > 0 && (
            <div className="p-4 rounded-xl bg-warning/5 border border-warning/20">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-warning" />
                <h4 className="text-sm font-medium text-foreground">Warnings</h4>
              </div>
              <ul className="space-y-2">
                {data.warnings.map((warning, index) => (
                  <li key={index} className="text-sm text-muted-foreground">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.missing_items.length > 0 && (
            <div className="p-4 rounded-xl bg-muted border border-border">
              <div className="flex items-center gap-2 mb-3">
                <XCircle className="w-4 h-4 text-muted-foreground" />
                <h4 className="text-sm font-medium text-foreground">Missing Items</h4>
              </div>
              <div className="flex flex-wrap gap-2">
                {data.missing_items.map((item, index) => (
                  <Badge key={index} variant="outline" className="text-xs">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {data.parsing_warnings.length > 0 && (
            <div className="p-4 rounded-xl bg-muted border border-border">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-muted-foreground" />
                <h4 className="text-sm font-medium text-foreground">Parsing Warnings</h4>
              </div>
              <ul className="space-y-1">
                {data.parsing_warnings.map((warning, index) => (
                  <li key={index} className="text-xs text-muted-foreground font-mono">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Task Breakdown */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Task Breakdown
        </h3>
        <div className="space-y-3">
          {data.task_breakdown.map((task) => (
            <div
              key={task.key}
              className="flex items-center gap-4 p-3 rounded-lg bg-secondary/30"
            >
              <div className="flex-shrink-0">
                {getStatusIcon(task.status)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">{task.label}</span>
                  <span className="text-xs text-muted-foreground">• {task.detail}</span>
                </div>
              </div>
              <div className="flex-shrink-0 text-xs text-muted-foreground font-mono">
                {(task.duration_ms / 1000).toFixed(2)}s
              </div>
              <div className="w-24 flex-shrink-0">
                <Progress 
                  value={(task.duration_ms / totalDuration) * 100} 
                  className="h-1.5"
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Transcript Discovery */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Transcript Discovery
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-4">
          <div className="text-center p-3 rounded-lg bg-secondary/50">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.pages_scanned}</div>
            <div className="text-xs text-muted-foreground">Pages Scanned</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-secondary/50">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.candidates_total}</div>
            <div className="text-xs text-muted-foreground">Candidates</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-secondary/50">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.transcript_like_count}</div>
            <div className="text-xs text-muted-foreground">Transcript-like</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-secondary/50">
            <div className="text-xl font-bold text-foreground">{data.transcript_discovery.match_filtered_count}</div>
            <div className="text-xs text-muted-foreground">Filtered</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-bullish/10">
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
          <div className="mt-4 p-3 rounded-lg bg-destructive/5 border border-destructive/20">
            <div className="text-xs font-medium text-destructive mb-1">Fetch Failures</div>
            <div className="text-xs text-muted-foreground">
              {data.transcript_discovery.fetch_failures.join(", ")}
            </div>
          </div>
        )}
      </div>

      {/* Fundamentals Validation */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Fundamentals Validation
        </h3>
        <div className="flex flex-wrap gap-2 mb-4">
          {data.fundamentals_validation.yahoo_source_used && (
            <Badge variant="outline" className="text-xs">Yahoo Finance</Badge>
          )}
          {data.fundamentals_validation.alpha_source_used && (
            <Badge variant="outline" className="text-xs">Alpha Vantage</Badge>
          )}
        </div>
        
        <div className="mb-4">
          <div className="text-xs text-muted-foreground mb-2">Compared Fields</div>
          <div className="flex flex-wrap gap-1">
            {data.fundamentals_validation.compared_fields.map((field) => (
              <Badge key={field} variant="secondary" className="text-xs font-mono">
                {field}
              </Badge>
            ))}
          </div>
        </div>

        {data.fundamentals_validation.notes.length > 0 && (
          <div className="p-3 rounded-lg bg-bullish/5 border border-bullish/20">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-bullish" />
              <span className="text-sm text-foreground">
                {data.fundamentals_validation.notes.join(" ")}
              </span>
            </div>
          </div>
        )}

        {data.fundamentals_validation.mismatches.length > 0 && (
          <div className="mt-4 rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-secondary/50">
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Field</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Yahoo</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Alpha</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Diff</th>
                </tr>
              </thead>
              <tbody>
                {data.fundamentals_validation.mismatches.map((mismatch) => (
                  <tr key={mismatch.key} className="border-t border-border">
                    <td className="px-3 py-2 font-mono text-foreground">{mismatch.key}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{mismatch.yahoo_value}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{mismatch.alpha_value}</td>
                    <td className="px-3 py-2 text-right text-warning font-mono">
                      {mismatch.relative_diff_pct.toFixed(1)}%
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
