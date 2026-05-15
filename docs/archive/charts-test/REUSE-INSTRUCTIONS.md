# Charts Test Pack - Exact Reuse Instructions

This is a drop-in pack of exactly what is needed to recreate the archived charts test page and styling.

## Copy these files into your target repo

- `docs/archive/charts-test/app/page.tsx` -> `app/charts-test/page.tsx`
- `docs/archive/charts-test/components/ui/button.tsx` -> `components/ui/button.tsx`
- `docs/archive/charts-test/components/ui/badge.tsx` -> `components/ui/badge.tsx`
- `docs/archive/charts-test/lib/utils.ts` -> `lib/utils.ts`
- `docs/archive/charts-test/styles/minimal-chart-theme.css` -> merge into your global CSS

## Install packages

```bash
pnpm add recharts lucide-react @radix-ui/react-slot class-variance-authority clsx tailwind-merge
```

## Required setup details

- Tailwind utility classes are used heavily; this page assumes Tailwind is active.
- Import path alias `@/` must resolve to repo root paths (or rewrite imports).
- Include the CSS variables from `minimal-chart-theme.css` in your global stylesheet.

## What is intentionally not included

- Entire site globals or app-wide CSS.
- Unrelated components.
- Any backend code.

This pack is scoped to the chart page look + behavior only.
