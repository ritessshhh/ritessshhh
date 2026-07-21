#!/usr/bin/env python3
"""
Fetch live GitHub stats for the profile info card + contribution heatmap and
write them to data/stats.json.

Two data paths:
  * With a token (GH_STATS_TOKEN, or the Action's built-in GITHUB_TOKEN): uses
    the authenticated GraphQL + REST API. A personal GH_STATS_TOKEN with the
    `repo` scope also pulls PRIVATE contributions, a commits/PRs/issues/reviews
    breakdown, and per-repo additions/deletions for a real lines-of-code figure.
  * With no token: falls back to the public, unauthenticated contributions API
    so the script still runs locally for previews (public activity only).

Every section is wrapped so a single failing call (e.g. a rate-limited LOC scan)
degrades to the previous stats.json value instead of crashing the whole run.
Run daily by .github/workflows/update-profile-art.yml.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

USER = os.environ.get("GH_PROFILE_USER", "ritessshhh")
TOKEN = os.environ.get("GH_STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "stats.json")

GQL_URL = "https://api.github.com/graphql"
REST = "https://api.github.com"
UA = "profile-readme-bot/1.0"

LEVEL = {  # GraphQL contributionLevel enum -> heatmap level 0..4
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}


# ---- HTTP helpers ---------------------------------------------------------
def _req(url, data=None, headers=None, method=None):
    h = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"bearer {TOKEN}"
    if headers:
        h.update(headers)
    body = data.encode() if isinstance(data, str) else data
    return urllib.request.Request(url, data=body, headers=h, method=method)


def gql(query, variables):
    payload = json.dumps({"query": query, "variables": variables})
    req = _req(GQL_URL, data=payload,
               headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


def rest(path, retries=6):
    """GET a REST endpoint. Retries on 202 (GitHub computing stats)."""
    url = path if path.startswith("http") else REST + path
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(_req(url), timeout=30) as r:
                if r.status == 202:                       # stats not ready yet
                    time.sleep(2 + attempt * 2)
                    continue
                raw = r.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 202:
                time.sleep(2 + attempt * 2)
                continue
            raise
    return None


# ---- contribution calendar + activity breakdown --------------------------
def fetch_graphql_stats():
    q = """
    query($login:String!){
      user(login:$login){
        createdAt
        followers { totalCount }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalPullRequestReviewContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount contributionLevel } }
          }
        }
      }
    }"""
    d = gql(q, {"login": USER})["user"]
    cc = d["contributionsCollection"]
    days = []
    for wk in cc["contributionCalendar"]["weeks"]:
        for day in wk["contributionDays"]:
            days.append({
                "date": day["date"],
                "count": day["contributionCount"],
                "level": LEVEL.get(day["contributionLevel"], 0),
            })
    days.sort(key=lambda x: x["date"])
    return {
        "created_at": d["createdAt"],
        "followers": d["followers"]["totalCount"],
        "calendar": {"total": cc["contributionCalendar"]["totalContributions"], "days": days},
        "activity": {
            "commits": cc["totalCommitContributions"],
            "prs": cc["totalPullRequestContributions"],
            "issues": cc["totalIssueContributions"],
            "reviews": cc["totalPullRequestReviewContributions"],
            "private": cc["restrictedContributionsCount"],
        },
    }


def fetch_public_calendar():
    """Token-free fallback: jogruber's public contributions mirror."""
    url = f"https://github-contributions-api.jogruber.de/v4/{USER}?y=last"
    with urllib.request.urlopen(_req(url), timeout=30) as r:
        d = json.loads(r.read().decode())
    days = [{"date": c["date"], "count": c["count"], "level": c["level"]}
            for c in d["contributions"]]
    days.sort(key=lambda x: x["date"])
    return {"calendar": {"total": d["total"]["lastYear"], "days": days}}


# ---- derived streaks / best day ------------------------------------------
def streaks(days):
    longest = run = 0
    for x in days:
        run = run + 1 if x["count"] > 0 else 0
        longest = max(longest, run)
    i = len(days) - 1
    if i >= 0 and days[i]["count"] == 0:   # today isn't over -> don't break it
        i -= 1
    current = 0
    while i >= 0 and days[i]["count"] > 0:
        current += 1
        i -= 1
    return {"current": current, "longest": longest}


# ---- profile / repos / languages / LOC -----------------------------------
def fetch_profile():
    d = rest(f"/users/{USER}")
    return {"name": d.get("name"), "bio": d.get("bio"), "location": d.get("location"),
            "public_repos": d.get("public_repos"), "created_at": d.get("created_at"),
            "followers": d.get("followers")}


def list_repos():
    """Owned, non-fork repos. With a token this includes private repos too."""
    repos, page = [], 1
    base = "/user/repos?affiliation=owner&per_page=100" if TOKEN else f"/users/{USER}/repos?per_page=100"
    while True:
        batch = rest(f"{base}&page={page}")
        if not batch:
            break
        repos.extend(r for r in batch if not r["fork"])
        if len(batch) < 100:
            break
        page += 1
    return repos


# Container/markup formats whose byte counts wildly overstate real coding
# effort (a notebook embeds its rendered image outputs). Kept out of the bar.
LANG_EXCLUDE = {"Jupyter Notebook", "HTML", "CSS", "TeX", "Roff", "Makefile", "Dockerfile"}


def fetch_languages(repos):
    totals = {}
    for r in repos:
        data = rest(r["languages_url"]) or {}
        for lang, b in data.items():
            if lang in LANG_EXCLUDE:
                continue
            totals[lang] = totals.get(lang, 0) + b
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    return [{"name": n, "bytes": b, "pct": round(100 * b / grand, 1)} for n, b in ranked]


def fetch_loc(repos):
    """Sum this user's additions/deletions across all repos via stats/contributors."""
    added = removed = 0
    for r in repos:
        stats = rest(f"/repos/{r['full_name']}/stats/contributors")
        if not stats:
            continue
        for contrib in stats:
            if (contrib.get("author") or {}).get("login", "").lower() == USER.lower():
                for wk in contrib["weeks"]:
                    added += wk["a"]
                    removed += wk["d"]
    return {"added": added, "removed": removed, "net": added - removed}


# ---- assembly -------------------------------------------------------------
def human_age(created_iso):
    start = datetime.datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    days = (now - start).days
    years, rem = divmod(days, 365)
    return {"years": years, "days_extra": rem,
            "text": (f"{years} yr{'s' if years != 1 else ''}"
                     + (f", {rem} days" if rem else ""))}


def load_prev():
    try:
        with open(OUT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guarded(prev, key, fn):
    """Run fn(); on failure keep the previous stats.json value for `key`."""
    try:
        return fn()
    except Exception as e:            # noqa: BLE001 - degrade, don't crash
        print(f"  ! {key} failed ({e}); keeping previous", file=sys.stderr)
        return prev.get(key)


def main():
    prev = load_prev()
    out = {"username": USER,
           "generated_at": datetime.datetime.now(datetime.timezone.utc)
           .strftime("%Y-%m-%dT%H:%M:%SZ")}

    # calendar + activity: GraphQL if we have a token, else public fallback
    if TOKEN:
        core = guarded(prev, "_core", fetch_graphql_stats)
    else:
        print("  (no token -> public activity only)", file=sys.stderr)
        core = guarded(prev, "_core", fetch_public_calendar)
    core = core or {}
    cal = core.get("calendar") or prev.get("calendar") or {"total": 0, "days": []}
    out["calendar"] = cal
    days = cal["days"]
    out["streaks"] = streaks(days) if days else prev.get("streaks", {})
    out["active_days"] = sum(1 for d in days if d["count"] > 0) if days else prev.get("active_days", 0)
    out["best_day"] = (max(days, key=lambda d: d["count"]) if days
                       else prev.get("best_day"))
    if "activity" in core:
        out["activity"] = core["activity"]
    elif prev.get("activity"):
        out["activity"] = prev["activity"]

    profile = guarded(prev, "profile", fetch_profile) or {}
    created = core.get("created_at") or profile.get("created_at")
    out["profile"] = {
        "name": profile.get("name"),
        "location": profile.get("location"),
        "followers": core.get("followers", profile.get("followers")),
        "public_repos": profile.get("public_repos"),
        "created_at": created,
        "account_age": human_age(created) if created else prev.get("profile", {}).get("account_age"),
    }

    repos = guarded(prev, "_repos", list_repos) or []
    out["repos"] = len(repos) if repos else prev.get("repos", 0)
    out["stars"] = sum(r["stargazers_count"] for r in repos) if repos else prev.get("stars", 0)
    out["languages"] = (guarded(prev, "languages", lambda: fetch_languages(repos))
                        if repos else prev.get("languages", []))
    out["loc"] = (guarded(prev, "loc", lambda: fetch_loc(repos))
                  if repos else prev.get("loc", {}))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    loc = out.get("loc") or {}
    print(f"wrote {OUT}: {cal['total']} contribs, "
          f"streak {out['streaks'].get('current')}/{out['streaks'].get('longest')}, "
          f"{len(out['languages'])} languages, "
          f"+{loc.get('added', 0):,}/-{loc.get('removed', 0):,} LOC")


if __name__ == "__main__":
    main()
