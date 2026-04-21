"use client"

import { CheckCircle2, Circle, Loader2, AlertCircle } from "lucide-react"
import { Progress } from "@/components/ui/progress"

interface Stage {
  key: string
  label: string
  status: "pending" | "loading" | "done" | "error"
  progress: number
  message: string
  duration_ms?: number | null
}

interface JobProgressProps {
  ticker: string
  progress: {
    percent: number
    active_stage: string
    active_subtask: string
    stages: Stage[]
  }
  status: "queued" | "running" | "completed" | "failed"
}

export function JobProgress({ ticker, progress, status }: JobProgressProps) {
  const getStageIcon = (stage: Stage) => {
    switch (stage.status) {
      case "done":
        return <CheckCircle2 className="w-5 h-5 text-bullish" />
      case "loading":
        return <Loader2 className="w-5 h-5 text-primary animate-spin" />
      case "error":
        return <AlertCircle className="w-5 h-5 text-destructive" />
      default:
        return <Circle className="w-5 h-5 text-muted-foreground/40" />
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-secondary border border-border mb-4">
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
          <span className="text-sm font-medium text-foreground">
            {status === "queued" ? "Queued" : "Processing"}
          </span>
        </div>
        <h2 className="text-2xl font-semibold text-foreground">
          Analyzing <span className="font-mono text-primary">{ticker}</span>
        </h2>
        <p className="mt-2 text-muted-foreground">
          {progress.active_subtask || "Preparing analysis pipeline..."}
        </p>
      </div>

      {/* Overall Progress */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">Overall Progress</span>
          <span className="text-sm font-mono text-foreground">{Math.round(progress.percent)}%</span>
        </div>
        <Progress value={progress.percent} className="h-2" />
      </div>

      {/* Stage List */}
      <div className="space-y-1">
        {progress.stages.map((stage, index) => (
          <div
            key={stage.key}
            className={`flex items-center gap-4 p-4 rounded-lg transition-colors ${
              stage.status === "loading"
                ? "bg-secondary border border-border"
                : stage.status === "done"
                ? "bg-secondary/30"
                : "bg-transparent"
            }`}
          >
            {/* Stage Icon */}
            <div className="flex-shrink-0">
              {getStageIcon(stage)}
            </div>

            {/* Stage Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-sm font-medium ${
                  stage.status === "pending" ? "text-muted-foreground" : "text-foreground"
                }`}>
                  {stage.label}
                </span>
                {stage.status === "loading" && (
                  <span className="text-xs text-muted-foreground">
                    {stage.message}
                  </span>
                )}
              </div>
              {stage.status === "loading" && (
                <div className="mt-2">
                  <Progress value={stage.progress * 100} className="h-1" />
                </div>
              )}
            </div>

            {/* Duration */}
            {stage.duration_ms && stage.status === "done" && (
              <div className="flex-shrink-0 text-xs text-muted-foreground font-mono">
                {(stage.duration_ms / 1000).toFixed(1)}s
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="mt-8 text-center">
        <p className="text-xs text-muted-foreground">
          Report will be displayed automatically when processing completes.
        </p>
      </div>
    </div>
  )
}
