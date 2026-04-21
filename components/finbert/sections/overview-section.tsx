"use client"

import { CheckCircle2, TrendingUp, AlertTriangle, Target } from "lucide-react"
import { Progress } from "@/components/ui/progress"

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
      return TrendingUp
    case "evasiveness":
      return AlertTriangle
    case "outlook_strength":
      return Target
    default:
      return CheckCircle2
  }
}

export function OverviewSection({ data }: OverviewSectionProps) {
  return (
    <div className="space-y-8">
      {/* Executive Summary */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Executive Summary
        </h3>
        <p className="text-base text-foreground leading-relaxed">
          {data.executive_summary}
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {data.metrics.map((metric) => {
          const Icon = getMetricIcon(metric.key)
          const colorClass = getMetricColor(metric.key, metric.value)
          
          return (
            <div
              key={metric.key}
              className="p-4 rounded-xl bg-card border border-border"
            >
              <div className="flex items-center gap-2 mb-3">
                <Icon className={`w-4 h-4 ${colorClass}`} />
                <span className="text-xs text-muted-foreground font-medium">
                  {metric.label}
                </span>
              </div>
              <div className="flex items-end gap-2 mb-2">
                <span className={`text-3xl font-bold ${colorClass}`}>
                  {metric.value}
                </span>
                <span className="text-sm text-muted-foreground mb-1">/100</span>
              </div>
              <Progress 
                value={metric.value} 
                className="h-1.5"
              />
            </div>
          )
        })}
      </div>

      {/* Key Takeaways */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Key Takeaways
        </h3>
        <ul className="space-y-3">
          {data.key_takeaways.map((takeaway, index) => (
            <li key={index} className="flex gap-3">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-secondary flex items-center justify-center">
                <span className="text-xs font-medium text-muted-foreground">
                  {index + 1}
                </span>
              </div>
              <span className="text-sm text-foreground leading-relaxed pt-0.5">
                {takeaway}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "View Transcript Details", desc: "Speaker-level analysis", tab: "transcript" },
          { label: "Check Market Reaction", desc: "News & social sentiment", tab: "market" },
          { label: "Review Data Quality", desc: "Source reliability", tab: "audit" },
        ].map((action) => (
          <button
            key={action.tab}
            className="p-4 rounded-xl bg-secondary/50 border border-border hover:bg-secondary transition-colors text-left group"
          >
            <div className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
              {action.label}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {action.desc}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
