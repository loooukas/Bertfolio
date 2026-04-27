"use client"

import { useEffect, useRef, useState } from "react"
import { Header } from "@/components/finbert/header"
import { TickerInput } from "@/components/finbert/ticker-input"
import { JobProgress } from "@/components/finbert/job-progress"
import { ReportView } from "@/components/finbert/report-view"
import { EmptyState } from "@/components/finbert/empty-state"
import { adaptAnalysisResponseToUI, adaptJobProgress, DEFAULT_PROGRESS } from "@/lib/finbert/adapters"
import {
  DEFAULT_UI_SETTINGS,
  pollIntervalMs,
  sanitizeAnalyzeRunOverrides,
  sanitizeUISettings,
  type UISettings,
} from "@/lib/finbert/ui-settings"
import { cn } from "@/lib/utils"
import {
  createAnalyzeJob,
  FinbertClientError,
  getAnalyzeJob,
  getAnalyzeResult,
} from "@/lib/finbert/client"
import type { BackendJobStatus, UIReportModel } from "@/lib/finbert/types"

type PageStatus = BackendJobStatus | "idle"

const UI_SETTINGS_STORAGE_KEY = "bertfolio-ui-settings-v1"

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function errorMessageFromUnknown(error: unknown): string {
  if (error instanceof FinbertClientError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return "Unable to complete analysis. Please try again."
}

export default function HomePage() {
  const [ticker, setTicker] = useState("")
  const [jobStatus, setJobStatus] = useState<PageStatus>("idle")
  const [progress, setProgress] = useState(DEFAULT_PROGRESS)
  const [report, setReport] = useState<UIReportModel | null>(null)
  const [errorMessage, setErrorMessage] = useState("")
  const [showReport, setShowReport] = useState(false)
  const [uiSettings, setUiSettings] = useState<UISettings>(DEFAULT_UI_SETTINGS)
  const latestRunRef = useRef(0)

  useEffect(() => {
    return () => {
      latestRunRef.current += 1
    }
  }, [])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(UI_SETTINGS_STORAGE_KEY)
      if (!raw) {
        return
      }
      const parsed = JSON.parse(raw) as Partial<UISettings>
      setUiSettings(sanitizeUISettings(parsed))
    } catch {
      setUiSettings(DEFAULT_UI_SETTINGS)
    }
  }, [])

  useEffect(() => {
    try {
      window.localStorage.setItem(UI_SETTINGS_STORAGE_KEY, JSON.stringify(uiSettings))
    } catch {
      // no-op
    }
  }, [uiSettings])

  const handleAnalyze = async (inputTicker: string) => {
    const normalizedTicker = inputTicker.trim().toUpperCase()
    if (!normalizedTicker) {
      return
    }

    const runToken = latestRunRef.current + 1
    latestRunRef.current = runToken

    setTicker(normalizedTicker)
    setJobStatus("queued")
    setProgress(DEFAULT_PROGRESS)
    setErrorMessage("")
    setReport(null)
    setShowReport(false)

    try {
      const createdJob = await createAnalyzeJob(normalizedTicker, sanitizeAnalyzeRunOverrides(uiSettings.run_overrides))
      if (latestRunRef.current !== runToken) {
        return
      }

      setJobStatus(createdJob.status)
      setProgress(adaptJobProgress(createdJob.progress))

      let latestJob = createdJob
      while (latestRunRef.current === runToken && (latestJob.status === "queued" || latestJob.status === "running")) {
        await sleep(pollIntervalMs(uiSettings.polling_mode))
        if (latestRunRef.current !== runToken) {
          return
        }

        latestJob = await getAnalyzeJob(createdJob.job_id)
        if (latestRunRef.current !== runToken) {
          return
        }

        setJobStatus(latestJob.status)
        setProgress(adaptJobProgress(latestJob.progress))

        if (latestJob.status === "failed") {
          throw new Error(latestJob.error || `Analysis failed for ${normalizedTicker}.`)
        }
      }

      if (latestRunRef.current !== runToken) {
        return
      }

      if (latestJob.status !== "completed") {
        throw new Error("Analysis did not complete successfully.")
      }

      const completedJob = await getAnalyzeResult(createdJob.job_id)
      if (latestRunRef.current !== runToken) {
        return
      }
      if (!completedJob.result) {
        throw new Error("Analysis completed without a result payload.")
      }

      setReport(adaptAnalysisResponseToUI(completedJob.result))
      setJobStatus("completed")
      setShowReport(true)
    } catch (error) {
      if (latestRunRef.current !== runToken) {
        return
      }
      setJobStatus("failed")
      setReport(null)
      setShowReport(false)
      setErrorMessage(errorMessageFromUnknown(error))
    }
  }

  const handleReset = () => {
    latestRunRef.current += 1
    setTicker("")
    setJobStatus("idle")
    setProgress(DEFAULT_PROGRESS)
    setErrorMessage("")
    setReport(null)
    setShowReport(false)
  }

  const showAnalyzeInput = jobStatus === "idle" || jobStatus === "failed"

  return (
    <div className="min-h-screen flex flex-col">
      <Header
        onHomeClick={handleReset}
        settings={uiSettings}
        onSettingsChange={(next) => setUiSettings(sanitizeUISettings(next))}
      />
      
      <main className="flex-1">
        {/* Input Section */}
        <section
          className={cn(
            "border-b transition-all duration-300 ease-out",
            showAnalyzeInput
              ? "max-h-[520px] border-border opacity-100"
              : "pointer-events-none max-h-0 overflow-hidden border-transparent opacity-0",
          )}
        >
          <div className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
            <TickerInput 
              onAnalyze={handleAnalyze} 
              isLoading={jobStatus === "running" || jobStatus === "queued"}
              currentTicker={ticker}
              onReset={handleReset}
            />
          </div>
        </section>

        {/* Progress / Report Section */}
        <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {jobStatus === "idle" && <EmptyState />}
          
          {(jobStatus === "queued" || jobStatus === "running") && (
            <JobProgress 
              ticker={ticker} 
              progress={progress} 
              status={jobStatus}
            />
          )}
          
          {jobStatus === "completed" && showReport && report && (
            <ReportView report={report} settings={uiSettings} />
          )}
          
          {jobStatus === "failed" && (
            <div className="text-center py-12">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-destructive/10 mb-4">
                <svg className="w-8 h-8 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-foreground mb-2">Analysis Failed</h3>
              <p className="text-muted-foreground mb-4">
                {errorMessage || `Unable to complete analysis for ${ticker}. Please try again.`}
              </p>
              <button
                onClick={handleReset}
                className="text-sm text-primary hover:underline"
              >
                Start new analysis
              </button>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
