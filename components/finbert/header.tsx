"use client"

import Link from "next/link"
import { Activity, BarChart3, FileText, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"

export function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo and Brand */}
          <div className="flex items-center gap-3">
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
          </div>

          {/* Navigation */}
          <nav className="hidden md:flex items-center gap-1">
            <Link 
              href="/" 
              className="px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary rounded-md transition-colors"
            >
              Analysis
            </Link>
            <Link 
              href="/charts-test" 
              className="px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md transition-colors"
            >
              Charts Test
            </Link>
          </nav>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="hidden sm:flex gap-2">
              <FileText className="w-4 h-4" />
              <span>Docs</span>
            </Button>
            <Button variant="ghost" size="icon" className="w-9 h-9">
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
    </header>
  )
}
