#!/usr/bin/env python3
"""Run grade_answer.json against TypeSafe with three learner answers (correct, wrong method, answer only).

Usage: TYPESAFE_API_KEY must be set (see ~/.zshrc). No SDK needed; plain urllib.
Docs: https://docs.typesafe.ai/llms.txt   API: POST https://api.typesafe.ai/v1/systemone
"""
import json, os, pathlib, sys, time, urllib.error, urllib.request

HERE = pathlib.Path(__file__).parent
base = json.load(open(HERE / "grade_answer.json"))
key = os.environ.get("TYPESAFE_API_KEY") or sys.exit("TYPESAFE_API_KEY is not set")

variants = {
    "A correct, full working": "x=5 because 22-7 is 15 and 15 divided by 3 is 5",
    "B wrong method (added 7)": "x = 29/3 because 22+7 is 29 and then you divide by 3",
    "C correct, answer only": "5",
}

for label, ans in variants.items():
    payload = json.loads(json.dumps(base))
    payload["state"]["learner_answer"] = ans
    req = urllib.request.Request(
        "https://api.typesafe.ai/v1/systemone",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"{label}: HTTP {e.code} {e.read().decode()[:300]}")
        continue
    a = body["answers"]
    c, s = a["error_type"], a["working_shown"]
    probs = ", ".join(f"{k}={v:.3f}" for k, v in sorted(c["probabilities"].items(), key=lambda kv: -kv[1]))
    print(f"\n=== {label} ===  ({time.time()-t0:.2f}s, model={body['model']}, in={body['usage']['input_tokens']} out={body['usage']['output_tokens']})")
    print(f"  learner_answer : {ans!r}")
    print(f"  is_correct     : noul={a['is_correct']['noul']:.3f}")
    print(f"  error_type     : choice={c['choice']}  confidence={c['confidence']:.3f}  probs: {probs}")
    print(f"  working_shown  : score={s['score']:.3f} of 0..{len(s['legend'])-1}  confidence={s['confidence']:.3f}")
