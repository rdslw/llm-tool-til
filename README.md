# llm-tool-til

Til toolbox and `llm til` command for [Simon Willison's LLM](https://llm.datasette.io/).

After a long conversation with `llm`, ask the model for a summary, a primer, or
documentation of the conversation. The model writes it as a markdown note into
`~/.kb/`, with a name like `til-2610-git-rebase-onto.md`. Two ways:

- `llm -c -T Til '...'`: the `Til` toolbox. The model calls tools to create,
  edit, view, list and search notes. A note costs at least two requests.
- `llm til ['...']`: one request; the plugin writes the reply to a new note. See
  [The `llm til` command](#the-llm-til-command).

The model does the important work: it selects the content, the structure and the
markdown format. The plugin only stores the notes safely.

`AGENTS.md` points at this file, so keep operational project knowledge here.

## Installation

The package is not on PyPI. Install it into the `llm` environment with one of:

```bash
# from a local checkout; -e (editable): changes in the directory apply at once
llm install -e /path/to/llm-tool-til

# from GitHub (for SSH access: git+ssh://git@github.com/rdslw/llm-tool-til)
llm install 'git+https://github.com/rdslw/llm-tool-til'

# from GitHub, a fixed release
llm install 'git+https://github.com/rdslw/llm-tool-til@v0.1.0'
```

Then create `~/.kb/` once (the toolbox never creates it) and check the install:

```bash
mkdir ~/.kb
llm tools list | grep Til_                  # shows the five Til_ tools
```

`llm install` also works when `llm` is a `uv tool`, because `llm` depends on `pip`.

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

`llm` stops after 5 tool calls in one prompt by default. For many edits, use a
higher limit, e.g. `--chain-limit 15`.

## Tools

| Tool | Use |
| --- | --- |
| `Til_create(slug, content)` | Create the note `til-YYMM-<slug>.md`. Fails if the file exists. The result tells the model not to repeat the note text. |
| `Til_str_replace(filename, old_str, new_str)` | Replace text that occurs exactly once in a `.md` or `.txt` file. |
| `Til_view(filename)` | Return the full text of a file. |
| `Til_list_files()` | List the file names, newest first. |
| `Til_search(query)` | Find `query` (plain text, case-insensitive) in all files. Output like `grep -n -i -C3`, newest files first. |

Two groups of files:

- Notes: `til-YYMM-<slug>.md`. The tools can create, edit, view, list and search them.
  `YYMM` is the local year and month at creation. The model gives only the `slug`:
  1-60 characters from `[a-zA-Z0-9_.-]`. Example: slug `git-rebase-onto` gives
  `til-2610-git-rebase-onto.md`.
- Other files directly in `~/.kb/` with the extension `.md`, `.txt` or `.sh`
  (any case), or with no extension. The tools can view, list and search them.
  `Til_str_replace` can edit the `.md` and `.txt` files; `.sh` files and files
  without an extension are read-only.

Newest first means last changed first (file modification time).

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

`-T Til` adds the definitions of the five tools to every request. As JSON in the
OpenAI function format that `llm` sends, they are 1508 characters, about 420
tokens (422 with the `o200k_base` tokenizer, 426 with `cl100k_base`). The budget
is 450 tokens.

| Tool | Tokens |
| --- | --- |
| `Til_create` | 132 |
| `Til_str_replace` | 111 |
| `Til_search` | 79 |
| `Til_view` | 58 |
| `Til_list_files` | 46 |

273 of the 422 tokens are fixed JSON structure: tool names, parameter names and
types. Only the remaining tokens are description text. The descriptions give
only what the model needs before the first call; guidance for a failed call is in
the error messages, which cost tokens only when an error occurs.

Providers convert the definitions to their own format and can add fixed tool-use
instructions, so the billed number is different. The JSON count is an upper
bound: `codex/gpt-6-luna` (plugin `llm-openai-codex` 0.8.0) bills the five
definitions as 244 tokens. To see the real number for a model, compare
`llm -u -m MODEL 'hi'` with `llm -u -m MODEL -T Til 'hi'`.

Each tool call adds one more request to the chain, and each request sends the full
conversation again: the earlier messages, the tool definitions, and all earlier
tool calls and tool results.

- After a long conversation, `llm -c -T Til '...'` sends that conversation at
  least two times: once to get the tool call, and once with the tool result.
- The note text that the model gives to `Til_create` or `Til_str_replace` costs
  output tokens once. After that, it is input in each later request of the chain
  and of later `llm -c` prompts.
- Provider prompt caching, if available, makes the repeated input cheaper. Check
  it, do not assume it: `llm logs --json` shows the cached tokens of each request
  if the provider reports them. With `codex/gpt-6-luna` and `llm-openai-codex`
  0.8.0, all requests in the tests below had 0 cached tokens: that plugin
  version sends no `session-id` header, so the backend gives each request a
  random cache key. With a patched plugin that sends the conversation ID as
  `session-id`, request 2 of a tool chain had 6,656 of 7,072 input tokens
  cached.
- The `Til_create` result tells the model "Do not repeat full note text.", so
  the final answer does not pay for the note a second time.
- `llm til` avoids the second request and keeps the note out of later `llm -c`
  prompts; see the next section.

Upper bounds for one tool result, at the limits above (`o200k_base`, English
text; other languages and code give more tokens):

| Tool result | Upper bound |
| --- | --- |
| `Til_create`, `Til_str_replace` | about 30 tokens (one status line), about 50 for an error line |
| `Til_list_files`, 400 names | about 4,000 tokens |
| `Til_view`, 100 KB | about 20,000-25,000 tokens |
| `Til_search`, 600 lines of 200 characters | about 30,000-35,000 tokens |

The docstrings of the tool methods are the tool descriptions, so keep them short.
Recount the definition tokens after a change:

```bash
uv run --with tiktoken python -c 'import json, tiktoken, llm_tool_til as t; d = [{"type": "function", "function": {"name": x.name, "description": x.description, "parameters": x.input_schema}} for x in t.Til.method_tools()]; print(len(tiktoken.get_encoding("o200k_base").encode(json.dumps(d))))'
```

## The `llm til` command

```
llm til [PROMPT] [--cid ID] [-m MODEL] [--slug SLUG] [--log]
```

It sends one request: the logged conversation (the latest one, or `--cid`), then
PROMPT. It sends no tool definitions. The reply streams to the terminal, and the
plugin writes it to a new note `~/.kb/til-YYMM-<slug>.md`.

- PROMPT replaces the default prompt `TIL_PROMPT` (55 tokens):
  "Write a markdown TIL note of this conversation for a senior engineer who will
  reread it to recall the topic: key facts, decisions, commands, pitfalls. Be
  concise; use lists; add a diagram if it helps. Use ASD-STE100 Simplified
  Technical English."
- The plugin always adds `TIL_OUTPUT_RULE` (30 tokens) after the prompt: "Reply
  with only the markdown note, starting with a short '# Title' line. Use
  impersonal README style, without 'I' or 'you'."
- `--slug` gives the slug. Without it, the slug comes from the `# Title` line:
  ASCII, lowercase, other characters become `-`, a leading word `til` is
  removed, at most 50 characters cut at a word boundary, or `note` if there is
  no title.
- If the file name is in use, the plugin adds `-2`, `-3`, ... up to `-99` and
  shows a warning. It never overwrites a file.
- `-m` uses another model than the model of the conversation.
- Logging is off: the reply is not stored in the conversation, so a later
  `llm -c` does not send the note again. `--log` stores it in the conversation.
  Without `--log`, `llm logs` has no record of the request and its token usage.
- Before the request, the plugin checks `~/.kb/`, `--slug`, the conversation
  and the model, so an error costs nothing.
- The same safety rules and limits as for `Til_create` apply. If the file cannot
  be written (larger than 100 KB or 2000 lines, all names up to `-99` in use, a
  file system error), the plugin stores the paid reply in the conversation logs
  also without `--log`; `llm logs -n 1` shows it. If the reply has no text, or
  is a tool call, no file is written.

Cost for the example of a 20,000-token conversation and a 1,500-token note
(definitions counted as 244 tokens, as billed by `codex/gpt-6-luna`):

| Command | Requests | Input tokens | Output tokens |
| --- | --- | --- | --- |
| `llm -c -T Til '...'` | 2 | about 42,000, less if the provider caches | about 1,550 |
| `llm til` | 1 | about 20,100 | about 1,500 |

Measured with `codex/gpt-6-luna` (plugin `llm-openai-codex` 0.8.0), after a
2,162-token conversation (46 input, 2,116 output):

| Command | Request | Input tokens | Output tokens | Cached |
| --- | --- | --- | --- | --- |
| `llm -c -T Til 'Save a TIL note of this conversation.'` | 1: tool call | 2,421 | 1,023 | 0 |
| | 2: tool result | 3,474 | 21 | 0 |

The final answer was one line ("Saved as `~/.kb/til-2610-git-rebase.md`."), so
the "Do not repeat full note text." hint worked. A later `llm til` in the same
conversation had 3,342 input tokens: the 1,023-token note from the tool call
was in the history again.

Limits:

- If the conversation used tools, its history contains tool calls, and `llm til`
  sends no tool definitions. `codex/gpt-6-luna` accepted such a history (test
  with the `llm_time` tool). Other providers can refuse it; then use
  `llm -c -T Til '...'`.
- Default model options from `llm models options` are not applied.
- The command uses `llm.cli.load_conversation`, an internal `llm` function. A
  test fails if a new `llm` release changes it.

## Compared to llm-tools-edit

The tools are a subset of
[simonw/llm-tools-edit](https://github.com/simonw/llm-tools-edit) `Filesystem`
(`create`, `view`, `str_replace` and `list_files`), plus `search`. Not included:
`insert` (use `str_replace` on a unique anchor), line numbers and `view_range`,
`max_lines` and `max_chars`, `MemoryFS`, `SQLiteFS`, and a configurable root
directory.

`Til_search` is pure Python, not a call to `rg` or `grep`. It has the same output
format as `grep -n -i -C3`, but it needs no external program, has the same
behavior on Linux and macOS, ignores `~/.ripgreprc` and locale settings, and
applies the same file name and symlink checks as the other tools, while it 
allows easier limits implementation and enforcing.

## Development

```bash
uv sync                                     # installs this package into .venv
uv run pytest
uv run llm tools list | grep Til_
uv build
```

The tests set `HOME` to a temporary directory, so they never touch the real
`~/.kb/`, and `LLM_USER_PATH` to a temporary directory for the `llm` logs. The
tests of `-T Til` and `llm til` run the `llm` CLI with the `echo` model from
[llm-echo](https://github.com/simonw/llm-echo), which replies with the prompt
it got as JSON and replays tool calls from the prompt.

`.github/workflows/test.yml` runs the tests with Python 3.10-3.14 on each push
to `master`, on pull requests, and once a month.

`uv.lock` is not committed: this is a library, and unlocked resolution finds
problems with new `llm` releases early. `[tool.uv] exclude-newer` keeps package
releases newer than 34 hours out of every resolution.

## Release

- Before a release, `uv run pytest` and `uv build` must pass.
- Set `version` (`X.Y.Z`) in `pyproject.toml` in the last commit of the release.
  There is no separate version (bump) commit. A version is never used again.
- Put an annotated tag `vX.Y.Z` directly on that commit. The tag message is the
  release notes:
  `git tag -a vX.Y.Z -m "Release X.Y.Z" -m "- change 1"`
- Push the branch and the tag: `git push origin master --follow-tags`.
- Make the GitHub release from the tag:
  `gh release create vX.Y.Z --notes-from-tag --verify-tag`.
- There is no PyPI publication at the moment. Users install from GitHub, with
  `@vX.Y.Z` for a fixed release.

If PyPI publication is decided later:

- Add `.github/workflows/publish.yml` as in `llm-tool-brave`: on a published
  release, test the built wheel (`uv sync --all-groups --no-editable`), run
  `uv build`, and publish with `pypa/gh-action-pypi-publish`.
- On pypi.org, add a pending trusted publisher: project `llm-tool-til`,
  repository `rdslw/llm-tool-til`, workflow `publish.yml`, environment `pypi`.
- In the GitHub repository settings, add the environment `pypi`.
- Add `llm install llm-tool-til` to [Installation](#installation).
