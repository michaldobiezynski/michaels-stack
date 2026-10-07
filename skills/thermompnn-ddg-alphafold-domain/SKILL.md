---
name: thermompnn-ddg-alphafold-domain
description: |
  Run a real ΔΔG (protein stability) prediction locally on a variant, using ThermoMPNN with an
  AlphaFold model, including the domain-extraction validity check. Use when: (1) you need ΔΔG
  for a missense variant and FoldX/Rosetta are licence-blocked, (2) ThermoMPNN inference dies
  with FileNotFoundError on /proj/kuhl_lab/ThermoMPNN/vanilla_model_weights/v_48_020.pt,
  (3) a web ΔΔG server (DDMut/DynaMut) returns job ids then Internal Server Error, or you need
  a calculation judges/reviewers can replay, (4) you are about to truncate a large multi-domain
  AlphaFold model to one domain and need to know whether that is valid, (5) you must state
  whether positive or negative ΔΔG means destabilising for a given tool.
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# Local ΔΔG on an AlphaFold domain with ThermoMPNN

## Problem

ΔΔG predictors are mostly licence-gated (FoldX, Rosetta) or web services whose job APIs are
flaky and unreplayable. ThermoMPNN runs locally on CPU with bundled weights, no MSA, in
minutes, but its repo ships configured for the authors' cluster and fails immediately.

## Solution

### 1. Validate the truncation BEFORE calculating

In a large multi-domain AlphaFold model, the *relative placement* of domains is far less
reliable than each domain's fold, so burial and neighbour counts can be pure packing artefact.
Count where a residue's neighbours come from before trusting anything local about it:

```python
# heavy-atom neighbours within 10 A, split by whether they come from inside the domain
intra = sum(1 for r, atoms in coords.items() if lo <= r <= hi for xyz in atoms
            if norm(xyz - ref) < 10.0 and r != target)
```

Verified example: one residue drew **129 of 129** neighbours from inside its domain, so
extracting that domain lost nothing and ΔΔG was well posed. Another residue in the same
protein drew **82 of 128 from outside**, so any ΔΔG there would measure model packing, and
the correct action was to report no value and say why. This check is also the cleanest way
to defuse a "buried residue" claim that is really an inter-domain artefact.

Get the current AlphaFold filename from the API, not by guessing: model versions increment
(`v4` 404s once `v6` is current).

```sh
curl -s "https://alphafold.ebi.ac.uk/api/prediction/<UNIPROT>" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['pdbUrl'])"
```

Extract the domain by filtering ATOM records on residue number, keeping original numbering so
the variant keeps its real position.

### 2. Install and fix the config

```sh
git clone --depth 1 https://github.com/Kuhlman-Lab/ThermoMPNN.git
python3 -m venv .venv
.venv/bin/pip install torch pytorch-lightning omegaconf biopython pandas tqdm torchmetrics wandb
```

`wandb` is imported by `train_thermompnn.py`, which inference imports transitively; set
`WANDB_MODE=disabled` rather than logging in.

**The blocking gotcha**: `local.yaml` hardcodes `thermompnn_dir: "/proj/kuhl_lab/ThermoMPNN"`,
so inference fails with `FileNotFoundError: /proj/kuhl_lab/ThermoMPNN/vanilla_model_weights/v_48_020.pt`
even though those weights are bundled in the clone. Repoint it:

```sh
sed -i '' "s|/proj/kuhl_lab/ThermoMPNN|$PWD/ThermoMPNN|" ThermoMPNN/local.yaml
```

### 3. Run and interpret

```sh
cd ThermoMPNN
WANDB_MODE=disabled ../.venv/bin/python analysis/custom_inference.py \
    --pdb ../domain.pdb --chain A --out_dir ../out/
```

Output is a full site-saturation scan (n_residues × 20). **Positions in the CSV are 0-based
within the supplied structure**, so map back with `residue = position + domain_start` and
confirm by checking the `wildtype` letter matches the expected residue.

**Never assume the sign convention. Derive it:** identity substitutions (wildtype == mutation)
must score ~0, and X→Pro should sit on the destabilising side of the mean. In the verified run,
identity scored exactly +0.000 and X→Pro averaged +1.82 against an overall +0.83, establishing
**positive = destabilising** for this tool.

Report the value against the scan's own distribution (percentile of all substitutions, and
the site's mean vs other sites) rather than as a bare number: the site-sensitivity percentile
is what tells you whether the position matters, and it comes free with the scan.

## Verification

Full run completed on CPU: 285-residue domain, 5,700 predictions, a few minutes, no GPU.

## Notes

- Magnitude interpretation matters therapeutically: ~+1.5 kcal/mol is a protein that still
  folds and is still made at reduced level, which is a different therapeutic situation from a
  severely destabilised one, where there would be nothing to stabilise.
- ThermoMPNN was trained largely on small monomeric domains; applying it to a domain excised
  from a large protein is reasonable but should be stated as a caveat.
- Related: [[myvariant-hg38-assembly-default]] for the sequence-level predictor panel
  (AlphaMissense, ESM1b, CADD) that complements a structural ΔΔG.
