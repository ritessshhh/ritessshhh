#!/usr/bin/env python3
"""
Count your real lines of code across every repo you own -- WITHOUT cloning.

Why this is better than `git clone` + cloc on each repo:
  * downloads a gzipped TARBALL per repo (no .git history, no full checkout) ->
    a fraction of the bandwidth and disk of a clone
  * extracts to a temp dir and SKIPS oversized files (datasets, binaries, bundles)
    so a 500 MB data repo never lands on disk
  * runs repos in PARALLEL
  * partitions real programming code vs. data / docs / markup, so the total
    isn't dominated by JSON, Unity prefabs, CSV, Markdown, etc.

Token: set it in the environment -- NEVER hardcode it in the file.
    export GH_STATS_TOKEN=<your-token>        # needs `repo` scope for private repos
    python get-loc/get-loc.py

Tuning via env vars:
    GH_USER=ritessshhh      whose repos (defaults to the token owner)
    INCLUDE_FORKS=1         count forks too (off by default)
    MAX_FILE_KB=1024        skip files bigger than this during extraction
    WORKERS=8               parallel repos
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

TOKEN = os.environ.get("GH_STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("Set GH_STATS_TOKEN (or GITHUB_TOKEN) in your environment first.")

USER = os.environ.get("GH_USER")  # None -> the token owner (/user/repos)
INCLUDE_FORKS = bool(os.environ.get("INCLUDE_FORKS"))
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_KB", "1024")) * 1024
WORKERS = int(os.environ.get("WORKERS", "8"))

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "loc.json")

# cloc language names that are NOT hand-written programming code. Edit freely --
# e.g. delete "HTML"/"CSS" here if you want to count them as code.
NON_CODE = {
    # data / config
    "JSON", "JSON5", "YAML", "TOML", "INI", "XML", "CSV", "TSV", "Properties",
    "Unity-Prefab", "Protocol Buffers", "SVG", "GeoJSON",
    # docs
    "Markdown", "Text", "reStructuredText", "AsciiDoc", "Org Mode", "PO File",
    "Gettext Catalog",
    # markup / styling
    "HTML", "CSS", "SCSS", "Sass", "LESS", "Stylus", "XSLT",
    # build / generated / misc
    "make", "CMake", "Gradle", "Dockerfile", "ProGuard", "C# Generated",
    "DOS Batch", "diff", "Jupyter Notebook",
}
# directories cloc should never descend into
EXCLUDE_DIRS = ("node_modules,.git,venv,.venv,env,__pycache__,dist,build,out,"
                ".next,.nuxt,coverage,vendor,Pods,Carthage,DerivedData,bin,obj,"
                "target,.terraform,.expo,Library")


def list_repos():
    """Owned repos (private included via the token), forks optional."""
    base = f"https://api.github.com/users/{USER}/repos" if USER else "https://api.github.com/user/repos"
    repos, page = [], 1
    while True:
        r = requests.get(base, headers=HEADERS,
                         params={"per_page": 100, "page": page,
                                 "visibility": "all", "affiliation": "owner"},
                         timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return [r for r in repos if INCLUDE_FORKS or not r["fork"]]


def download_and_extract(full_name, dest):
    """Stream the repo tarball and extract only reasonably-sized files."""
    url = f"https://api.github.com/repos/{full_name}/tarball"
    with requests.get(url, headers=HEADERS, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        tmp_tar = dest + ".tar.gz"
        with open(tmp_tar, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    kept = 0
    with tarfile.open(tmp_tar, "r:gz") as tar:
        for m in tar:
            if m.isfile() and m.size <= MAX_FILE_BYTES:
                tar.extract(m, dest, filter="data")   # filter='data' blocks path traversal
                kept += 1
    os.remove(tmp_tar)
    return kept


def cloc_dir(path):
    """Run cloc once; return {language: code_lines} for everything it found."""
    res = subprocess.run(
        ["cloc", path, "--json", "--quiet", f"--exclude-dir={EXCLUDE_DIRS}",
         "--not-match-f=(\\.min\\.(js|css)$|[-.]lock\\.json$|\\.d\\.ts$)"],
        capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return {}
    try:
        stats = json.loads(res.stdout)
    except ValueError:
        return {}
    return {lang: v["code"] for lang, v in stats.items()
            if lang not in ("header", "SUM")}


def process(repo):
    name = repo["full_name"]
    workdir = tempfile.mkdtemp(prefix="loc_")
    try:
        download_and_extract(name, workdir)
        by_lang = cloc_dir(workdir)
    except Exception as e:                      # noqa: BLE001 - keep going
        print(f"  ! {name}: {e}", file=sys.stderr)
        by_lang = {}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    code = sum(v for k, v in by_lang.items() if k not in NON_CODE)
    print(f"  {name:<45} {code:>8,} code lines")
    return repo["name"], by_lang


def main():
    repos = list_repos()
    print(f"Found {len(repos)} repos (forks {'in' if INCLUDE_FORKS else 'ex'}cluded). "
          f"Counting via tarball + cloc...\n")

    lang_code, lang_other, per_repo = {}, {}, {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process, r): r for r in repos}
        for fut in as_completed(futures):
            rname, by_lang = fut.result()
            per_repo[rname] = sum(v for k, v in by_lang.items() if k not in NON_CODE)
            for lang, c in by_lang.items():
                bucket = lang_other if lang in NON_CODE else lang_code
                bucket[lang] = bucket.get(lang, 0) + c

    total_code = sum(lang_code.values())
    total_other = sum(lang_other.values())

    print("\n===============================")
    print(f"Real code:  {total_code:,} lines")
    print(f"Excluded:   {total_other:,} lines (data / docs / markup)")
    print("===============================\n")
    print("Code by language:\n")
    for lang, c in sorted(lang_code.items(), key=lambda x: -x[1]):
        print(f"  {lang:<20} {c:>10,}")
    print("\nTop repos by code:\n")
    for rname, c in sorted(per_repo.items(), key=lambda x: -x[1])[:10]:
        print(f"  {rname:<40} {c:>10,}")

    with open(OUT_JSON, "w") as f:
        json.dump({"total_code": total_code, "total_excluded": total_other,
                   "by_language": lang_code, "excluded_by_language": lang_other,
                   "by_repo": per_repo}, f, indent=2)
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
