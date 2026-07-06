# AGENTS.md

## Purpose

AgentKitBoard is a reference board for external AI-agent tooling repos. It tracks links, categories, notes, verification status, and comparison tables.

## Repo Policy

- Reference external repositories; do not vendor or copy their source code.
- Keep the README useful as the main landing page.
- Keep the catalog data in `catalog/repos.yaml` aligned with the README table.
- Mark new entries as `seed` or `needs-url` until repo URL, license, and maintenance status are checked.
- Do not present claimed token savings as verified unless there is a local benchmark or trustworthy source note.
- Prefer short, scannable summaries over long prose.

## Entry Quality

Each referenced repo should include:

- Name
- Canonical URL
- Category
- Language
- License
- Supported agent/provider surfaces
- Short reason it belongs here
- Verification status
- Last checked date when verified

## Editing Rules

- Use ASCII Markdown and YAML.
- Keep tables readable in GitHub.
- If a repo is stale, do not remove it immediately. Mark it as `stale` and add a note.
- If a link is uncertain, use `needs-url`.
