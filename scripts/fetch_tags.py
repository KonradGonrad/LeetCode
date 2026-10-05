"""Fetch LeetCode topic tags once per slug; persist successes and errors."""

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://leetcode.com/graphql"
QUERY = "query Tags($titleSlug: String!) { question(titleSlug: $titleSlug) { topicTags { name } } }"


def load_cache(path):
    if path.is_symlink():
        raise ValueError(f"Cache must not be a symbolic link: {path}")
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Tag cache must be a JSON object.")
    for slug, entry in data.items():
        if (not isinstance(entry, dict) or entry.get("status") not in {"ok", "error"}
                or not isinstance(entry.get("tags"), list)
                or not all(isinstance(tag, str) for tag in entry["tags"])):
            raise ValueError(f"Invalid tag cache entry: {slug}")
    return data


def save_cache(path, cache):
    if path.is_symlink():
        raise ValueError(f"Cache must not be a symbolic link: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".tags-", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(cache, handle, ensure_ascii=False, indent=4, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def fetch_tags(slug):
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"query": QUERY, "variables": {"titleSlug": slug}}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "LeetCode-Notebook/1.0", "Referer": "https://leetcode.com/"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("LeetCode returned GraphQL errors.")
    question = payload["data"]["question"]
    if question is None:
        raise ValueError("Problem not found on LeetCode.")
    tags = question["topicTags"]
    if not isinstance(tags, list) or any(
        not isinstance(tag, dict) or not isinstance(tag.get("name"), str) for tag in tags
    ):
        raise ValueError("Invalid topicTags response.")
    return list(dict.fromkeys(tag["name"] for tag in tags if tag["name"].strip()))


def update_cache(tasks, path, *, refresh=False, retry_errors=False):
    cache = load_cache(path)
    slugs = sorted({task.name.split("-", 1)[1] for task in tasks})
    for slug in slugs:
        existing = cache.get(slug)
        if existing is not None and not refresh and not (
            retry_errors and existing["status"] == "error"
        ):
            continue
        entry = {"fetched_at": datetime.now(timezone.utc).isoformat()}
        try:
            entry.update(status="ok", tags=fetch_tags(slug))
        except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError) as error:
            entry.update(status="error", tags=[], error=str(error))
            print(f"Tags unavailable for {slug}: {error}", file=sys.stderr)
        cache[slug] = entry
        # Persist immediately: a later failure must not lose previous requests.
        save_cache(path, cache)
    return cache


def main():
    if __package__:
        from . import organizer
    else:
        import organizer
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        cache = update_cache(organizer.discover_tasks(), organizer.ROOT / "scripts/leetcode_cache.json",
                             refresh=args.refresh, retry_errors=args.retry_errors)
        print(f"Cached problems: {len(cache)}; errors: {sum(e['status'] == 'error' for e in cache.values())}")
        return 0
    except (OSError, ValueError) as error:
        print(f"Tag cache error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
