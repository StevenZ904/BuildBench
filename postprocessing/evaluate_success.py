"""
Evaluate Strict and Flexible Success metrics for BuildBench.

As described in Section 5 of the paper:
- Strict Success: ALL binary file names in the expert-generated list exist
  in the produced binaries.
- Flexible Success: AT LEAST ONE file name in the expert-generated list
  exists in the produced binaries.

Usage:
    python postprocessing/evaluate_success.py \
        --ground_truth data/compilation_label.json \
        --compiled_dir compiled_repos/

Ground truth format (compilation_label.json):
{
    "repo_name": ["expected_binary_1", "expected_binary_2"],
    ...
}
Repos with empty lists are non-compilable and are skipped.
"""

import os
import json
import argparse
from utils import find_linux_compiled_artifacts


def get_produced_binary_names(compiled_repo_dir):
    """Extract the set of binary file basenames from a compiled repo directory."""
    if not os.path.isdir(compiled_repo_dir):
        return set()

    binary_paths = find_linux_compiled_artifacts(
        compiled_repo_dir, max_workers=4
    )
    return {os.path.basename(p) for p in binary_paths}


def evaluate_success(ground_truth, compiled_dir):
    """
    Evaluate Strict and Flexible success across all repositories.

    Returns a dict with per-repo results and aggregate metrics.
    """
    # Filter out repos with empty expected binary lists (non-compilable)
    ground_truth = {k: v for k, v in ground_truth.items() if v}

    results = {}
    strict_count = 0
    flexible_count = 0
    completion_count = 0
    total = len(ground_truth)

    for repo_name, expected_binaries in ground_truth.items():
        repo_dir = os.path.join(compiled_dir, repo_name)
        produced = get_produced_binary_names(repo_dir)
        produced_basenames = {os.path.basename(b) for b in produced}

        expected_set = set(expected_binaries)

        # Completion: any binary produced
        has_completion = len(produced_basenames) > 0

        # Strict: all expected binaries are present
        strict = expected_set.issubset(produced_basenames) if expected_set else False

        # Flexible: at least one expected binary is present
        flexible = bool(expected_set & produced_basenames) if expected_set else False

        results[repo_name] = {
            "expected": list(expected_set),
            "produced": list(produced_basenames),
            "completion": has_completion,
            "strict_success": strict,
            "flexible_success": flexible,
        }

        if has_completion:
            completion_count += 1
        if strict:
            strict_count += 1
        if flexible:
            flexible_count += 1

    summary = {
        "total_repos": total,
        "completion_count": completion_count,
        "completion_pct": round(100 * completion_count / total, 1) if total else 0,
        "strict_success_count": strict_count,
        "strict_success_pct": round(100 * strict_count / total, 1) if total else 0,
        "flexible_success_count": flexible_count,
        "flexible_success_pct": round(100 * flexible_count / total, 1) if total else 0,
    }

    return results, summary


def main():
    parser = argparse.ArgumentParser(description="Evaluate Strict/Flexible Success")
    parser.add_argument("--ground_truth", type=str, required=True,
                        help="Path to JSON file with expected binary names per repo")
    parser.add_argument("--compiled_dir", type=str, required=True,
                        help="Path to directory containing compiled repos")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to save detailed results JSON")
    args = parser.parse_args()

    with open(args.ground_truth, "r") as f:
        ground_truth = json.load(f)

    results, summary = evaluate_success(ground_truth, args.compiled_dir)

    print(f"Total repos: {summary['total_repos']}")
    print(f"Completion:       {summary['completion_count']} ({summary['completion_pct']}%)")
    print(f"Strict Success:   {summary['strict_success_count']} ({summary['strict_success_pct']}%)")
    print(f"Flexible Success: {summary['flexible_success_count']} ({summary['flexible_success_pct']}%)")

    if args.output:
        with open(args.output, "w") as f:
            json.dump({"summary": summary, "per_repo": results}, f, indent=2)
        print(f"Detailed results saved to {args.output}")


if __name__ == "__main__":
    main()
