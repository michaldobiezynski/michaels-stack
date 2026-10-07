#!/usr/bin/env bash
# Usage: TYPESAFE_API_KEY=... ./run.sh   (key from https://console.typesafe.ai/settings/keys)
set -euo pipefail
cd "$(dirname "$0")"
curl -sS -w '\nHTTP %{http_code}  %{time_total}s\n' -X POST https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer ${TYPESAFE_API_KEY:-}" \
  -H "Content-Type: application/json" \
  -d @grade_answer.json
