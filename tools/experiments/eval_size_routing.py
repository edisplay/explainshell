"""Evaluate cheap-vs-capable model agreement across size buckets.

Sample manpages stratified by gz size, extract with two models,
compute per-file option-set agreement, aggregate by bucket.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from explainshell.extraction import (
    ExtractionOutcome,
    ExtractionResult,
    ExtractorConfig,
    make_extractor,
)
from explainshell.extraction.runner import run
from explainshell.models import Option

BUCKETS = [(0, 1000), (1000, 2000), (2000, 4000), (4000, 8000)]


def collect_files(root: str) -> list[tuple[tuple[int, int], str]]:
    by_bucket: dict[tuple[int, int], list[str]] = defaultdict(list)
    for dp, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".gz"):
                continue
            p = os.path.join(dp, f)
            sz = os.path.getsize(p)
            for lo, hi in BUCKETS:
                if lo < sz <= hi:
                    by_bucket[(lo, hi)].append(p)
                    break
    return by_bucket


def sample_files(
    root: str, n_per_bucket: int, seed: int
) -> list[tuple[tuple[int, int], str]]:
    by_bucket = collect_files(root)
    rng = random.Random(seed)
    out: list[tuple[tuple[int, int], str]] = []
    for b in BUCKETS:
        pool = by_bucket.get(b, [])
        rng.shuffle(pool)
        for p in pool[:n_per_bucket]:
            out.append((b, p))
    return out


def opt_key(o: Option) -> tuple:
    return (tuple(sorted(o.short)), tuple(sorted(o.long)))


def diff_options(left_opts: list[Option], right_opts: list[Option]) -> dict[str, Any]:
    li = {opt_key(o): o for o in left_opts}
    ri = {opt_key(o): o for o in right_opts}
    only_left = set(li) - set(ri)
    only_right = set(ri) - set(li)
    common = set(li) & set(ri)
    text_diffs = sum(1 for k in common if li[k].text.strip() != ri[k].text.strip())
    arg_diffs = sum(
        1 for k in common if bool(li[k].has_argument) != bool(ri[k].has_argument)
    )
    denom = max(len(li), len(ri), 1)
    return {
        "left_n": len(li),
        "right_n": len(ri),
        "only_left": len(only_left),
        "only_right": len(only_right),
        "common": len(common),
        "text_diffs": text_diffs,
        "arg_diffs": arg_diffs,
        "agreement": len(common) / denom,
    }


def run_extractor(
    label: str, model: str, run_dir: str, files: list[str], jobs: int
) -> dict[str, ExtractionResult]:
    cfg = ExtractorConfig(model=model, run_dir=run_dir)
    ext = make_extractor("llm", cfg)
    results: dict[str, ExtractionResult] = {}
    counter = {"n": 0}
    total = len(files)

    def on_result(path: str, entry: ExtractionResult) -> None:
        counter["n"] += 1
        results[path] = entry
        outcome = entry.outcome.value
        n_opts = (
            len(entry.mp.options) if entry.outcome == ExtractionOutcome.SUCCESS else 0
        )
        print(
            f"  [{label} {counter['n']}/{total}] {os.path.basename(path)} "
            f"{outcome} opts={n_opts}",
            flush=True,
        )

    print(f"\n=== {label} ({model}) on {len(files)} files, jobs={jobs} ===", flush=True)
    t0 = time.monotonic()
    run(ext, files, jobs=jobs, on_result=on_result)
    print(f"  {label} done in {time.monotonic() - t0:.0f}s", flush=True)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="manpages/ubuntu/26.04")
    ap.add_argument("--left-model", default="codex/gpt-5.4-mini/medium")
    ap.add_argument("--right-model", default="codex/gpt-5.4/medium")
    ap.add_argument("--n-per-bucket", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="logs/eval_size_routing.json")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("explainshell").setLevel(logging.WARNING)

    sample = sample_files(args.root, args.n_per_bucket, args.seed)
    files = [p for _, p in sample]
    print(f"sampled {len(files)} files: ", end="")
    by_b: dict[tuple[int, int], int] = defaultdict(int)
    for b, _ in sample:
        by_b[b] += 1
    print(", ".join(f"{lo}-{hi}={by_b[(lo, hi)]}" for lo, hi in BUCKETS))

    run_dir = os.path.join("logs", f"eval_size_routing_{int(time.time())}")
    os.makedirs(run_dir, exist_ok=True)

    left_res = run_extractor("LEFT", args.left_model, run_dir, files, args.jobs)
    right_res = run_extractor("RIGHT", args.right_model, run_dir, files, args.jobs)

    rows: list[dict[str, Any]] = []
    skipped = 0
    for bucket, path in sample:
        left = left_res.get(path)
        right = right_res.get(path)
        if (
            not left
            or not right
            or left.outcome != ExtractionOutcome.SUCCESS
            or right.outcome != ExtractionOutcome.SUCCESS
        ):
            skipped += 1
            continue
        d = diff_options(left.mp.options, right.mp.options)
        d["bucket"] = list(bucket)
        d["path"] = path
        d["size"] = os.path.getsize(path)
        rows.append(d)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(
            {
                "left_model": args.left_model,
                "right_model": args.right_model,
                "n_per_bucket": args.n_per_bucket,
                "seed": args.seed,
                "rows": rows,
                "skipped": skipped,
            },
            f,
            indent=2,
        )
    print(f"\nwrote {len(rows)} rows ({skipped} skipped) to {args.out}\n")

    print(
        f"{'bucket':>10s} {'n':>4s} {'agree':>7s} "
        f"{'L_opts':>7s} {'R_opts':>7s} "
        f"{'onlyL':>6s} {'onlyR':>6s} {'txtΔ':>6s} {'argΔ':>6s}"
    )
    for bucket in BUCKETS:
        rs = [r for r in rows if tuple(r["bucket"]) == bucket]
        if not rs:
            continue
        median = statistics.median
        mean = statistics.mean
        print(
            f"{bucket[0]:>4d}-{bucket[1]:<5d} {len(rs):>4d} "
            f"{mean(r['agreement'] for r in rs):>6.1%} "
            f"{median(r['left_n'] for r in rs):>7.0f} "
            f"{median(r['right_n'] for r in rs):>7.0f} "
            f"{mean(r['only_left'] for r in rs):>6.1f} "
            f"{mean(r['only_right'] for r in rs):>6.1f} "
            f"{mean(r['text_diffs'] for r in rs):>6.1f} "
            f"{mean(r['arg_diffs'] for r in rs):>6.1f}"
        )
    print()

    print("worst-disagreement files (top 10 by sum of only_left+only_right):")
    rows.sort(key=lambda r: -(r["only_left"] + r["only_right"]))
    for r in rows[:10]:
        print(
            f"  size={r['size']:5d}  L={r['left_n']:3d} R={r['right_n']:3d} "
            f"onlyL={r['only_left']:3d} onlyR={r['only_right']:3d}  {r['path']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
