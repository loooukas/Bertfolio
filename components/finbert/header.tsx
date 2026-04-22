"use client"

import Link from "next/link"
import { useMemo, useState } from "react"
import { usePathname } from "next/navigation"
import { Activity, FileText, Settings, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  DEFAULT_UI_SETTINGS,
  sanitizeAnalyzeRunOverrides,
  sanitizeUISettings,
  type AnalyzeRunOverrides,
  type PollingMode,
  type UISettings,
} from "@/lib/finbert/ui-settings"

interface HeaderProps {
  onHomeClick?: () => void
  settings?: UISettings
  onSettingsChange?: (next: UISettings) => void
}

function pollingModeLabel(mode: PollingMode): string {
  if (mode === "fast") return "Fast (lower latency)"
  if (mode === "eco") return "Eco (lower CPU usage)"
  return "Balanced"
}

export function Header({ onHomeClick, settings, onSettingsChange }: HeaderProps) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const pathname = usePathname()
  const effectiveSettings = useMemo(() => sanitizeUISettings(settings), [settings])
  const onCacheRunsPage = pathname.startsWith("/cache-runs")

  const updateSettings = (patch: Partial<UISettings>) => {
    if (!onSettingsChange) {
      return
    }
    onSettingsChange(sanitizeUISettings({ ...effectiveSettings, ...patch }))
  }

  const updateRunSettings = (patch: Partial<AnalyzeRunOverrides>) => {
    if (!onSettingsChange) {
      return
    }
    onSettingsChange(
      sanitizeUISettings({
        ...effectiveSettings,
        run_overrides: sanitizeAnalyzeRunOverrides({
          ...effectiveSettings.run_overrides,
          ...patch,
        }),
      }),
    )
  }

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo and Brand */}
          <button
            type="button"
            onClick={onHomeClick}
            className="flex items-center gap-3 rounded-md px-1 py-1 text-left transition-colors hover:bg-secondary/50"
          >
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary">
              <Activity className="w-5 h-5 text-primary-foreground" />
            </div>
            <div className="flex flex-col">
              <span className="text-base font-semibold text-foreground tracking-tight">
                FinBERT
              </span>
              <span className="text-xs text-muted-foreground -mt-0.5">
                Earnings Signals
              </span>
            </div>
          </button>

          {/* Navigation */}
          <nav className="hidden md:flex items-center gap-1">
            {onHomeClick ? (
              <button
                type="button"
                onClick={onHomeClick}
                className={`px-3 py-2 text-sm font-medium hover:bg-secondary rounded-md transition-colors ${
                  onCacheRunsPage ? "text-muted-foreground hover:text-foreground" : "text-foreground"
                }`}
              >
                Analysis
              </button>
            ) : (
              <Link
                href="/"
                className={`px-3 py-2 text-sm font-medium hover:bg-secondary rounded-md transition-colors ${
                  onCacheRunsPage ? "text-muted-foreground hover:text-foreground" : "text-foreground"
                }`}
              >
                Analysis
              </Link>
            )}
            <Link
              href="/cache-runs"
              className={`px-3 py-2 text-sm font-medium hover:bg-secondary rounded-md transition-colors ${
                onCacheRunsPage ? "text-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Cache Runs
            </Link>
          </nav>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:flex gap-2">
              <Link href="/docs">
              <FileText className="w-4 h-4" />
              <span>Docs</span>
              </Link>
            </Button>
            <Button variant="ghost" size="icon" className="w-9 h-9" onClick={() => setSettingsOpen(true)}>
              <Settings className="w-4 h-4" />
              <span className="sr-only">Settings</span>
            </Button>
            <div className="hidden sm:block w-px h-6 bg-border mx-1" />
            <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-bullish opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-bullish"></span>
                </span>
                <span>API Online</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent showCloseButton={false} className="h-[85vh] max-h-[85vh] w-[94vw] max-w-3xl overflow-hidden p-0">
          <div className="flex h-full min-h-0 flex-col">
            <div className="sticky top-0 z-20 border-b border-border bg-background px-6 py-4">
              <div className="flex items-start justify-between gap-3">
                <DialogHeader className="pr-2">
                  <DialogTitle>Run & Display Settings</DialogTitle>
                  <DialogDescription>
                    Adjust how often the app polls the backend and how dense the report layout renders.
                  </DialogDescription>
                </DialogHeader>
                <DialogClose asChild>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                    <X className="h-4 w-4" />
                    <span className="sr-only">Close settings</span>
                  </Button>
                </DialogClose>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-4">
              <div className="space-y-5 pb-2">
            <div className="space-y-2">
              <Label htmlFor="polling-mode">Polling Mode</Label>
              <Select
                value={effectiveSettings.polling_mode}
                onValueChange={(value) =>
                  updateSettings({
                    polling_mode: value as PollingMode,
                  })
                }
              >
                <SelectTrigger id="polling-mode" className="w-full">
                  <SelectValue placeholder="Select polling mode" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="fast">{pollingModeLabel("fast")}</SelectItem>
                  <SelectItem value="balanced">{pollingModeLabel("balanced")}</SelectItem>
                  <SelectItem value="eco">{pollingModeLabel("eco")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-3 rounded-lg border border-border p-3">
              <div className="text-sm font-medium text-foreground">Data Collection (Per Run)</div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <NumberInput
                  label="News Pool"
                  value={effectiveSettings.run_overrides.news_pool_size}
                  min={80}
                  max={1000}
                  onChange={(value) => updateRunSettings({ news_pool_size: value })}
                />
                <NumberInput
                  label="Social Pool"
                  value={effectiveSettings.run_overrides.social_pool_size}
                  min={80}
                  max={1000}
                  onChange={(value) => updateRunSettings({ social_pool_size: value })}
                />
                <NumberInput
                  label="News Kept"
                  value={effectiveSettings.run_overrides.news_limit}
                  min={10}
                  max={120}
                  onChange={(value) => updateRunSettings({ news_limit: value })}
                />
                <NumberInput
                  label="Social Kept"
                  value={effectiveSettings.run_overrides.social_limit}
                  min={10}
                  max={120}
                  onChange={(value) => updateRunSettings({ social_limit: value })}
                />
                <NumberInput
                  label="News Lookback Days"
                  value={effectiveSettings.run_overrides.news_lookback_days}
                  min={3}
                  max={365}
                  onChange={(value) => updateRunSettings({ news_lookback_days: value })}
                />
                <NumberInput
                  label="Social Lookback Days"
                  value={effectiveSettings.run_overrides.social_lookback_days}
                  min={3}
                  max={365}
                  onChange={(value) => updateRunSettings({ social_lookback_days: value })}
                />
              </div>
            </div>

            <div className="space-y-3 rounded-lg border border-border p-3">
              <div className="text-sm font-medium text-foreground">Score Weights (%)</div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <NumberInput
                  label="Transcript Weight"
                  value={effectiveSettings.run_overrides.score_weight_transcript}
                  min={0}
                  max={100}
                  onChange={(value) => updateRunSettings({ score_weight_transcript: value })}
                />
                <NumberInput
                  label="Fundamentals Weight"
                  value={effectiveSettings.run_overrides.score_weight_fundamentals}
                  min={0}
                  max={100}
                  onChange={(value) => updateRunSettings({ score_weight_fundamentals: value })}
                />
                <NumberInput
                  label="News Weight"
                  value={effectiveSettings.run_overrides.score_weight_news}
                  min={0}
                  max={100}
                  onChange={(value) => updateRunSettings({ score_weight_news: value })}
                />
                <NumberInput
                  label="Social Weight"
                  value={effectiveSettings.run_overrides.score_weight_social}
                  min={0}
                  max={100}
                  onChange={(value) => updateRunSettings({ score_weight_social: value })}
                />
              </div>
              <div className="text-[11px] text-muted-foreground">
                Weights are normalized automatically; they do not need to sum to 100.
              </div>
            </div>

            <div className="space-y-3 rounded-lg border border-border p-3">
              <div className="text-sm font-medium text-foreground">Feed Sources</div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <SourceToggle
                  label="Alpha Vantage News"
                  checked={effectiveSettings.run_overrides.news_enable_alpha_vantage}
                  onCheckedChange={(checked) => updateRunSettings({ news_enable_alpha_vantage: checked })}
                />
                <SourceToggle
                  label="Yahoo Finance News"
                  checked={effectiveSettings.run_overrides.news_enable_yahoo_finance}
                  onCheckedChange={(checked) => updateRunSettings({ news_enable_yahoo_finance: checked })}
                />
                <SourceToggle
                  label="Reddit Social"
                  checked={effectiveSettings.run_overrides.social_enable_reddit}
                  onCheckedChange={(checked) => updateRunSettings({ social_enable_reddit: checked })}
                />
                <SourceToggle
                  label="Stocktwits Social"
                  checked={effectiveSettings.run_overrides.social_enable_stocktwits}
                  onCheckedChange={(checked) => updateRunSettings({ social_enable_stocktwits: checked })}
                />
              </div>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <div className="text-sm font-medium text-foreground">Use Analysis Cache</div>
                <div className="text-xs text-muted-foreground">
                  Reuse the full cached report when available. Turn off to recompute and overwrite the cache.
                </div>
              </div>
              <Switch
                checked={effectiveSettings.run_overrides.use_cache}
                onCheckedChange={(checked) => updateRunSettings({ use_cache: checked })}
              />
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg border border-border p-3">
                <div>
                  <div className="text-sm font-medium text-foreground">Two-column market + key quotes</div>
                  <div className="text-xs text-muted-foreground">
                    Apply a denser 2-column layout to market cards and transcript key quotes.
                  </div>
                </div>
                <Switch
                  checked={effectiveSettings.market_columns === 2 && effectiveSettings.quote_columns === 2}
                  onCheckedChange={(checked) =>
                    updateSettings({
                      market_columns: checked ? 2 : 1,
                      quote_columns: checked ? 2 : 1,
                    })
                  }
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border p-3">
                <div>
                  <div className="text-sm font-medium text-foreground">Auto-open Data Audit on warnings</div>
                  <div className="text-xs text-muted-foreground">
                    Jump to Data Audit first when the report has warnings/failures.
                  </div>
                </div>
                <Switch
                  checked={effectiveSettings.auto_open_audit_on_warnings}
                  onCheckedChange={(checked) => updateSettings({ auto_open_audit_on_warnings: checked })}
                />
              </div>
            </div>
              </div>
            </div>

            <div className="sticky bottom-0 z-20 flex items-center justify-between border-t border-border bg-background px-6 py-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  if (!onSettingsChange) {
                    return
                  }
                  onSettingsChange(DEFAULT_UI_SETTINGS)
                }}
              >
                Reset Defaults
              </Button>
              <Button type="button" onClick={() => setSettingsOpen(false)}>
                Done
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </header>
  )
}

function NumberInput({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => {
          const next = Number(event.target.value)
          if (!Number.isFinite(next)) {
            return
          }
          onChange(clampInt(next, min, max))
        }}
      />
      <div className="text-[11px] text-muted-foreground">
        Range {min}-{max}
      </div>
    </div>
  )
}

function SourceToggle({
  label,
  checked,
  onCheckedChange,
}: {
  label: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between rounded-md border border-border bg-secondary/20 px-3 py-2">
      <div className="text-xs text-foreground">{label}</div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  )
}

function clampInt(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(value)))
}
