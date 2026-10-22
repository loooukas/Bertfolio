# October 2026 dependency security update

The production lockfile now resolves Next.js to 16.4.1, sharp to 0.35.5, and `source-map-js` to 1.2.2. These updates address the [Next.js October 14 security update](https://nextjs.org/blog/nextjs-security-update-october-14-2026), including the [React Server Components typed-array RCE](https://github.com/vercel/next.js/security/advisories/GHSA-673q-mjm6-r5xr), [Image Optimization SVG RCE](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw), and [Server Actions denial of service](https://github.com/vercel/next.js/security/advisories/GHSA-p3m5-59mp-jv5r). The other targeted advisories are [sharp](https://github.com/advisories/GHSA-wq5f-xc86-pv6w) and [source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

Validation used `pnpm install --lockfile-only --ignore-scripts --frozen-lockfile` and `pnpm audit --prod --json`. The final production audit reports seven high and two moderate findings, with no critical findings. High findings remain in `browserslist`, `nanoid`, and `postcss`. Lockfile validation passed; builds and runtime, Vercel Preview, and production behavior were not tested.

## Python certificate bundle

Both Python dependency manifests now require `certifi>=2026.10.19`. The [certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2) marks earlier versions affected because they trust emSign roots whose intermediates were revoked after key compromise. The advisory lists 2026.10.18 as the patched version. The 2026.10.19 release is compatible with Python 3.9.

This updates dependency declarations only. The canonical checkout's existing virtual environment was Python 3.9.6 with certifi 2026.2.25; this change does not update that environment. No project Python, pip, package imports, installation, or tests were run for this patch.

The Python 3.9 constraint also limits separate updates. urllib3 1.26.20 is in current upstream advisory ranges, but the fixed urllib3 2.8.0 requires Python 3.10 or newer, while both manifests still specify `urllib3<2`. The project also declares `numpy>=2.2.4`, which itself requires Python 3.10 or newer, despite `requires-python>=3.9`. These compatibility changes need a separate runtime review.
