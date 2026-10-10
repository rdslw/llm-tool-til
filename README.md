# llm-tool-til

Til toolbox and `llm til` command for [Simon Willison's LLM](https://llm.datasette.io/).

After a conversation with `llm`, ask the model for a summary, a primer, or
documentation of the conversation. The model writes it as a markdown note into
`~/.kb/`, with a name like `til-2610-git-rebase-onto.md`. Two ways:

- `llm -c -T Til '...'`: the `Til` toolbox. The model calls tools to create,
  edit, view, list and search notes. A note costs at least two requests.
- `llm til ['...']`: one request; the plugin writes the reply to a new note. See
  [The `llm til` command](#the-llm-til-command).

The model does the important work: it selects the content, the structure and the
markdown format. The plugin only stores the notes safely.

`AGENTS.md` points at this file, so keep operational project knowledge here.
`Development` and `Release` sections are at the bottom.

## Installation

The package is not on PyPI. Install it into the `llm` environment with one of:

```bash
# from a local checkout; -e (editable): changes in the directory apply at once
llm install -e /path/to/llm-tool-til

# from GitHub (for SSH access: git+ssh://git@github.com/rdslw/llm-tool-til)
llm install 'git+https://github.com/rdslw/llm-tool-til'
```

## Usage

```bash
# continue the last conversation and save a note about it
llm -c -T Til 'Write a TIL primer of this conversation: the problem, the fix, key commands and pitfalls.'

# --td shows the tool calls, --ta asks for approval before each tool call
llm -c -T Til --td --ta 'Add the last answer to the git rebase note.'

# find what you noted before
llm -T Til 'Search my notes in ~/.kb: what did I write about git rebase?'

# interactive
llm chat -T Til

# one request: save the last conversation as a note with the default prompt
llm til

# the same with your own instructions, a fixed slug, or another conversation
llm til 'Write a primer of the asyncio part only.' --slug asyncio-primer
llm til --cid 01k0abcd...
```

## Tools implemented

| Tool | Use |
| --- | --- |
| `Til_create(slug, content)` | Create the note `til-YYMM-<slug>.md`. Fails if the file exists. The result tells the model not to repeat the note text. |
| `Til_str_replace(filename, old_str, new_str)` | Replace text that occurs exactly once in a `.md` or `.txt` file. |
| `Til_view(filename)` | Return the full text of a file. |
| `Til_list_files()` | List the file names, newest first. |
| `Til_search(query)` | Find `query` (plain text, case-insensitive) in all files (newest first). |

`Til_search` is pure Python, not a call to `rg` or `grep`. It has the same output
format as `grep -n -i -C3`, but it needs no external program, has the same
behavior on Linux and macOS, ignores `~/.ripgreprc` and locale settings, and
applies the same file name and symlink checks as the other tools, while it
allows easier limits implementation and enforcing.

`Til_search("docker")` output, for two files (`:` marks a matching line, `-` a
context line):

```
til-2610-docker-networks.md:1:# Docker networks
til-2610-docker-networks.md-2-
til-2610-docker-networks.md-3-## Bridge
til-2610-docker-networks.md-4-
til-2610-docker-networks.md-5-The default network is a bridge.
til-2610-docker-networks.md:6:Run docker network inspect bridge to see it.
--
notes.txt-1-cleanup:
notes.txt:2:  docker system prune -a
```

## Safety

- The root directory is always `~/.kb/`. If it does not exist, all tools fail;
  the toolbox never creates it. If `~/.kb` is a symlink, the toolbox uses its target.
- A file name can contain only the characters `[a-zA-Z0-9_.-]` and cannot start
  with `.`. So it cannot contain `/` and cannot be `.` or `..`: path traversal is
  not possible. Hidden files are not visible.
- `Til_create` makes only notes (`til-YYMM-<slug>.md`). `Til_str_replace` edits only
  `.md` and `.txt` files. Scripts (`.sh`) and files without an extension are read-only.
- The tools refuse symlinks in `~/.kb/`, so a link cannot send a read or write outside.
  `Til_list_files` and `Til_search` show only regular files: no symlinks, no
  subdirectories.
- `Til_create` never overwrites: it opens the file in exclusive mode (`"x"`).
- `Til_str_replace` changes text only if `old_str` occurs exactly once.
- There is no delete, rename or overwrite tool.

Limits (constants in `llm_tool_til.py`):

| Limit | Value |
| --- | --- |
| One file, written by `Til_create` or `Til_str_replace` | 100 KB (102400 bytes UTF-8) and 2000 lines |
| One file, read by `Til_view` or `Til_str_replace` | 100 KB |
| `Til_list_files` output | 400 names, then a line with the count of older files |
| `Til_search` output | 100 matching lines, 600 lines with context; each line cut to 200 characters; only the first 102400 characters of each file |

## Context Cost

- `-T Til` adds the five tool definitions to every request: about 420 tokens
  as JSON (budget 450). `codex/gpt-6-luna` bills them as 244. Measure:
  `llm -u -m MODEL 'hi'` with and without `-T Til`.
- Each tool call is one more request with the full conversation, so a note
  costs the conversation at least twice. The note text is input again in later
  requests. `llm til` avoids both.
- Caching makes repeats cheaper; check `cached_tokens` in `llm logs --json`.
- One tool result costs at most about 4,000 (`Til_list_files`), 25,000
  (`Til_view`) or 35,000 tokens (`Til_search`).
- Keep the docstrings (tool descriptions) short; error guidance goes in the
  error messages. Recount after a change:

```bash
uv run --with tiktoken python -c 'import json, tiktoken, llm_tool_til as t; d = [{"type": "function", "function": {"name": x.name, "description": x.description, "parameters": x.input_schema}} for x in t.Til.method_tools()]; print(len(tiktoken.get_encoding("o200k_base").encode(json.dumps(d))))'
```

## The `llm til` command

```
llm til [PROMPT] [--cid ID] [-m MODEL] [--slug SLUG] [--log]
```

One request: the logged conversation (the latest, or `--cid`) and PROMPT, to
the model of the conversation (or `-m`), without tool definitions. The reply
streams to the terminal and goes to a new note `~/.kb/til-YYMM-<slug>.md`.

- PROMPT replaces `TIL_PROMPT` (55 tokens: note for a senior engineer; facts,
  decisions, commands, pitfalls; concise lists; ASD-STE100).
  `TIL_OUTPUT_RULE` (30 tokens) is always added: only the note, a short
  `# Title`, impersonal README style.
- Slug: `--slug`, else from the `# Title` (ASCII, lowercase, no leading `til`,
  at most 50 characters), else `note`. A name in use gets `-2` ... `-99` and a
  warning; no overwrite.
- Not logged, so a later `llm -c` does not send the note again (and `llm logs`
  has no usage record); `--log` stores it. If the file cannot be written, the
  reply is logged anyway (`llm logs -n 1`).
- `~/.kb/`, `--slug`, the conversation and the model are checked before the
  paid request. `Til_create` safety rules and limits apply.

| 20,000-token conversation, 1,500-token note | Requests | Input tokens | Output tokens |
| --- | --- | --- | --- |
| `llm -c -T Til '...'` | 2 | about 42,000 (less with caching) | about 1,550 |
| `llm til` | 1 | about 20,100 | about 1,500 |

Limits:

- A history with tool calls goes without tool definitions. `codex/gpt-6-luna`
  accepts it; other providers can refuse it (then use `llm -c -T Til`).
- Default options from `llm models options` are not applied.
- It uses the internal `llm.cli.load_conversation`; a test catches changes.

## Development

```bash
uv sync                          # builds this package (editable) into .venv; sets its version
uv run pytest
uv run llm plugins               # version of the local build, e.g. 0.1.0.post2+g1a2b3c4
uv run llm tools list | grep Til_
uv run llm til --help            # the local code runs; no build or install needed
uv run --with llm-openai-codex llm -m codex/gpt-6-luna -T Til 'List my notes.'
```

- Version: `uv sync` (also done by `uv run`) builds the package, and `hatch-vcs`
  then takes the version from `git describe`: `0.1.0` on the tag,
  `0.1.0.postN+g<hash>` N commits later (`post-release` scheme), `.d<date>`
  added for uncommitted changes. `[tool.uv] cache-keys` makes uv rebuild after
  a new commit or tag.
- `uv run llm` uses the same `llm` user directory (keys, logs) as the global
  `llm`, unless `LLM_USER_PATH` is set, so `uv run llm til` can save a
  conversation of the global `llm`. The `.venv` has no model plugins: add one
  with `--with`.
- Sandbox (e.g. Claude Code): `~/.cache/uv` can be read-only. Point uv to a
  writable cache with `UV_CACHE_DIR="$TMPDIR/uv-cache"` (or `--cache-dir`).
- `llm` reads stdin if it is not a terminal, so use `</dev/null` in scripts.

Tests use a temporary `HOME` (never the real `~/.kb/`) and `LLM_USER_PATH`; CLI
tests use the `echo` model of [llm-echo](https://github.com/simonw/llm-echo).

`.github/workflows/test.yml` runs the tests with Python 3.10-3.14 on each push
to `master`, on pull requests, and once a month.

`uv.lock` is not committed: this is a library, and unlocked resolution finds
problems with new `llm` releases early. It has no version of this package (dynamic).
`[tool.uv] exclude-newer` keeps package releases newer than 34 hours out of every resolution.

## Release

Design rule: a GitHub release comes from `git push` (of a tag), so no `gh` needed,
no version commit: the git tag is the only place of the version.

- Version: from the tag (`hatch-vcs`); see [Development](#development).
- Tags: annotated only (`git tag -a`). The tag message is the release notes,
  separate from the commit messages, and `git push --follow-tags` sends the
  tag with the branch. Lightweight tags would lack a message, and would need a
  separate tag push to origin, hence are suboptimal.
- Use `git config push.followTags true` to not have to use --follow-tags with push
- `.github/workflows/release.yml` runs on a pushed `v*` tag: it checks that the
  tag is an annotated `vX.Y.Z`, runs the tests, checks that the built wheel has
  the tag version, then runs `gh release create --notes-from-tag` in GitHub
  Actions.
- We use `v1.2.3` and `1.2.3`:
  - `v1.2.3`: git tag, GitHub release, `llm install '...@v1.2.3'`.
  - `1.2.3`: Python version (package metadata, `llm plugins`, wheel and sdist names);

### Steps for a release

```bash
uv run pytest && uv build              # 1. checks pass (version: 0.1.0.postN+g<hash>)
tmp/release-notes.sh                   # 2. (optional) see commits since the last release
git tag -a v0.2.0 -m "Release 0.2.0" -m "<notes>"  # 3. annotated tag on HEAD; notes e.g. from 2
tmp/release-notes.sh v0.2.0            # 4. (optional) check the notes
git push --follow-tags                 # 5. branch and tag; release.yml makes the release
```

Troubleshooting:
- Wrong tag before the push: `git tag -d v0.2.0`, then tag again.
- `release.yml` failed after the push: no release exists. Remove the tag
  (`git push origin :refs/tags/v0.2.0` and `git tag -d v0.2.0`), fix, tag and
  push again. Never move the tag of a published release; release a new version.

### PyPI

There is no PyPI publication at the moment. If it is decided later:

- Add a `publish` job to `release.yml` (`uv build`, then
  `pypa/gh-action-pypi-publish`; `permissions: id-token: write`; environment
  `pypi`). A separate workflow `on: release` does not work here: a release made
  with the workflow token starts no other workflow.
- On pypi.org, add a pending trusted publisher: project `llm-tool-til`,
  repository `rdslw/llm-tool-til`, workflow `release.yml`, environment `pypi`.
- In the GitHub repository settings, add the environment `pypi`.
- Add `llm install llm-tool-til` to [Installation](#installation).
