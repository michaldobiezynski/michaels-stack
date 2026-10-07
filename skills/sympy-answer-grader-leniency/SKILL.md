---
name: sympy-answer-grader-leniency
description: |
  Make a sympy-based free-response maths grader accept what learners and LLM verifiers actually
  type. Use when: (1) an auto-grader marks 'Nx/n' wrong against 'N*x/n', (2) 'e^{-\lambda b}' or
  'e^(-2x)' fails against 'exp(-lambda*b)', (3) parse_expr silently turns N, E, S, O, Q into sympy
  objects so the key's free symbols vanish, (4) 'lambda' as a symbol name raises or misparses,
  (5) '0.1111 (=1/9)' or 'sigma = E*sqrt(n)' fails a numeric/expression check. Found while
  verifying 1,963 generated statistics questions: 55 of 89 'disagreements' were grader strictness.
author: Claude Code
version: 1.0.0
date: 2026-09-12
---

# sympy answer-grader leniency

## Problem
A grader that calls `parse_expr` with `implicit_multiplication_application` looks lenient but
fails on four common inputs, and each failure looks like a wrong answer rather than a parser bug.

## Trigger conditions
- Expression keys that contain single capital letters `N`, `E`, `S`, `O`, `Q` (sample size N,
  expectation E) or `lambda`.
- Learner/verifier answers in TeX (`\frac`, `\sqrt`, `e^{...}`, `\lambda`), with Greek glyphs
  (`λ`, `σ`, `√`), with glued products (`Nx`, `nM`), or with annotations (`0.1111 (=1/9)`).

## Root causes (verified)
1. `parse_expr("N*x/n")` binds `N` to `sympy.N` (evalf) and `E` to Euler's number, so the parsed
   key has no symbols `N`/`E`; any vocabulary-based normalisation of the given answer then sees
   an empty vocabulary. Fix: `local_dict={c: Symbol(c) for c in "NESOQ"}`.
2. `lambda` is a Python keyword; sympy's `lambda_notation` transformation treats it as `Lambda`.
   Rename to `lam` in BOTH key and given before parsing.
3. `Nx` is one symbol under implicit multiplication. Split glued tokens only when every letter is
   a free symbol of the parsed KEY (so `exp`, `sqrt` and genuine multi-letter names survive).
4. `e^(...)`, `e^{...}`, `e^x` are the symbol `e` to a power, not `exp`. Rewrite them, and
   `√n` -> `sqrt(n)` with grouping, and insert `*` between a letter/digit and `sqrt|exp|log`.

## Solution sketch
```python
LOCALS = {c: Symbol(c) for c in "NESOQ"}
def _parse(s): return parse_expr(s, transformations=standard + (implicit_multiplication_application, convert_xor), local_dict=LOCALS)
# _clean: Greek -> names (λ -> lam), TeX -> plain (\frac{a}{b} -> ((a)/(b)), e^{x} -> exp(x), \lambda -> lam),
#         strip trailing '(= ...)' annotations and a leading 'name =' / 'f(x) =', '^' -> '**',
#         'e**(' -> 'exp(', 'sqrtn' -> 'sqrt(n)', 'Esqrt(' -> 'E*sqrt('.
key = _parse(_clean(k)); vocab = {s.name for s in key.free_symbols}
given = _parse(_split_glued(_clean(g), vocab))   # 'Nx' -> 'N*x' only if N and x are key symbols
```
Keep a `recheck` command that re-grades stored verifier answers locally: it costs nothing and
turns grader improvements into measurable agreement gains (95.5% -> 98.3% here).

## Verification
Tests: `'Nx/n' == 'N*x/n'`, `'λ/(λ - I*t)'`, `'e^{-\lambda b}' == 'exp(-lambda*b)'`,
`'e^{xy}(2y+xy^2)'`, `'\frac{N-a}{N}'`, `'0.1111 (=1/9)'` all pass; remaining disagreements are
genuine (different numeric answers, distinct algebraic forms of a bound).

## Notes
- Do not add `I` or `gamma` to the symbol overrides: `I` is often the imaginary unit in
  characteristic functions, and `gamma` is often the function.
- Normalise the key with the same `_clean` as the given, otherwise the `lambda` rename breaks
  equality.

## Addendum (14/09/2026): a TeX converter in front of the grader must not break plain text
- If you add a LaTeX-to-text pass that reads the argument after `^` or `_`, it MUST accept a
  parenthesised group as well as a braced one, or plain `x^(5/12)` becomes `x^(()5/12)` and
  every bracketed power grades wrong. Caught only because identical key/verifier strings
  showed up as 'disagreements' in a re-grade: always eyeball the disagreement list for
  identical pairs after changing the cleaner.
- Normalise subscripts (`x_2`, `x_{2}`, `x2` -> `x2`) and absolute values (`|x|` -> `Abs(x)`)
  in the shared cleaner so key and given meet in the same form.

## Addendum (23/09/2026): 'exact ≈ decimal' answers
- LLM verifiers often answer '8/15 ≈ 0.5333' or '1.06066 (=sqrt(9/8))'. Stripping '≈' leaves
  '8/15  0.5333', which implicit multiplication parses as a product: silently wrong. Split the
  given answer on ≈/≃/~= and accept if ANY stated form is correct; strip a trailing
  '(= ...)' annotation with a greedy `.*\)$`, not `[^)]*`, or nested brackets defeat it.
  Treat '[ ]' as grouping in expression answers. On a 1,147-question Machine Learning course
  these three raised checker agreement from 91.6% to 95.5% with no model calls.

## Addendum (25/09/2026): bracketed restatements, and do not let leniency become hedging
- Verifiers also write a BARE bracket: '0.642857 (9/14)', '0.3679 (e^{-1})', '4√5 (≈ 8.944)'.
  Implicit multiplication reads '0.64 (9/14)' as a product. But '2 (3)' can genuinely mean 6,
  so do not strip every trailing bracket: treat a bare bracket as a restatement only when it
  is spaced off from the lead AND evaluates to the same number; then grade the lead alone.
  This also stops '0.3 (0.5)' from passing for either key (no hedging between two answers).
- Handle a marked '(≈ ...)' / '(= ...)' BEFORE the 23/09 '≈' split, or '26/3 (≈8.667)'
  splits inside the bracket into '26/3 (' and '8.667)' and both halves fail to parse.
- Map Unicode '²' '³' to '^2' '^3', and insert a space between a Greek glyph and an adjacent
  letter ('λσ' -> 'lam sigma', 'mτ' -> 'm tau', 'πR' -> 'pi R'); otherwise they fuse into one
  unknown name that the glued-symbol splitter cannot break.
- Measure a cleaner change in BOTH directions over the stored verifier answers before applying
  it: count False->True (recovered) and True->False (regressions) separately and eyeball every
  recovered pair. Result on 51,628 questions: 73 recovered, 0 regressions.

## Addendum (26/09/2026): leniency creates false positives; review it adversarially
Re-grading stored verifier answers only proves you did not LOSE correct answers. It cannot show
wrong answers you now ACCEPT. A fresh-context reviewer fuzzing real questions (each MC option's
own text, `K = W`, `W (K)`, `K ≈ W` mutations) found these in a version with 0 regressions:
- MC index regex `^(\d+)[\s):.]` read '1 m', '02:05', '1:200', '1 or 2' as indices: 112 wrong
  options accepted. Rule: a bare index is the WHOLE answer (`(0|[1-9]\d?)[.)]?`); then option text
  (exact, then case-folded only if unique, since `\phi` vs `\Phi`); then 'N (note)' with a space; then a letter.
- Dropping a powered left side ('q^n =', 'σ^2 = 2') accepts σ^2 = 2 for key σ = 2. Drop only a
  bare name, a subscripted name, or f(x).
- '≈' any-form rule is a hedge ('0.3 ≈ 0.5'). Accept any form only while the stated forms agree
  (within ~5%); otherwise all must be right.
- A bracketless function argument runs to the next function, operator (+ - = , / and single *)
  or bracket: 'sin pi x' = sin(pi x), 'sin x cos y' = sin(x)cos(y), 'sin x^2' = sin(x^2),
  'ln 2/3' = ln(2)/3. Taking only the next token, or using the rule only on parse errors, each
  broke one half of these. 'sin^-1 x' is asin, not 1/sin.
- A cleaner applied to key AND answer can hide mangling: `(?<=\w)(?=sin\b)` turned asin into
  a*sin on both sides, so 'a*sin(u)' passed for key asin(u). Guard the a of asin/acos/atan.
- Map sympy functions used as bare variables (beta, gamma, eta, E1, zeta) to Symbols unless
  called; they otherwise crash even the KEY's parse, so the question can never be passed.
- Wrap the public check in try/except -> False: 'x = 3, y = 4' parses to a tuple and crashed the
  learner's submission.
