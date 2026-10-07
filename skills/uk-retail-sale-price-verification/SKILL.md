---
name: uk-retail-sale-price-verification
description: |
  Get EXACT sale prices and discount depth from UK sports/running retailers when a deal hunt
  (e.g. Newsjack news-search in host-search fallback) has to verify 'up to X% off' claims.
  Use when: (1) WebFetch on a Shopify collection page returns only navigation/header shell
  ('product listings not included in the content'), (2) a brand site returns 403 to both
  WebFetch and curl (adidas, New Balance, Brooks, inov8, Decathlon UK), (3) Sports Direct or
  Wiggle time out, (4) HotUKDeals deal pages show no posted date. Covers the Shopify
  /collections/<handle>/products.json trick (compare_at_price), parsing Gymshark's embedded
  application/json blocks via curl, which UK retailers are reachable by which tool, and
  where dated UK voucher evidence actually lives.
author: Claude Code
version: 1.0.0
date: 2026-09-20
---

# UK retail sale-price verification

## Problem
Search results for 'running clothes sale UK' are evergreen retailer landing pages, not evidence.
Verifying real discount depth needs product-level prices, but WebFetch (small-model summariser)
gets only the JavaScript shell of most modern shop pages, and many brand sites block bots outright.

## Context / trigger conditions
- WebFetch answer says the page 'shows navigation menus and promotional banners only' or
  'product listings ... are not included in the provided content'.
- HTTP 403 from adidas.co.uk, newbalance.co.uk, brooksrunning.com, inov8.com, decathlon.co.uk
  (fetcher AND curl). Under Armour UK returns 418 to curl and 'A required part of this site
  couldn't load' to the fetcher. on.com returns a 4 KB shell.
- sportsdirect.com and wiggle.com time out (60 s) for the fetcher and give curl exit 000.
- HotUKDeals deal pages (`/deals/<slug>-<id>`) never show a posted date to the fetcher, only
  'Unfortunately, this deal is no longer available' when expired.

## Solution
1. **Shopify stores: use the public products feed, not the HTML.**
   `GET {store}/collections/{handle}/products.json?limit=250&page=N` returns every variant's
   `price` and `compare_at_price`. Discount = 1 - price/compare_at_price. Run
   `scripts/shopify_sale.py <store> <handle> [...]` (bundled) to rank by discount, filter shoes/
   women's, and flag sold-out variants. Verified 20/09/2026 on runnorthwest.co.uk,
   run4it.com, startfitness.co.uk, soarrunning.com. Handles come from the site's nav links or
   a `site:<domain> sale` WebSearch; guessed handles 404 (tracksmith.com, ronhill.com,
   alpkit.com returned 0 rows or 404: they either hide sale collections or discount nothing).
2. **Gymshark (headless Next.js, curl gets 200 with ~1.8 MB):** the real sale handles are
   `/collections/last-chance/mens`, `/collections/sale-shorts/mens`,
   `/collections/sale-t-shirts-tops/mens`, `/collections/sale-bottoms/mens` (guesses like
   `/collections/sale/mens` or `/collections/mens-sale` 404). Parse the
   `<script type="application/json">` blocks and walk for dicts holding `discountPercentage`,
   `price`, `compareAtPrice`, `title`. The Gymshark Central blog post
   `gymshark.com/blog/article/seasonal-sales` is a dated, bylined source for sale windows.
3. **Server-rendered UK running shops that the fetcher CAN read:** sportsshoes.com (sale
   clothing at `/products/sale/clothing/`, note the fetcher mislabelled a women's line as
   men's, so confirm the title from the HTML with a python regex, not ugrep, which chokes on
   `£` unicode), runnersneed.com, runandbecome.com, northernrunner.com (category pages such
   as `/sale/clothing-c143/running-tights-and-tracksters-c440`), johnlewis.com offer pages,
   jdsports.co.uk (real paths: `/men/mens-clothing/sale/sport/running/` and
   `/men/mens-clothing/brand/on-running/sale/`; guessed paths 404).
4. **Dated voucher evidence:** `hotukdeals.com/vouchers/<retailer-domain>` pages load and
   carry 'Ends in N days' plus current promos ('extra 10% off sale items', 'up to 70% off');
   moneysavingexpert.com/deals/<store>/ also loads. Use these instead of coupon-farm pages.
5. **Blocked brand sites:** report as unverified and triangulate through stockists (JD Sports
   for On/Nike/adidas, Run North West and Run4It for Ronhill/Gore Wear/New Balance).

## Verification
`python3 scripts/shopify_sale.py https://www.run4it.com mens-sale-running-clothing --top 5`
prints a ranked table with `discounted products: N; >=50% off: M`. If it prints
`ERROR: HTTPError: HTTP Error 404`, the handle is wrong, not the store.

## Example
20/09/2026 men's running-clothing hunt: Start Fitness `mens-running-outlet` feed showed 266
discounted products, 99 at >=50% (Compressport Hurricane V2 jacket £149.99 -> £25), which no
fetcher pass could see because the collection page only returned the header.

## Notes
- products.json prices are in the store's default currency; tracksmith.com defaults to USD and
  its `/gb/` market path does not expose feeds.
- `available: false` variants still appear in the feed; the script flags them `[sold out?]`.
- Gymshark's running page HTML also contains the sale-collection hrefs, so grep
  `href="[^"]*(sale|last-chance)` before guessing handles.
- Related: `newsjack-competitive-positioning-pass` (same plugin, different job).

## References
- Shopify storefront JSON endpoints: https://shopify.dev/docs/api/ajax/reference/product
- Gymshark seasonal sale calendar: https://www.gymshark.com/blog/article/seasonal-sales
