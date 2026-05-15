# Archived Charts Test Pack

This archive preserves the removed charts test page plus the UI dependencies and style tokens that controlled its look.

## Archived from

- Page source commit: `36ca8de`
- Original route path: `app/charts-test/page.tsx`

## Included files

- `app/page.tsx` (the charts test page)
- `components/ui/button.tsx` (button styling used by page header/back button)
- `components/ui/badge.tsx` (badge styling used in header)
- `styles/globals.snapshot.css` (theme/token snapshot used by chart colors and card styles)

## Why this is not live

- The files are stored under `docs/archive/` and are not part of Next.js route resolution.
- Nothing in the live app imports these archived files.

## Reuse checklist for another repo

1. Copy `app/page.tsx` into your target route (example: `app/charts-test/page.tsx`).
2. Copy/merge `components/ui/button.tsx` and `components/ui/badge.tsx` if missing.
3. Ensure CSS variables exist (from `styles/globals.snapshot.css`):
- `--background`, `--card`, `--border`, `--foreground`, `--muted-foreground`
- `--bullish`, `--bearish`, `--neutral`
- `--chart-1` through `--chart-5`
4. Ensure deps are installed:
- `recharts`
- `lucide-react`
- `@radix-ui/react-slot`
- `class-variance-authority`
5. Ensure your alias config supports `@/components/...` and `@/lib/utils`.

## Notes

- The page uses synthetic data by design.
- The visual quality comes from both Recharts config and theme tokens; copy both, not just the TSX.
