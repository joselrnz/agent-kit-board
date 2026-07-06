#!/usr/bin/env python3
"""Scrape GitHub Trending, keep AI/tooling hits, and update README sections."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


README_PATH = Path("README.md")
TRENDING_PATH = Path("data/trending-ai.json")
ARCHIVE_PATH = Path("data/trending-archive.json")
TRENDING_START = "<!-- agent-kit-board:trending:start -->"
TRENDING_END = "<!-- agent-kit-board:trending:end -->"
GITHUB_RE = re.compile(r"https://github\.com/([^/\s)]+)/([^/\s)#)]+)")
BLOCKED_REPOS = {"google-gemini/gemini-cli"}
DEFAULT_WINDOWS = ("daily", "weekly", "monthly")

AI_TOPICS = {
    "agent",
    "agents",
    "agentic",
    "ai",
    "ai-agent",
    "ai-agents",
    "ai-assistant",
    "ai-tools",
    "anthropic",
    "artificial-intelligence",
    "autonomous-agents",
    "automation",
    "chatbot",
    "chatgpt",
    "claude",
    "codex",
    "computer-vision",
    "copilot",
    "cursor",
    "deep-learning",
    "deepseek",
    "diffusion-models",
    "embeddings",
    "fine-tuning",
    "gemini",
    "genai",
    "generative-ai",
    "glm",
    "gpt",
    "gpt-4",
    "huggingface",
    "image-generation",
    "knowledge-graph",
    "langchain",
    "langgraph",
    "large-language-models",
    "llama",
    "llamaindex",
    "llm",
    "llmops",
    "llms",
    "machine-learning",
    "mcp",
    "mistral",
    "model-context-protocol",
    "multimodal",
    "natural-language-processing",
    "neural-network",
    "nlp",
    "ollama",
    "openai",
    "prompt",
    "prompt-engineering",
    "pytorch",
    "qwen",
    "rag",
    "reinforcement-learning",
    "retrieval-augmented-generation",
    "semantic-search",
    "speech-recognition",
    "stable-diffusion",
    "tensorflow",
    "text-generation",
    "text-to-image",
    "transformer",
    "transformers",
    "vector-database",
    "vector-search",
    "vllm",
    "whisper",
    "zhipu",
}

AI_KEYWORDS = {
    "agent",
    "agentic",
    "ai",
    "anthropic",
    "artifical intellegence",
    "artificial intelligence",
    "assistant",
    "automation",
    "autonomous",
    "chatbot",
    "chatgpt",
    "claude",
    "codex",
    "copilot",
    "cursor",
    "deepseek",
    "diffusion",
    "embedding",
    "fine-tune",
    "fine-tuning",
    "gemini",
    "genai",
    "generative ai",
    "glm",
    "gpt",
    "huggingface",
    "inference",
    "langchain",
    "langgraph",
    "llamaindex",
    "llm",
    "llmops",
    "mcp",
    "mistral",
    "model context protocol",
    "multimodal",
    "neural network",
    "nlp",
    "ollama",
    "openai",
    "prompt",
    "pytorch",
    "qwen",
    "rag",
    "reasoning",
    "retrieval",
    "semantic",
    "tensorflow",
    "token",
    "transformer",
    "vector",
    "vllm",
    "whisper",
    "zhipu",
}


class GitHubRepoMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    exists: bool = True
    description: str = ""
    language: str = ""
    stars: int = Field(default=0, ge=0)
    topics: list[str] = Field(default_factory=list)
    pushed_at: str = ""
    archived: bool = False


class TrendingRepo(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    url: str
    description: str
    language: str
    stars: int = Field(ge=0)
    recent_stars: int = Field(ge=0)
    window: str
    topics: list[str] = Field(default_factory=list)
    pushed_at: str
    first_seen: str
    last_seen: str
    seen_count: int = Field(ge=1)


def utc_today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def normalize_repo(owner: str, repo: str) -> str:
    return f"{owner}/{repo.removesuffix('.git')}"


def is_blocked(slug: str) -> bool:
    return slug.lower() in BLOCKED_REPOS


def fetch(url: str, token: str | None = None) -> str:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/vnd.github+json",
        "User-Agent": "agent-kit-board-trending-refresh",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()


def parse_int(value: str | None) -> int:
    if not value:
        return 0
    match = re.search(r"[\d,]+", value)
    return int(match.group(0).replace(",", "")) if match else 0


def parse_trending(page: str, window: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    for row in re.findall(r'<article class="Box-row">(.*?)</article>', page, re.DOTALL):
        slug_match = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', row, re.DOTALL)
        if not slug_match:
            continue

        slug = slug_match.group(1).strip()
        if slug.count("/") != 1 or is_blocked(slug):
            continue

        desc_match = re.search(r'<p class="col-9[^"]*">(.*?)</p>', row, re.DOTALL)
        stars_match = re.search(r'/stargazers"[^>]*>.*?([\d,]+)\s*</a>', row, re.DOTALL)
        recent_match = re.search(r"([\d,]+)\s*stars?\s*(?:today|this week|this month)", row, re.IGNORECASE)
        language_match = re.search(r'<span itemprop="programmingLanguage">([^<]+)</span>', row)

        repos.append(
            {
                "slug": slug,
                "description": strip_tags(desc_match.group(1)) if desc_match else "",
                "stars": parse_int(stars_match.group(1) if stars_match else None),
                "recent_stars": parse_int(recent_match.group(1) if recent_match else None),
                "language": strip_tags(language_match.group(1)) if language_match else "",
                "window": window,
            }
        )

    return repos


def github_meta(slug: str, token: str | None) -> GitHubRepoMeta | None:
    if is_blocked(slug):
        return None
    try:
        raw = fetch(f"https://api.github.com/repos/{slug}", token=token)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return GitHubRepoMeta(exists=False)
        print(f"Could not validate {slug}: HTTP {error.code}", file=sys.stderr)
        return None
    except Exception as error:  # noqa: BLE001 - keep trend refresh resilient.
        print(f"Could not validate {slug}: {error}", file=sys.stderr)
        return None

    data = json.loads(raw)
    return GitHubRepoMeta(
        description=data.get("description") or "",
        language=data.get("language") or "",
        stars=int(data.get("stargazers_count") or 0),
        topics=list(data.get("topics") or []),
        pushed_at=data.get("pushed_at") or "",
        archived=bool(data.get("archived")),
    )


def is_ai(slug: str, description: str, topics: list[str] | None = None) -> bool:
    if topics and any(topic.lower() in AI_TOPICS for topic in topics):
        return True

    text = f"{slug} {description}".lower()
    for keyword in AI_KEYWORDS:
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
            return True
    return False


def validate_trending(repos: list[dict[str, Any]], limit: int, token: str | None) -> list[TrendingRepo]:
    today = utc_today()
    if not repos:
        return []

    cap = repos[: max(limit * 3, limit + 10)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        metas = list(pool.map(lambda item: github_meta(item["slug"], token), cap))

    selected: list[TrendingRepo] = []
    for repo, meta in zip(cap, metas):
        if meta is not None and not meta.exists:
            continue

        topics = meta.topics if meta else []
        description = meta.description or repo["description"] if meta else repo["description"]
        if not is_ai(repo["slug"], description, topics):
            continue

        if meta and meta.archived:
            continue

        slug = str(repo["slug"])
        selected.append(
            TrendingRepo(
                slug=slug,
                name=slug.split("/", 1)[1],
                url=f"https://github.com/{slug}",
                description=description,
                language=meta.language or repo["language"] if meta else repo["language"],
                stars=meta.stars or int(repo["stars"]) if meta else int(repo["stars"]),
                recent_stars=int(repo["recent_stars"]),
                window=str(repo["window"]),
                topics=topics,
                pushed_at=meta.pushed_at if meta else "",
                first_seen=today,
                last_seen=today,
                seen_count=1,
            )
        )

    selected.sort(key=lambda item: (item.recent_stars, item.stars), reverse=True)
    return selected[:limit]


def collect_trending(limit: int, windows: tuple[str, ...], token: str | None) -> dict[str, list[TrendingRepo]]:
    grouped: dict[str, list[TrendingRepo]] = {}

    for window in windows:
        try:
            page = fetch(f"https://github.com/trending?since={urllib.parse.quote(window)}")
        except Exception as error:  # noqa: BLE001 - one failed window should not kill all refresh.
            print(f"Could not scrape trending {window}: {error}", file=sys.stderr)
            grouped[window] = []
            continue

        parsed = parse_trending(page, window)
        grouped[window] = validate_trending(parsed, limit=limit, token=token)

    return grouped


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def repo_to_dict(repo: TrendingRepo) -> dict[str, Any]:
    return repo.model_dump()


def flatten_grouped(grouped: dict[str, list[TrendingRepo]]) -> list[TrendingRepo]:
    current: list[TrendingRepo] = []
    seen: set[str] = set()
    for window in ("daily", "weekly", "monthly"):
        for repo in grouped.get(window, []):
            if repo.slug in seen:
                continue
            seen.add(repo.slug)
            current.append(repo)
    return current


def merge_archive(current: list[TrendingRepo], archive_path: Path, max_archive: int) -> dict[str, Any]:
    today = utc_today()
    previous = load_json(archive_path).get("repos", {})
    previous = previous if isinstance(previous, dict) else {}
    current_by_slug = {repo.slug: repo for repo in current}

    archive: dict[str, dict[str, Any]] = {}
    for slug, raw in previous.items():
        if not isinstance(raw, dict):
            continue
        archive[slug] = raw

    for repo in current:
        prior = archive.get(repo.slug, {})
        item = repo_to_dict(repo)
        item["first_seen"] = str(prior.get("first_seen") or repo.first_seen)
        item["seen_count"] = int(prior.get("seen_count") or 0) + 1
        item["active"] = True
        archive[repo.slug] = item

    for slug, item in list(archive.items()):
        if slug not in current_by_slug:
            item["active"] = False
            item.setdefault("last_seen", today)

    sorted_items = sorted(
        archive.values(),
        key=lambda item: (str(item.get("last_seen") or ""), int(item.get("recent_stars") or 0), int(item.get("stars") or 0)),
        reverse=True,
    )

    return {
        "checked_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "repos": {str(item["slug"]): item for item in sorted_items[:max_archive]},
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def markdown_link(slug: str) -> str:
    return f"[{slug}](https://github.com/{slug})"


def short(value: str, limit: int = 120) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    if len(clean) <= limit:
        return clean.replace("|", "\\|")
    return (clean[: limit - 1].rstrip() + "…").replace("|", "\\|")


def stars(value: int) -> str:
    if value >= 1000:
        return f"⭐ {value / 1000:.1f}k"
    return f"⭐ {value}"


def render_table(items: list[dict[str, Any]], empty: str) -> str:
    if not items:
        return empty

    lines = [
        "| Repo | Window | Language | ⭐ Stars | 🔥 Recent | Why it matched | Last seen |",
        "|---|---|---|---:|---:|---|---:|",
    ]
    for item in items:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_link(str(item["slug"])),
                    str(item.get("window") or "-"),
                    str(item.get("language") or "-"),
                    stars(int(item.get("stars") or 0)),
                    f"🔥 +{int(item.get('recent_stars') or 0)}",
                    short(str(item.get("description") or "-")),
                    str(item.get("last_seen") or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def render_window_details(window: str, repos: list[TrendingRepo], open_attr: str = "") -> str:
    title = {
        "daily": "📅 Daily",
        "weekly": "🗓️ Weekly",
        "monthly": "📆 Monthly",
    }.get(window, window.title())
    current_items = [repo_to_dict(repo) for repo in repos]
    table = render_table(current_items, f"No AI/tooling repos matched GitHub Trending for `{window}`.")
    details_tag = f"<details {open_attr}>" if open_attr else "<details>"
    return f"""{details_tag}
<summary><strong>{title}</strong></summary>

{table}

</details>"""


def render_trending_section(grouped: dict[str, list[TrendingRepo]], archive: dict[str, Any], archive_limit: int) -> str:
    archived_items = [
        item
        for item in archive.get("repos", {}).values()
        if isinstance(item, dict) and not item.get("active")
    ][:archive_limit]

    generated = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    daily = render_window_details("daily", grouped.get("daily", []), "open")
    weekly = render_window_details("weekly", grouped.get("weekly", []))
    monthly = render_window_details("monthly", grouped.get("monthly", []))
    return f"""{TRENDING_START}
## 🔥 Trending AI Repos

Auto-updated from GitHub Trending. Current rows are repos trending now; archive rows are kept after they fall out so references are not lost.

Generated: `{generated}`

### Current Trending Windows

{daily}

{weekly}

{monthly}

### Previously Trending Archive

{render_table(archived_items, "No archived trending repos yet.")}
{TRENDING_END}"""


def update_readme(readme_path: Path, section: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    for owner, repo in GITHUB_RE.findall(text):
        if normalize_repo(owner, repo).lower() in BLOCKED_REPOS:
            raise ValueError(f"blocked repo found in README: {owner}/{repo}")

    if TRENDING_START in text and TRENDING_END in text:
        pattern = re.compile(rf"{re.escape(TRENDING_START)}.*?{re.escape(TRENDING_END)}", re.DOTALL)
        text = pattern.sub("", text).replace("\n\n\n", "\n\n")

    anchor = "\n## 🚀 Start Here\n"
    if anchor in text:
        text = text.replace(anchor, f"\n{section}\n\n## 🚀 Start Here\n", 1)
    else:
        fallback_anchor = "\n## 🧱 Choose By What It Is\n"
        if fallback_anchor in text:
            text = text.replace(fallback_anchor, f"\n{section}\n\n## 🧱 Choose By What It Is\n", 1)
        else:
            text = text.rstrip() + "\n\n" + section + "\n"

    readme_path.write_text(text, encoding="utf-8")


def parse_windows(value: str) -> tuple[str, ...]:
    windows = tuple(part.strip() for part in value.split(",") if part.strip())
    valid = {"daily", "weekly", "monthly"}
    invalid = [window for window in windows if window not in valid]
    if invalid:
        raise ValueError(f"invalid trending windows: {', '.join(invalid)}")
    return windows or DEFAULT_WINDOWS


def main() -> int:
    parser = argparse.ArgumentParser(description="Update README with GitHub Trending AI repos.")
    parser.add_argument("--readme", default=str(README_PATH), help="Path to README.md")
    parser.add_argument("--trending", default=str(TRENDING_PATH), help="Current trending JSON path")
    parser.add_argument("--archive", default=str(ARCHIVE_PATH), help="Trending archive JSON path")
    parser.add_argument("--windows", default="daily,weekly,monthly", help="Comma-separated windows: daily,weekly,monthly")
    parser.add_argument("--limit", type=int, default=20, help="Number of current trending repos to keep")
    parser.add_argument("--archive-limit", type=int, default=50, help="Number of archived repos to show in README")
    parser.add_argument("--max-archive", type=int, default=500, help="Number of archived repos to keep in JSON")
    args = parser.parse_args()

    token = os.environ.get("AGENT_KIT_BOARD_GITHUB_BEARER")
    windows = parse_windows(args.windows)
    grouped = collect_trending(limit=args.limit, windows=windows, token=token)
    current = flatten_grouped(grouped)
    archive = merge_archive(current, Path(args.archive), max_archive=args.max_archive)

    write_json(
        Path(args.trending),
        {
            "checked_at": archive["checked_at"],
            "windows": list(windows),
            "groups": {
                window: [repo_to_dict(repo) for repo in repos]
                for window, repos in grouped.items()
            },
            "repos": {repo.slug: repo_to_dict(repo) for repo in current},
        },
    )
    write_json(Path(args.archive), archive)
    update_readme(Path(args.readme), render_trending_section(grouped, archive, args.archive_limit))

    print(f"Updated trending section ({len(current)} current, {len(archive.get('repos', {}))} archived).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
