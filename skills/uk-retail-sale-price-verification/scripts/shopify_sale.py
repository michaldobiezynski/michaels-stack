#!/usr/bin/env python3
"""Rank discounted products in Shopify collections via the public products.json feed.

usage: shopify_sale.py <store_url> <collection_handle> [<store_url> <collection_handle> ...]
       shopify_sale.py https://www.run4it.com mens-sale-running-clothing --exclude shoe,trainer --require men
Options (apply to all pairs):
  --exclude a,b   skip products whose type/title/tags contain any term (default: shoe,trainer,footwear,boot,sandal,insole,sock)
  --require a,b   keep only products whose title/tags contain any term (default: none)
  --min-pct N     only print items with at least N% off (default 0)
  --top N         rows per store (default 15)
"""
import json, sys, urllib.request, ssl, socket, argparse
socket.setdefaulttimeout(20)
ctx = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json"}
ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--exclude", default="shoe,trainer,footwear,boot,sandal,insole,sock")
ap.add_argument("--require", default="")
ap.add_argument("--min-pct", type=int, default=0)
ap.add_argument("--top", type=int, default=15)
opts, rest = ap.parse_known_args()
if len(rest) < 2 or len(rest) % 2: sys.exit(__doc__)
excl = [t.strip().lower() for t in opts.exclude.split(",") if t.strip()]
req = [t.strip().lower() for t in opts.require.split(",") if t.strip()]

def blob(p):
    tags = p.get("tags", [])
    tags = " ".join(tags) if isinstance(tags, list) else str(tags)
    return f'{p.get("product_type","")} {p.get("title","")} {tags}'.lower()

for base, handle in zip(rest[::2], rest[1::2]):
    base = base.rstrip("/"); rows = []; err = None
    for page in range(1, 6):
        url = f"{base}/collections/{handle}/products.json?limit=250&page={page}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), context=ctx) as r:
                prods = json.loads(r.read().decode()).get("products", [])
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:100]; break
        if not prods: break
        for p in prods:
            b = blob(p)
            if any(t in b for t in excl): continue
            if req and not any(t in b for t in req): continue
            best = None
            for v in p.get("variants", []):
                try: price = float(v["price"]); comp = float(v.get("compare_at_price") or 0)
                except (KeyError, TypeError, ValueError): continue
                if comp > price > 0:
                    pct = round(100 * (1 - price / comp))
                    if best is None or pct > best[0]: best = (pct, price, comp, bool(v.get("available")))
            if best and best[0] >= opts.min_pct:
                rows.append((*best, p.get("vendor", ""), p["title"]))
        if len(prods) < 250: break
    rows.sort(reverse=True)
    print(f"\n=== {base}/collections/{handle} ===")
    if err and not rows: print("  ERROR:", err); continue
    print(f"  discounted products: {len(rows)}; >=50% off: {sum(1 for r in rows if r[0] >= 50)}")
    for pct, price, comp, avail, vendor, title in rows[:opts.top]:
        print(f"  {pct:>3}%  {price:>8.2f}  (was {comp:>8.2f})  {vendor} | {title}{'' if avail else '  [sold out?]'}")
