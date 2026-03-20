#!/usr/bin/env python3
"""
detect_build_systems.py

Scan many C/C++ repositories to detect build systems present.
- Searches each repo's root and one level of subdirectories (depth=1).
- Reports multiple build systems if they co-exist.
- Records evidence (which file(s) matched).
- Adds a global counter for repos without any build-related files.

Usage:
  python detect_build_systems.py /path/to/repos_parent \
      --format json --output build_systems.json --jobs 8 --include-generated

Notes:
- By default, common generated dirs (build/, out/, etc.) are ignored.
- Ninja files are often generated; include them with --include-generated if desired.
"""

from __future__ import annotations
import argparse
import csv
import fnmatch
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Heuristic ignore set for immediate subdirectories (depth=1)
DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".cache", "__pycache__",
    "build", "out", "dist", "target",
    "cmake-build-debug", "cmake-build-release",
    "node_modules", ".venv", "venv", ".tox",
}

@dataclass(frozen=True)
class Detector:
    name: str
    exact: Tuple[str, ...] = tuple()
    globs: Tuple[str, ...] = tuple()
    # If true, these are often generated (e.g., Ninja build files);
    # they are skipped unless --include-generated is set.
    often_generated: bool = False

DETECTORS: Tuple[Detector, ...] = (
    # Core build systems
    Detector("CMake", exact=("CMakeLists.txt", "CMakePresets.json")),
    Detector("Meson", exact=("meson.build",)),
    Detector("Autotools", exact=("configure.ac", "Makefile.am", "aclocal.m4", "configure")),
    Detector("Make", exact=("Makefile", "GNUmakefile", "makefile")),
    Detector("Bazel", exact=("WORKSPACE", "WORKSPACE.bazel", "BUILD", "BUILD.bazel")),
    Detector("Buck", exact=("BUCK", ".buckconfig")),
    Detector("SCons", exact=("SConstruct", "SConscript")),
    Detector("QMake", globs=("*.pro", "*.pri")),
    Detector("Premake", exact=("premake5.lua", "premake4.lua")),
    Detector("xmake", exact=("xmake.lua",)),
    Detector("Waf", exact=("wscript", "waf")),
    Detector("Qbs", globs=("*.qbs",)),
    Detector("GN", exact=("BUILD.gn",)),
    # IDE formats (still valid build entry points)
    Detector("Visual Studio (MSBuild)", globs=("*.sln", "*.vcxproj", "*.vcproj")),
    Detector("Xcode", globs=("*.xcodeproj",), exact=("project.pbxproj",)),
    # Often generated (opt-in)
    Detector("Ninja", exact=("build.ninja",), often_generated=True),
    # Custom scripts (not strictly a build system, but useful to flag)
    Detector("Custom Script", exact=("build.sh", "configure.sh", "bootstrap.sh", "build.bat")),
)

def list_scan_roots(repo_dir: Path, ignore_dirs: Set[str]) -> List[Path]:
    """Return [repo_dir, *its immediate subdirs (excluding ignored)]"""
    roots = [repo_dir]
    try:
        for p in repo_dir.iterdir():
            if p.is_dir() and p.name not in ignore_dirs:
                roots.append(p)
    except PermissionError:
        pass
    return roots

def scan_one_repo(
    repo_dir: Path,
    ignore_dirs: Set[str],
    include_generated: bool,
    selected_detector: str = None,
) -> Dict:
    """Scan a single repo root + depth=1 subdirs and detect build systems."""
    findings: Dict[str, List[str]] = {}  # build_system -> [evidence relative paths]
    scan_roots = list_scan_roots(repo_dir, ignore_dirs)

    # Collect (relative) filenames to check, keeping path context for evidence
    rel_paths: List[Path] = []
    for root in scan_roots:
        try:
            for entry in root.iterdir():
                # include both files and dirs (e.g., .xcodeproj is a dir)
                rel_paths.append(entry.relative_to(repo_dir))
        except PermissionError:
            continue

    # For faster lookups
    basenames = [p.name for p in rel_paths]

    if selected_detector:
        dets = [d for d in DETECTORS if d.name == selected_detector]
    else:
        dets = DETECTORS

    for det in dets:
        if det.often_generated and not include_generated:
            continue

        matched: List[Path] = []

        # Exact filename matches (by basename)
        if det.exact:
            exact_set = set(det.exact)
            for rp, base in zip(rel_paths, basenames):
                if base in exact_set:
                    matched.append(rp)

        # Glob matches (by basename)
        if det.globs:
            for pattern in det.globs:
                for rp, base in zip(rel_paths, basenames):
                    if fnmatch.fnmatch(base, pattern):
                        matched.append(rp)

        if matched:
            findings[det.name] = sorted(str(p) for p in set(matched))

    systems = sorted(findings.keys())
    return {
        "repo": str(repo_dir),
        "systems": systems,
        "evidence": findings,  # mapping: system -> list of relative paths
    }

def enumerate_repos(parent: Path, scan_self: bool) -> List[Path]:
    """Treat each immediate subdirectory as a repo; optionally include parent itself."""
    repos: List[Path] = []
    if scan_self:
        repos.append(parent)
    try:
        for p in parent.iterdir():
            if p.is_dir():
                repos.append(p)
    except PermissionError:
        pass
    return sorted(repos)

def summarize_per_system(results: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in results:
        for s in r.get("systems", []):
            counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

def count_no_build(results: List[Dict]) -> Tuple[int, List[str]]:
    """Return (number_without_build_files, list_of_repo_paths)."""
    no_list = [r["repo"] for r in results if not r.get("systems")]
    return len(no_list), no_list

def write_json(results: List[Dict], output: Path | None):
    per_system = summarize_per_system(results)
    no_count, no_list = count_no_build(results)
    data = {
        "results": results,
        "summary": {
            "per_system_counts": per_system,
            "repos_without_build_files": no_count,
            "repos_without_build_files_list": no_list,
        },
    }
    text = json.dumps(data, indent=2)
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        print(text)

def write_csv(results: List[Dict], output: Path | None):
    fieldnames = ["repo", "systems", "evidence"]
    rows = []
    for r in results:
        systems = ";".join(r.get("systems", []))
        # Flatten evidence as "System: path1, path2 | System2: ..."
        ev_pairs = []
        for sys_name, paths in r.get("evidence", {}).items():
            ev_pairs.append(f"{sys_name}: {', '.join(paths)}")
        evidence_str = " | ".join(ev_pairs)
        rows.append({"repo": r["repo"], "systems": systems, "evidence": evidence_str})

    if output:
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def main(repos_parent: Path, 
         format: str, output: Path | None, 
         include_generated: bool, 
         ignore_dirs: set[str], 
         scan_self: bool,
         selected_detector: str | None) -> List[Dict]:
    parent = repos_parent.resolve()
    if not parent.exists() or not parent.is_dir():
        ap.error(f"{parent} is not a directory")

    ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    if args.ignore:
        ignore_dirs.update(args.ignore)

    repos = enumerate_repos(parent, scan_self=args.scan_self)
    if not repos:
        print("No repositories found.", file=sys.stderr)
        sys.exit(1)

    results: List[Dict] = []
    
    if args.select_detector:
        print(f"Running only the '{args.select_detector}' detector.", file=sys.stderr)
        selected_detector = args.select_detector
    else:
        selected_detector = None

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = {
            ex.submit(scan_one_repo, repo, ignore_dirs, args.include_generated, selected_detector): repo
            for repo in repos
        }
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                repo = futs[fut]
                results.append({"repo": str(repo), "systems": [], "evidence": {}, "error": str(e)})

    # Stable ordering by repo path
    results.sort(key=lambda r: r["repo"])

    # Write output
    if args.format == "json":
        write_json(results, args.output)
    else:
        write_csv(results, args.output)

    # Print a quick summary to stderr for convenience
    per_system = summarize_per_system(results)
    no_count, _ = count_no_build(results)
    print("\n=== Summary (repos per system) ===", file=sys.stderr)
    for name, cnt in per_system.items():
        print(f"{name:26} {cnt}", file=sys.stderr)
    print(f"{'No build system detected':26} {no_count}", file=sys.stderr)
    return results

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Detect build systems across many repos (depth=1).")
    ap.add_argument("repos_parent", type=Path, help="Directory containing many repo directories.")
    ap.add_argument("--format", choices=["json", "csv"], default="json", help="Output format.")
    ap.add_argument("--output", type=Path, help="Output file path (otherwise prints to stdout).")
    ap.add_argument("--jobs", type=int, default=8, help="Parallel worker count.")
    ap.add_argument("--include-generated", action="store_true",
                    help="Include often-generated artifacts (e.g., Ninja build.ninja).")
    ap.add_argument("--ignore", nargs="*", default=None,
                    help="Extra directory names to ignore at depth=1 (space-separated).")
    ap.add_argument("--scan-self", action="store_true",
                    help="Also scan the parent folder itself as a repo.")
    ap.add_argument("--select-detector", type=str, choices=[d.name for d in DETECTORS], default=None,
                    help="Only run a specific detector (for testing/debugging).")
    args = ap.parse_args()
    main(
        repos_parent=args.repos_parent,
        format=args.format,
        output=args.output,
        include_generated=args.include_generated,
        ignore_dirs=set(args.ignore) if args.ignore else set(),
        scan_self=args.scan_self,
        selected_detector=args.select_detector,
    )
