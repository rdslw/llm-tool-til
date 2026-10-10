"""Til toolbox and `llm til` command for Simon Willison's LLM: markdown notes in ~/.kb/.

The tools can list, view and search .md, .txt, .sh and extensionless files directly
in ~/.kb/. They can create only notes named til-YYMM-<slug>.md, and edit only .md and
.txt files. They cannot overwrite or delete a file, and never create ~/.kb/ itself.

The `llm til` command writes a note of a logged conversation with one request.
"""

import re
import time
import unicodedata
from pathlib import Path

import click
import llm

SAFE_CHARS_RE = re.compile(r"[a-zA-Z0-9_.-]+")
EXTENSIONS = {"md", "txt", "sh"}  # plus files without an extension
EDIT_EXTENSIONS = {"md", "txt"}
MAX_SLUG_LENGTH = 60
MAX_BYTES = 100 * 1024  # for one file
MAX_LINES = 2000  # for one file that the tools write
MAX_LIST_LINES = 400
MAX_SEARCH_MATCHES = 100
MAX_SEARCH_LINES = 600  # matches plus context lines
SEARCH_CONTEXT = 3  # lines before and after a match, like grep -C3
MAX_LINE_CHARS = 200  # for one Til_search output line
MAX_SUFFIX = 99  # llm til: til-YYMM-<slug>-2.md ... -99.md when the name is in use
TIL_PROMPT = (
    "Write a markdown TIL note of this conversation for a senior engineer who will reread it to "
    "recall the topic: key facts, decisions, commands, pitfalls. Be concise; use lists; "
    "add a diagram if it helps. Use ASD-STE100 Simplified Technical English."
)
TIL_OUTPUT_RULE = (
    "Reply with only the markdown note, starting with a short '# Title' line. "
    "Use impersonal README style, without 'I' or 'you'."
)


def _is_kb_name(name: str) -> bool:
    # Whitelisted characters only, no hidden files, and an allowed extension.
    # Such a name has no "/" and does not start with ".", so it is directly in root.
    if not SAFE_CHARS_RE.fullmatch(name) or name.startswith("."):
        return False
    return "." not in name or name.rsplit(".", 1)[1].lower() in EXTENSIONS


def _check_slug(slug: str) -> None:
    if len(slug) > MAX_SLUG_LENGTH or not SAFE_CHARS_RE.fullmatch(slug):
        raise ValueError(
            f"Invalid slug {slug!r}: use 1-{MAX_SLUG_LENGTH} characters from a-z A-Z 0-9 _ . -"
        )


def _note_name(slug: str) -> str:
    return f"til-{time.strftime('%y%m')}-{slug}.md"


def _slug_from_title(text: str) -> str:
    # From the first "# Title" line: ASCII, lowercase, other characters become "-".
    title = next((line[2:] for line in text.splitlines() if line.startswith("# ")), "")
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9_.]+", "-", title.lower()).strip("-._")
    slug = re.sub(r"^til\b[-._]*", "", slug)  # the file name starts with "til-" already
    if len(slug) > 50:
        slug = slug[:51].rsplit("-", 1)[0][:50]  # cut at a word boundary
    return slug.strip("-._") or "note"


def _check_size(text: str, filename: str) -> None:
    size, lines = len(text.encode("utf-8")), len(text.splitlines())
    if size > MAX_BYTES or lines > MAX_LINES:
        raise ValueError(
            f"{filename} would have {size} bytes and {lines} lines; the limit is "
            f"{MAX_BYTES} bytes and {MAX_LINES} lines"
        )


class Til(llm.Toolbox):
    """Create, view, edit, list and search TIL markdown notes in ~/.kb/."""

    def __init__(self):
        self.root = Path("~/.kb").expanduser().resolve()

    def _check_root(self) -> None:
        if not self.root.is_dir():
            raise FileNotFoundError("~/.kb/ does not exist: the user must create it first")

    def _path(self, filename: str, edit: bool = False) -> Path:
        if not _is_kb_name(filename):
            raise ValueError(f"Invalid file name {filename!r}: use a name from Til_list_files")
        if edit and filename.rsplit(".", 1)[-1].lower() not in EDIT_EXTENSIONS:
            raise ValueError(f"{filename} cannot change: only .md and .txt files can change")
        self._check_root()
        path = self.root / filename
        # A symlink could point outside root, so refuse symlinks.
        if path.is_symlink():
            raise ValueError(f"{filename} is a symlink; symlinks are not allowed")
        return path

    def _read(self, filename: str, edit: bool = False) -> str:
        path = self._path(filename, edit)
        if not path.is_file():
            raise FileNotFoundError(f"{filename} does not exist; see Til_list_files")
        if path.stat().st_size > MAX_BYTES:
            raise ValueError(f"{filename} is larger than {MAX_BYTES} bytes")
        return path.read_text(encoding="utf-8")

    def _files(self) -> list[Path]:
        # All files the tools can see, newest (last changed) first.
        self._check_root()
        files = [
            p
            for p in self.root.iterdir()
            if _is_kb_name(p.name) and p.is_file() and not p.is_symlink()
        ]
        return sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)

    def _write_new(self, filename: str, content: str) -> None:
        path = self._path(filename, edit=True)
        _check_size(content, filename)
        # Mode "x" creates the file atomically and fails if it exists.
        with open(path, "x", encoding="utf-8") as f:
            f.write(content)

    def create(self, slug: str, content: str) -> str:
        """Create a new markdown note ~/.kb/til-YYMM-<slug>.md; the tool adds YYMM.
        slug: short topic stub, characters a-zA-Z0-9_.- only. content: impersonal README
        style, no I/you. Fails if the note exists. No need to list files first."""
        _check_slug(slug)
        filename = _note_name(slug)
        try:
            self._write_new(filename, content)
        except FileExistsError:
            raise FileExistsError(
                f"{filename} already exists; pick another slug or use Til_str_replace"
            ) from None
        return f"Created {filename}. Do not repeat full note text."

    def view(self, filename: str) -> str:
        """Return the full text of a file."""
        return self._read(filename)

    def str_replace(self, filename: str, old_str: str, new_str: str) -> str:
        """Edit a .md or .txt file: replace old_str, which must occur exactly once, with
        new_str. Copy old_str exactly from Til_view."""
        text = self._read(filename, edit=True)
        count = text.count(old_str)
        if count != 1:
            raise ValueError(
                f"old_str occurs {count} times in {filename}; it must occur exactly once: "
                "copy it exactly from Til_view, with enough surrounding text to be unique"
            )
        new_text = text.replace(old_str, new_str)
        _check_size(new_text, filename)
        self._path(filename, edit=True).write_text(new_text, encoding="utf-8")
        return f"Edited {filename}"

    def list_files(self) -> str:
        """List the files in ~/.kb, newest first."""
        names = [p.name for p in self._files()]
        if len(names) > MAX_LIST_LINES:
            hidden = len(names) - MAX_LIST_LINES
            names = names[:MAX_LIST_LINES] + [f"[{hidden} older files not shown; use Til_search]"]
        return "\n".join(names) or "No files yet."

    def search(self, query: str) -> str:
        """Find query (plain text, case-insensitive) in all files. Output like grep -n -C3,
        newest files first."""
        if not query.strip():
            raise ValueError("query must not be empty")
        needle, out, matches = query.lower(), [], 0
        for path in self._files():
            # Read at most MAX_BYTES characters, so a large file cannot flood the output.
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read(MAX_BYTES).splitlines()
            hits = [i for i, line in enumerate(lines) if needle in line.lower()]
            hits = hits[: MAX_SEARCH_MATCHES - matches]
            matches += len(hits)
            near = range(-SEARCH_CONTEXT, SEARCH_CONTEXT + 1)
            shown = sorted({i + d for i in hits for d in near if 0 <= i + d < len(lines)})
            previous = None
            for j in shown:
                if out and (previous is None or j != previous + 1):
                    out.append("--")
                sep = ":" if j in hits else "-"
                out.append(f"{path.name}{sep}{j + 1}{sep}{lines[j][:MAX_LINE_CHARS]}")
                previous = j
            if matches == MAX_SEARCH_MATCHES:
                out.append(f"[stopped at {MAX_SEARCH_MATCHES} matches; use a narrower query]")
                break
        if len(out) > MAX_SEARCH_LINES:
            out = out[:MAX_SEARCH_LINES] + [
                f"[stopped at {MAX_SEARCH_LINES} lines; use a narrower query]"
            ]
        return "\n".join(out) or f"No file contains {query!r}."


@llm.hookimpl
def register_tools(register):
    register(Til)


@llm.hookimpl
def register_commands(cli):
    @cli.command(name="til")
    @click.argument("prompt", required=False)
    @click.option(
        "--cid", "--conversation", "conversation_id", help="Conversation ID (default: the latest)"
    )
    @click.option("-m", "--model", "model_id", help="Model (default: the conversation model)")
    @click.option("--slug", help="Slug for the file name (default: from the '# Title' line)")
    @click.option("--log", is_flag=True, help="Store the response in the conversation")
    def til(prompt, conversation_id, model_id, slug, log):
        """Write a logged conversation as a TIL note into ~/.kb/, with one request.

        PROMPT replaces the default instructions. By default the note is not stored
        in the conversation, so a later llm -c does not send it again; use --log to
        store it. If the file cannot be written, the reply is stored in any case.
        If the file name is in use, a suffix -2, -3, ... is added.
        """
        import sqlite_utils
        from llm.cli import load_conversation, logs_db_path
        from llm.migrations import migrate

        toolbox = Til()
        # Check all that can fail before the request is paid for.
        try:
            toolbox._check_root()
            if slug:
                _check_slug(slug)
            conversation = load_conversation(conversation_id)
            if conversation is None:
                raise click.ClickException("No conversation found: chat with llm first")
            if model_id:
                conversation.model = llm.get_model(model_id)
        except (OSError, ValueError, llm.UnknownModelError) as ex:
            raise click.ClickException(str(ex))

        try:
            response = conversation.prompt(f"{prompt or TIL_PROMPT}\n\n{TIL_OUTPUT_RULE}")
            for chunk in response:
                click.echo(chunk, nl=False)
            click.echo()
            text = response.text()
        except Exception as ex:  # noqa: BLE001 - show provider errors like llm does
            raise click.ClickException(str(ex))
        if response.tool_calls() or not text.strip():
            raise click.ClickException("The response has no note text; nothing written")
        def store():
            db = sqlite_utils.Database(logs_db_path())
            migrate(db)
            response.log_to_db(db)

        if log:
            store()
        base = slug or _slug_from_title(text)
        names = [_note_name(base)] + [_note_name(f"{base}-{n}") for n in range(2, MAX_SUFFIX + 1)]
        error = None
        for filename in names:
            try:
                toolbox._write_new(filename, text.strip() + "\n")
                break
            except FileExistsError:
                continue
            except (OSError, ValueError) as ex:
                error = str(ex)
                break
        else:
            error = f"{names[0]} and suffixes -2 to -{MAX_SUFFIX} are in use"
        if error:
            # The reply is paid for: log it also without --log, so it is not lost.
            if not log:
                store()
            raise click.ClickException(f"{error}; nothing written. The reply is in: llm logs -n 1")
        if filename != names[0]:
            click.echo(f"Warning: {names[0]} exists, so the note is {filename}", err=True)
        click.echo(f"Saved {toolbox.root / filename}", err=True)
