import json
import os
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

#!/usr/bin/env python3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_JSON_PATH = os.environ.get("PROJECTS_JSON_PATH", os.path.join(SCRIPT_DIR, "Projects.json"))
CLONE_BASE_DIR = os.environ.get("CLONE_BASE_DIR", os.path.join(SCRIPT_DIR, "cloned_repos"))
GIT_BIN = "git"
MAX_WORKERS = 6
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

def ensure_paths():
    Path(CLONE_BASE_DIR).mkdir(parents=True, exist_ok=True)

def load_projects(path: str):
    p = Path(path)
    if not p.exists():
        print(f"Projects file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, list):
            raise ValueError("JSON root should be a list")
        return data
    except Exception as e:
        print(f"Failed to read JSON: {e}", file=sys.stderr)
        sys.exit(1)

def mask_token(s: str) -> str:
    if not GITHUB_TOKEN or GITHUB_TOKEN == "REPLACE_WITH_YOUR_GITHUB_TOKEN":
        return s
    return s.replace(GITHUB_TOKEN, "***")

def to_https(url: str) -> str:
    # Convert SSH git@github.com:owner/repo(.git) to https URL
    if url.startswith("git@github.com:"):
        path = url[len("git@github.com:"):]
        if not path.endswith(".git"):
            path += ".git"
        return f"https://github.com/{path}"
    if url.startswith("ssh://git@github.com/"):
        path = url[len("ssh://git@github.com/"):]
        if not path.endswith(".git"):
            path += ".git"
        return f"https://github.com/{path}"
    return url

def git_clone(url: str, dest: Path) -> tuple[bool, str]:
    dest_str = str(dest)
    base_url = to_https(url)

    # Use a transient url.<base>.insteadof to avoid writing the token to .git/config
    cmd = [
        GIT_BIN,
        "-c",
        f"url.https://x-access-token:{GITHUB_TOKEN}@github.com/.insteadof=https://github.com/",
        "clone",
        "--depth",
        "1",
        # "--recurse-submodules",
        base_url,
        dest_str,
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if proc.returncode == 0:
            return True, mask_token(proc.stdout.strip())
        else:
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            return False, mask_token(out.strip())
    except FileNotFoundError:
        return False, "git not found in PATH"
    except Exception as e:
        return False, f"Exception: {e}"

def clone_one(project: dict) -> str:
    name = project.get("name") or "unknown"
    url = project.get("url")
    if not url:
        return f"[ERR] {name}: missing url"

    target = Path(CLONE_BASE_DIR) / name
    if target.exists() and (target / ".git").exists():
        return f"[SKIP] {name}: already cloned"

    ok, msg = git_clone(url, target)
    if ok:
        return f"[OK] {name}"
    else:
        # Cleanup partial clone on failure
        if target.exists() and not (target / ".git").exists():
            try:
                # Best-effort cleanup of partial directory
                for root, dirs, files in os.walk(target, topdown=False):
                    for f in files:
                        try:
                            os.remove(os.path.join(root, f))
                        except Exception:
                            pass
                    for d in dirs:
                        try:
                            os.rmdir(os.path.join(root, d))
                        except Exception:
                            pass
                try:
                    os.rmdir(target)
                except Exception:
                    pass
            except Exception:
                pass
        return f"[ERR] {name}: {msg}"

def main():
    if not GITHUB_TOKEN or GITHUB_TOKEN == "REPLACE_WITH_YOUR_GITHUB_TOKEN":
        print("Please set GITHUB_TOKEN in this script to a valid GitHub token.", file=sys.stderr)
        sys.exit(2)

    ensure_paths()
    projects = load_projects(PROJECTS_JSON_PATH)

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(clone_one, proj): proj for proj in projects}
        for fut in as_completed(futures):
            res = fut.result()
            print(res)
            results.append(res)

    # Summary
    ok = sum(1 for r in results if r.startswith("[OK]"))
    skip = sum(1 for r in results if r.startswith("[SKIP]"))
    err = sum(1 for r in results if r.startswith("[ERR]"))
    print(f"Done. OK={ok}, SKIP={skip}, ERR={err}")

if __name__ == "__main__":
    main()