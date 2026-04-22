"use client"

import { CheckCircle2, TrendingUp, AlertTriangle, Target, Info } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

interface Metric {
  key: string
  label: string
  value: number
}

interface OverviewData {
  stance_label: string
  executive_summary: string
  key_takeaways: string[]
  metrics: Metric[]
}

interface OverviewSectionProps {
  data: OverviewData
  onNavigate?: (tab: "transcript" | "market" | "fundamentals") => void
}

const getMetricColor = (key: string, value: number) => {
  if (key === "evasiveness") {
    return value > 40 ? "text-bearish" : value > 25 ? "text-neutral" : "text-bullish"
  }
  return value > 70 ? "text-bullish" : value > 50 ? "text-neutral" : "text-bearish"
}

const getMetricIcon = (key: string) => {
  switch (key) {
    case "confidence":
    case "management_confidence":
      return TrendingUp
    case "evasiveness":
      return AlertTriangle
    case "outlook_strength":
    case "forward_looking_strength":
      return Target
    default:
      return CheckCircle2
  }
}

function metricTooltipCopy(key: string): string {
  switch (key) {
    case "management_confidence":
    case "confidence":
      return "Higher when language is concrete and quantified, with fewer hedges like may, might, roughly, or at this time."
    case "evasiveness":
      return "Higher when responses contain more hedge or deferral cues such as may, could, subject to, or cannot comment."
    case "outlook_strength":
    case "forward_looking_strength":
      return "Higher when forward terms are frequent, including guidance, expect, forecast, pipeline, ramp, and next quarter."
    case "transcript_coverage":
      return "Portion of requested transcript quarters successfully found and normalized in this run."
    default:
      return "Communication-quality and transcript-derived signal, scaled to 0-100 for comparability."
  }
}

function metricContext(key: string, value: number): string {
  if (key === "evasiveness") {
    if (value <= 28) return "Low Evasion"
    if (value <= 48) return "Moderate Evasion"
    return "High Evasion"
  }
  if (key === "outlook_strength" || key === "forward_looking_strength") {
    if (value <= 22) return "Conservative Outlook"
    if (value <= 45) return "Measured Outlook"
    return "Strong Outlook"
  }
  if (key === "transcript_coverage") {
    if (value < 50) return "Thin Coverage"
    if (value < 90) return "Partial Coverage"
    return "Full Coverage"
  }
  if (value < 45) return "Lower Confidence"
  if (value < 65) return "Moderate Confidence"
  return "High Confidence"
}

export function OverviewSection({ data, onNavigate }: OverviewSectionProps) {
  const summarySentences = data.executive_summary
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)

  return (
    <TooltipProvider>
      <div className="space-y-8">
        {/* Metrics Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {data.metrics.map((metric) => {
            const Icon = getMetricIcon(metric.key)
            const colorClass = getMetricColor(metric.key, metric.value)
            const tooltip = metricTooltipCopy(metric.key)
            const context = metricContext(metric.key, metric.value)

            return (
              <div key={metric.key} className="p-4 rounded-xl bg-card border border-border">
                <div className="flex items-center gap-2 mb-3">
                  <Icon className={`w-4 h-4 ${colorClass}`} />
                  <span className="text-xs text-muted-foreground font-medium">{metric.label}</span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button type="button" className="text-muted-foreground/70 hover:text-foreground">
                        <Info className="h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs text-xs">{tooltip}</TooltipContent>
                  </Tooltip>
                </div>
                <div className="mb-2 flex items-end gap-2">
                  <span className={`text-3xl font-bold ${colorClass}`}>{metric.value}</span>
                  <span className="mb-1 text-sm text-muted-foreground">/100</span>
                </div>
                <Progress value={metric.value} className="h-1.5" />
                <div className="mt-2 text-[11px] leading-4 text-muted-foreground">
                  <span className="font-medium text-foreground/90">{context}</span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Executive Summary */}
        {summarySentences.length > 0 && (
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">Executive Summary</h3>
            <div className="space-y-2">
              {summarySentences.map((sentence, index) => (
                <p key={`${index}-${sentence.slice(0, 12)}`} className="text-base leading-relaxed text-foreground">
                  {sentence}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Key Takeaways */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-muted-foreground">Key Takeaways</h3>
          <ul className="space-y-3">
            {data.key_takeaways.map((takeaway, index) => (
              <li key={index} className="flex gap-3">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-secondary">
                  <span className="text-xs font-medium text-muted-foreground">{index + 1}</span>
                </div>
                <span className="pt-0.5 text-sm leading-relaxed text-foreground">{takeaway}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[
            { label: "View Transcript Details", desc: "Speaker-level analysis", tab: "transcript" },
            { label: "Check Market Reaction", desc: "News & social sentiment", tab: "market" },
            { label: "Review Fundamentals", desc: "Valuation, growth, analyst context", tab: "fundamentals" },
          ].map((action) => (
            <button
              key={action.tab}
              type="button"
              onClick={() => onNavigate?.(action.tab as "transcript" | "market" | "fundamentals")}
              className="group rounded-xl border border-border bg-secondary/50 p-4 text-left transition-colors hover:bg-secondary"
            >
              <div className="text-sm font-medium text-foreground transition-colors group-hover:text-primary">{action.label}</div>
              <div className="mt-0.5 text-xs text-muted-foreground">{action.desc}</div>
            </button>
          ))}
        </div>
      </div>
    </TooltipProvider>
  )
}
