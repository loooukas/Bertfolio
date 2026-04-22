"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"

import { Header } from "@/components/finbert/header"
import { ReportView } from "@/components/finbert/report-view"
import { Button } from "@/components/ui/button"
import { adaptAnalysisResponseToUI } from "@/lib/finbert/adapters"
import { FinbertClientError, getCachedRun } from "@/lib/finbert/client"
import type { CachedRunResponse } from "@/lib/finbert/types"
import { DEFAULT_UI_SETTINGS, sanitizeUISettings, type UISettings } from "@/lib/finbert/ui-settings"

const UI_SETTINGS_STORAGE_KEY = "finbert-ui-settings-v2"

function formatRunTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.valueOf())) {
    return "Unknown"
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed)
}

function errorMessageFromUnknown(error: unknown): string {
  if (error instanceof FinbertClientError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return "Unable to load cached run."
}

export default function CachedRunDetailPage() {
  const params = useParams<{ ticker: string }>()
  const ticker = String(params.ticker || "").trim().toUpperCase()

  const [cachedRun, setCachedRun] = useState<CachedRunResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState("")
  const [uiSettings, setUiSettings] = useState<UISettings>(DEFAULT_UI_SETTINGS)

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

  useEffect(() => {
    if (!ticker) {
      setError("Ticker is missing from URL.")
      setCachedRun(null)
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)
    setError("")

    void getCachedRun(ticker)
      .then((payload) => {
        if (cancelled) {
          return
        }
        setCachedRun(payload)
      })
      .catch((nextError) => {
        if (cancelled) {
          return
        }
        setCachedRun(null)
        setError(errorMessageFromUnknown(nextError))
      })
      .finally(() => {
        if (cancelled) {
          return
        }
        setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [ticker])

  const report = useMemo(() => {
    if (!cachedRun) {
      return null
    }
    return adaptAnalysisResponseToUI(cachedRun.result)
  }, [cachedRun])

  return (
    <div className="min-h-screen flex flex-col">
      <Header settings={uiSettings} onSettingsChange={(next) => setUiSettings(sanitizeUISettings(next))} />

      <main className="max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-foreground">{ticker || "Cached Run"}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {cachedRun
                  ? `Cached on ${formatRunTime(cachedRun.updated_at)} • ${cachedRun.analysis_version || "Unknown version"}`
                  : "Loading cached report..."}
              </p>
            </div>
            <Button asChild variant="outline">
              <Link href="/cache-runs">Back to Cache Runs</Link>
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="rounded-xl border border-border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
            Loading cached report...
          </div>
        ) : null}

        {!isLoading && error ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {!isLoading && !error && report ? <ReportView report={report} settings={uiSettings} /> : null}
      </main>
    </div>
  )
}
