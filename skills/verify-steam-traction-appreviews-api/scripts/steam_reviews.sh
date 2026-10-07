#!/usr/bin/env bash
# Live Steam review totals for one or more appids, all languages, all purchase types.
# Usage: steam_reviews.sh <appid[:label]> [<appid[:label]> ...]
# Example: steam_reviews.sh 2021910:"FPS Chess" 1972440:"Shotgun King"
set -euo pipefail
for pair in "$@"; do
  id="${pair%%:*}"; label="${pair#*:}"; [ "$label" = "$pair" ] && label="$id"
  summary=$(curl -s "https://store.steampowered.com/appreviews/$id?json=1&language=all&purchase_type=all&num_per_page=0")
  details=$(curl -s "https://store.steampowered.com/api/appdetails?appids=$id&filters=basic,release_date")
  python3 - "$id" "$label" "$summary" "$details" <<'PY'
import sys, json
aid, label, summary, details = sys.argv[1:5]
q = json.loads(summary).get("query_summary", {})
t, p = q.get("total_reviews", 0), q.get("total_positive", 0)
d = json.loads(details).get(aid, {}).get("data", {}) or {}
name = d.get("name", "?"); rel = d.get("release_date", {})
state = "COMING SOON" if rel.get("coming_soon") else rel.get("date", "?")
pct = f"{100*p//t:>3}%" if t else "  - "
flag = "" if t else "   <- 0 reviews: check appid / release state"
print(f"{label:28s} {t:>7} reviews {pct}  {q.get('review_score_desc','?'):18s} steam name: {name} | release: {state}{flag}")
PY
done
