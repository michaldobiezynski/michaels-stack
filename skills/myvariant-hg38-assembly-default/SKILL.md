---
name: myvariant-hg38-assembly-default
description: |
  MyVariant.info silently interprets HGVS variant ids as hg19/GRCh37 unless the request
  includes assembly=hg38. Use when: (1) querying myvariant.info/v1/variant with
  chrN:g.POSREF>ALT ids built from GRCh38/hg38 coordinates, (2) a batch of known-real
  variants comes back almost entirely "notfound", (3) common SNPs from a WGS VCF return
  no gnomAD AF / rsid / ClinVar data, (4) an annotation "standout" appears at a locus
  where gene coordinates barely differ between builds (start-of-chromosome genes) and
  may be a coincidental cross-build hit.
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# MyVariant.info defaults to hg19; GRCh38 queries need assembly=hg38

## Problem

`POST https://myvariant.info/v1/variant` (and the GET variant/query endpoints) key HGVS
ids on **hg19 by default**. GRCh38-derived ids mostly miss (`notfound: true`), and the
failure is silent: the response is well-formed, so a naive pipeline reports "no
annotations" instead of erroring. Worse, occasional ids DO hit hg19 loci coincidentally
(genes near chromosome starts shift little between builds), producing plausible but
wrong-build annotations that survive as fake "findings".

## Solution

Append the assembly parameter: `https://myvariant.info/v1/variant?assembly=hg38`.
Verified effect on the same 47-variant batch: 1/47 resolved without it (plus one
coincidental cross-build annotation), 46/47 resolved with it, surfacing a ClinVar
Pathogenic hit the default-build query had hidden.

## Verification / sanity check

For any WGS-derived variant set, most variants are common SNPs: if fewer than ~half of
a batch return a gnomAD AF or rsid, suspect the assembly (or id format) before trusting
"rare/novel" conclusions. The absence of common-SNP annotations is the tell.

## Notes

- Ensembl VEP REST is the cross-check when it is up; MyGene.info (`fields=genomic_pos_hg38`)
  gives GRCh38 gene coordinates for region pulls.
- HGVS id construction for indels (ins/del forms) is a separate failure source; a
  notfound indel may be an id-format miss, not a novel variant.
