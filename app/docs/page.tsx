import Link from "next/link"

export default function DocsPage() {
  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-10 sm:px-6 lg:px-8">
      <section className="space-y-3 rounded-xl border border-border bg-card p-6">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">Bertfolio Docs</h1>
        <p className="text-sm text-muted-foreground">
          Local runbook and product behavior notes for the root Next.js app + FastAPI backend.
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Methodology</h2>
        <p className="text-sm text-muted-foreground">
          Deep dive on every calculated number, score thresholds, and the exact weighting formulas used in the app.
        </p>
        <Link
          href="/docs/model-methodology"
          className="inline-flex items-center rounded-md border border-border bg-secondary/40 px-3 py-2 text-sm text-foreground transition-colors hover:bg-secondary"
        >
          Open Model Methodology Guide
        </Link>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Run</h2>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-sm text-foreground">
          pnpm dev
        </div>
        <p className="text-sm text-muted-foreground">
          Starts both services together: Next.js on <code>127.0.0.1:3000</code> and FastAPI on{" "}
          <code>127.0.0.1:8000</code>.
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Latest UI Behavior</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>The analyze hero/input panel fades away once a run starts and stays hidden while viewing results.</li>
          <li>Clicking the top-left Bertfolio brand resets to a fresh homepage state so you can analyze another ticker.</li>
          <li>Transcript key quotes now attempt speaker attribution from real transcript evidence before fallback labels.</li>
          <li>Speaker cards open a modal showing every mention by transcript, with per-transcript mention-count buttons.</li>
          <li>Speaker/block diagnostics include analysts + management, but company-facing transcript aggregates are management-only.</li>
          <li>Transcript table filters now live by the table and all table headers are sortable ascending/descending.</li>
          <li>Fundamentals values auto-scale to K/M/B/T for cards, charts, and tables.</li>
        </ul>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Feed Quality Controls</h2>
        <p className="text-sm text-muted-foreground">
          News and social pipelines now fetch larger pools, dedupe, relevance-rank, and keep the highest quality top set.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <p className="font-mono text-xs text-muted-foreground">NEWS_LIMIT</p>
            <p className="font-mono text-sm text-foreground">50</p>
          </div>
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <p className="font-mono text-xs text-muted-foreground">NEWS_POOL_SIZE</p>
            <p className="font-mono text-sm text-foreground">240</p>
          </div>
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <p className="font-mono text-xs text-muted-foreground">SOCIAL_LIMIT</p>
            <p className="font-mono text-sm text-foreground">50</p>
          </div>
          <div className="rounded-md border border-border bg-secondary/40 p-3">
            <p className="font-mono text-xs text-muted-foreground">SOCIAL_POOL_SIZE</p>
            <p className="font-mono text-sm text-foreground">260</p>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          Social sources are currently Reddit + Stocktwits with source balancing; X/LinkedIn require separate provider APIs and are not enabled by default.
        </p>
        <p className="text-sm text-muted-foreground">
          Runtime scrape depth and source toggles can now be changed in the top-right Settings modal per analysis run.
        </p>
      </section>
    </main>
  )
}
