"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { Clock3, Database, RefreshCw, Trash2 } from "lucide-react"

import { Header } from "@/components/finbert/header"
import { Button } from "@/components/ui/button"
import { FinbertClientError, deleteCachedRun, getCacheRuns } from "@/lib/finbert/client"
import type { CacheRunSummary } from "@/lib/finbert/types"
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
  return "Unable to load cache runs."
}

export default function CacheRunsPage() {
  const [runs, setRuns] = useState<CacheRunSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState("")
  const [deletingTicker, setDeletingTicker] = useState<string | null>(null)
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

  const refreshRuns = useCallback(async () => {
    setIsLoading(true)
    setError("")
    try {
      const payload = await getCacheRuns()
      setRuns(payload.runs)
    } catch (nextError) {
      setError(errorMessageFromUnknown(nextError))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshRuns()
  }, [refreshRuns])

  const handleDelete = async (ticker: string) => {
    const confirmed = window.confirm(`Delete cached run for ${ticker}?`)
    if (!confirmed) {
      return
    }

    setDeletingTicker(ticker)
    setError("")
    try {
      await deleteCachedRun(ticker)
      setRuns((current) => current.filter((row) => row.ticker !== ticker))
    } catch (nextError) {
      setError(errorMessageFromUnknown(nextError))
    } finally {
      setDeletingTicker(null)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header settings={uiSettings} onSettingsChange={(next) => setUiSettings(sanitizeUISettings(next))} />

      <main className="max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Database className="h-4 w-4" />
              <span>Cached Analysis Runs</span>
            </div>
            <h1 className="mt-2 text-2xl font-semibold text-foreground">Open Saved Reports Instantly</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Browse local cached runs by ticker, transcript set, and run timestamp.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" onClick={() => void refreshRuns()} disabled={isLoading}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
            <Button asChild>
              <Link href="/">New Analysis</Link>
            </Button>
          </div>
        </div>

        {error ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {isLoading ? (
          <div className="rounded-xl border border-border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
            Loading cached runs...
          </div>
        ) : runs.length === 0 ? (
          <div className="rounded-xl border border-border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
            No cached runs found. Run an analysis first to populate cache.
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map((run) => (
              <div
                key={run.ticker}
                className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold text-foreground">{run.ticker}</h2>
                    <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                      {run.analysis_version || "Unknown version"}
                    </span>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Transcripts: {run.transcript_labels.length > 0 ? run.transcript_labels.join(", ") : `${run.transcripts_found} found`}
                  </div>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock3 className="h-3.5 w-3.5" />
                    <span>{formatRunTime(run.updated_at)}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button asChild>
                    <Link href={`/cache-runs/${encodeURIComponent(run.ticker)}`}>Open</Link>
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void handleDelete(run.ticker)}
                    disabled={deletingTicker === run.ticker}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    {deletingTicker === run.ticker ? "Deleting" : "Delete"}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
