#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
workflow="$repo_root/.github/workflows/deploy-review-pages.yml"
index="$repo_root/.github/review-pages-index.html"
guide="$repo_root/docs/review-deployment.md"

test -f "$workflow"
test -f "$index"
test -f "$guide"

grep -Fq 'workflow_dispatch:' "$workflow"
grep -Fq 'actions/configure-pages@v5' "$workflow"
grep -Fq 'actions/upload-pages-artifact@v4' "$workflow"
grep -Fq 'actions/deploy-pages@v4' "$workflow"
grep -Fq 'cp -R review-source/Sources/web _site/Sources/web' "$workflow"
grep -Fq 'cp review-source/Samples/synthetic-trip.json _site/Samples/synthetic-trip.json' "$workflow"
grep -Fq 'https://usxusx.github.io/Calendar/' "$guide"

if grep -Eq 'jekyll|D1|cloudflare|vercel|netlify' "$workflow"; then
  echo "Review deployment must remain a direct static Pages workflow" >&2
  exit 1
fi
