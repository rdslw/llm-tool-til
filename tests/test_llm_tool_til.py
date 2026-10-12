import json
import os
import time

import llm
import pytest
from click.testing import CliRunner
from llm.cli import cli

import llm_tool_til
from llm_tool_til import Til


@pytest.fixture
def kb(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    kb = tmp_path / ".kb"
    kb.mkdir()
    return kb


@pytest.fixture
def til(kb):
    return Til()


def note_name(slug):
    return f"til-{time.strftime('%y%m')}-{slug}.md"


def write_files(kb, files):
    # files: {name: text}, oldest first; each file gets a different mtime.
    for age, (name, text) in enumerate(reversed(list(files.items()))):
        (kb / name).write_text(text)
        os.utime(kb / name, (1_000_000 - age, 1_000_000 - age))


def test_register_tools_registers_til():
    registered = []
    llm_tool_til.register_tools(registered.append)
    assert registered == [Til]


def test_tool_names_use_til_prefix(til):
    # llm 0.32+ finds the toolbox for llm -c from the "Til_" prefix.
    # method_tools() exists in llm 0.26 and later; tools() came later.
    names = sorted(tool.name for tool in til.method_tools())
    assert names == ["Til_create", "Til_list_files", "Til_search", "Til_str_replace", "Til_view"]


def test_create_writes_note(til, kb):
    name = note_name("git-rebase-onto")
    assert til.create("git-rebase-onto", "# Git rebase --onto\n") == (
        f"Created {name}. Do not repeat full note text."
    )
    assert (kb / name).read_text() == "# Git rebase --onto\n"


@pytest.mark.parametrize("slug", ["Docker_Tips.v2", "-x", "a--b", "..", "x" * 60])
def test_create_accepts_whitelisted_slug(til, kb, slug):
    til.create(slug, "text\n")
    assert (kb / note_name(slug)).read_text() == "text\n"


@pytest.mark.parametrize(
    "slug", ["", "../evil", "a/b", "with space", "a:b", "zażółć", "x\n", "x" * 61]
)
def test_create_rejects_bad_slug(til, kb, slug):
    with pytest.raises(ValueError, match="Invalid slug"):
        til.create(slug, "text")
    assert list(kb.iterdir()) == []


def test_create_fails_if_note_exists(til, kb):
    til.create("topic", "first\n")
    with pytest.raises(FileExistsError, match="already exists"):
        til.create("topic", "second\n")
    assert (kb / note_name("topic")).read_text() == "first\n"


def test_all_tools_fail_if_kb_dir_is_missing(til, kb):
    kb.rmdir()
    for call in [
        lambda: til.create("topic", "text"),
        lambda: til.view("til-2610-topic.md"),
        lambda: til.str_replace("til-2610-topic.md", "a", "b"),
        til.list_files,
        lambda: til.search("text"),
    ]:
        with pytest.raises(FileNotFoundError, match="does not exist"):
            call()
    assert not kb.exists()


@pytest.mark.parametrize("name", ["til-2610-a.md", "notes.txt", "script.sh", "README", "Doc.MD"])
def test_view_returns_content_of_kb_files(til, kb, name):
    (kb / name).write_text("# Title\n\nBody\n")
    assert til.view(name) == "# Title\n\nBody\n"


def test_view_missing_file(til):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        til.view("til-2610-missing.md")


@pytest.mark.parametrize(
    "filename",
    [
        "../.bashrc",
        "/etc/passwd",
        ".hidden",
        ".",
        "..",
        "sub/notes.md",
        "x.py",
        "x.tar.gz",
        "x.",
        "x.md\n",
        "x.md\x00",
        "zażółć.md",
        "x y.md",
    ],
)
def test_bad_filenames_are_refused(til, filename):
    with pytest.raises(ValueError, match="Invalid file name"):
        til.view(filename)
    with pytest.raises(ValueError, match="Invalid file name"):
        til.str_replace(filename, "a", "b")


@pytest.mark.parametrize("name", ["notes.md", "log.txt", "Doc.MD", "LOG.TXT", "til-2610-x.txt"])
def test_str_replace_edits_md_and_txt_files(til, kb, name):
    (kb / name).write_text("old\n")
    assert til.str_replace(name, "old", "new") == f"Edited {name}"
    assert (kb / name).read_text() == "new\n"


@pytest.mark.parametrize("name", ["script.sh", "run.SH", "README"])
def test_str_replace_refuses_sh_and_extensionless_files(til, kb, name):
    (kb / name).write_text("old\n")
    with pytest.raises(ValueError, match="only .md and .txt files can change"):
        til.str_replace(name, "old", "new")
    assert (kb / name).read_text() == "old\n"


def test_symlink_out_of_kb_is_refused(til, kb, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("secret\n")
    (kb / "til-2610-link.md").symlink_to(secret)
    with pytest.raises(ValueError, match="symlink"):
        til.view("til-2610-link.md")
    with pytest.raises(ValueError, match="symlink"):
        til.str_replace("til-2610-link.md", "secret", "changed")
    assert til.list_files() == "No files yet."
    assert til.search("secret") == "No file contains 'secret'."
    assert secret.read_text() == "secret\n"


def test_create_does_not_write_through_symlink(til, kb, tmp_path):
    outside = tmp_path / "outside.md"
    (kb / note_name("topic")).symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        til.create("topic", "text")
    assert not outside.exists()


def test_str_replace_edits_unique_text(til, kb):
    til.create("topic", "# Title\n\nold line\n")
    name = note_name("topic")
    assert til.str_replace(name, "old line", "new line") == f"Edited {name}"
    assert (kb / name).read_text() == "# Title\n\nnew line\n"


@pytest.mark.parametrize("old_str, count", [("missing", 0), ("dup", 2)])
def test_str_replace_requires_exactly_one_match(til, kb, old_str, count):
    til.create("topic", "dup\ndup\n")
    name = note_name("topic")
    with pytest.raises(ValueError, match=f"occurs {count} times"):
        til.str_replace(name, old_str, "x")
    assert (kb / name).read_text() == "dup\ndup\n"


@pytest.mark.parametrize(
    "content", ["x" * (100 * 1024 + 1), "ż" * (50 * 1024 + 1), "line\n" * 2001]
)
def test_create_refuses_too_large_note(til, kb, content):
    with pytest.raises(ValueError, match="the limit is 102400 bytes and 2000 lines"):
        til.create("big", content)
    assert list(kb.iterdir()) == []


def test_create_accepts_note_at_the_limits(til):
    til.create("lines", "line\n" * 2000)
    til.create("bytes", "x" * 100 * 1024)


def test_str_replace_refuses_too_large_result(til, kb):
    til.create("topic", "anchor\n")
    name = note_name("topic")
    with pytest.raises(ValueError, match="the limit is"):
        til.str_replace(name, "anchor\n", "line\n" * 2001)
    assert (kb / name).read_text() == "anchor\n"


def test_view_refuses_too_large_file(til, kb):
    (kb / "big.txt").write_text("x" * (100 * 1024 + 1))
    with pytest.raises(ValueError, match="larger than 102400 bytes"):
        til.view("big.txt")


def test_list_files_without_files(til):
    assert til.list_files() == "No files yet."


def test_list_files_shows_allowed_files_newest_first(til, kb):
    write_files(
        kb,
        {
            "til-2611-old.md": "x",
            "script.sh": "x",
            "notes.txt": "x",
            "README": "x",
            "til-2509-new.md": "x",
            "code.py": "x",
            ".hidden": "x",
            "archive.tar.gz": "x",
        },
    )
    (kb / "subdir").mkdir()
    (kb / "dir.md").mkdir()
    assert til.list_files().splitlines() == [
        "til-2509-new.md",
        "README",
        "notes.txt",
        "script.sh",
        "til-2611-old.md",
    ]


def test_list_files_stops_at_max_lines(til, kb, monkeypatch):
    monkeypatch.setattr(llm_tool_til, "MAX_LIST_LINES", 2)
    write_files(kb, {"a.md": "x", "b.md": "x", "c.md": "x"})
    assert til.list_files().splitlines() == [
        "c.md",
        "b.md",
        "[1 older files not shown; use Til_search]",
    ]


def test_search_output_is_like_grep_with_context(til, kb):
    eleven = ["l1", "hit two"] + [f"l{n}" for n in range(3, 11)] + ["Hit eleven", "l12"]
    write_files(
        kb,
        {
            "til-2509-old.md": "old hit\n",
            "code.py": "hit\n",
            "a.txt": "\n".join(eleven) + "\n",
        },
    )
    assert til.search("HIT").splitlines() == [
        "a.txt-1-l1",
        "a.txt:2:hit two",
        "a.txt-3-l3",
        "a.txt-4-l4",
        "a.txt-5-l5",
        "--",
        "a.txt-8-l8",
        "a.txt-9-l9",
        "a.txt-10-l10",
        "a.txt:11:Hit eleven",
        "a.txt-12-l12",
        "--",
        "til-2509-old.md:1:old hit",
    ]


def test_search_without_match(til, kb):
    (kb / "a.md").write_text("text\n")
    assert til.search("nothing") == "No file contains 'nothing'."


def test_search_refuses_empty_query(til):
    with pytest.raises(ValueError, match="must not be empty"):
        til.search("  ")


def test_search_stops_at_max_matches(til, kb, monkeypatch):
    monkeypatch.setattr(llm_tool_til, "MAX_SEARCH_MATCHES", 2)
    monkeypatch.setattr(llm_tool_til, "SEARCH_CONTEXT", 0)
    write_files(kb, {"old.md": "hit\n", "new.md": "hit\nhit\n"})
    assert til.search("hit").splitlines() == [
        "new.md:1:hit",
        "new.md:2:hit",
        "[stopped at 2 matches; use a narrower query]",
    ]


def test_search_stops_at_max_lines(til, kb, monkeypatch):
    monkeypatch.setattr(llm_tool_til, "MAX_SEARCH_LINES", 3)
    (kb / "a.md").write_text("1\n2\n3\nhit\n5\n6\n7\n")
    assert til.search("hit").splitlines() == [
        "a.md-1-1",
        "a.md-2-2",
        "a.md-3-3",
        "[stopped at 3 lines; use a narrower query]",
    ]


def test_search_cuts_long_lines(til, kb):
    (kb / "a.md").write_text("hit " + "x" * 300 + "\n")
    assert til.search("hit") == "a.md:1:hit " + "x" * 196


def test_cli_tool_call_with_echo_model(kb, tmp_path, monkeypatch):
    # End to end: the plugin entry point, `-T Til`, and one tool call from the
    # llm-echo model, which replays the tool_calls given in the prompt.
    monkeypatch.setenv("LLM_USER_PATH", str(tmp_path / "llm"))
    prompt = json.dumps(
        {
            "prompt": "save a note",
            "tool_calls": [
                {
                    "name": "Til_create",
                    "arguments": {"slug": "cli-test", "content": "# CLI\n"},
                }
            ],
        }
    )
    result = CliRunner().invoke(cli, ["-m", "echo", "-T", "Til", prompt])
    assert result.exit_code == 0, result.output
    assert f"Created {note_name('cli-test')}" in result.output
    assert (kb / note_name("cli-test")).read_text() == "# CLI\n"


@pytest.fixture
def run_llm(kb, tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_USER_PATH", str(tmp_path / "llm"))
    return lambda *args: CliRunner().invoke(cli, list(args))


@pytest.fixture
def chain_limits(monkeypatch):
    # The chain_limit values that llm prompt gives to Conversation.chain().
    seen = []
    chain = llm.Conversation.chain

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("chain_limit"))
        return chain(self, *args, **kwargs)

    monkeypatch.setattr(llm.Conversation, "chain", spy)
    return seen


def chain_limit_option(command):
    return next(p for p in cli.commands[command].params if p.name == "chain_limit")


@pytest.mark.parametrize("command", ["prompt", "chat"])
def test_llm_chain_limit_default_is_unchanged(command):
    # If llm changes its --cl default, LLM_CHAIN_LIMIT needs a check.
    assert chain_limit_option(command).default == llm_tool_til.LLM_CHAIN_LIMIT


@pytest.mark.parametrize(
    "args, limit",
    [
        (["-T", "Til"], llm_tool_til.TIL_CHAIN_LIMIT),
        (["-T", "llm_version", "-T", "Til"], llm_tool_til.TIL_CHAIN_LIMIT),
        (["-T", "Til", "--cl", "5"], 5),
        (["-T", "Til", "--cl", "3"], 3),
        (["-T", "llm_version"], llm_tool_til.LLM_CHAIN_LIMIT),
    ],
)
def test_til_raises_default_chain_limit(run_llm, chain_limits, args, limit):
    result = run_llm("-m", "echo", *args, "hi")
    assert result.exit_code == 0, result.output
    assert chain_limits == [limit]


def test_til_keeps_changed_default_chain_limit(run_llm, chain_limits, monkeypatch):
    # A default other than LLM_CHAIN_LIMIT (new llm release, other plugin) stays.
    monkeypatch.setattr(chain_limit_option("prompt"), "default", 7)
    result = run_llm("-m", "echo", "-T", "Til", "hi")
    assert result.exit_code == 0, result.output
    assert chain_limits == [7]


def logged(run_llm):
    return json.loads(run_llm("logs", "list", "-n", "0", "--json").output)


def echoed_prompt(path):
    # The echo model replies with JSON that contains the prompt it got.
    return json.loads(path.read_text())["prompt"]


@pytest.mark.parametrize(
    "text, slug",
    [
        ("# Docker networks: bridge vs host\n\nbody\n", "docker-networks-bridge-vs-host"),
        ("intro\n# Zażółć gęślą jaźń: os.path & Docker\n", "zazoc-gesla-jazn-os.path-docker"),
        ("# " + "a" * 80, "a" * 50),
        ("# " + "word " * 20, "-".join(["word"] * 10)),
        ("# TIL: Move commits with `git rebase --onto`\n", "move-commits-with-git-rebase-onto"),
        ("# Tilde expansion in zsh\n", "tilde-expansion-in-zsh"),
        ("# TIL\n", "note"),
        ("no title line\n", "note"),
        ("## Only a subtitle\n", "note"),
        ("# ...\n", "note"),
    ],
)
def test_slug_from_title(text, slug):
    assert llm_tool_til._slug_from_title(text) == slug


def test_til_command_writes_note_without_logging(run_llm, kb):
    run_llm("-m", "echo", "hello")
    before = logged(run_llm)
    result = run_llm("til", "--slug", "demo")
    assert result.exit_code == 0, result.output
    note = kb / note_name("demo")
    assert f"Saved {Til().root / note.name}" in result.output
    prompt = f"{llm_tool_til.TIL_PROMPT}\n\n{llm_tool_til.TIL_OUTPUT_RULE}"
    assert echoed_prompt(note) == prompt
    assert note.read_text().endswith("}\n")
    assert logged(run_llm) == before


def test_til_command_custom_prompt_and_log(run_llm, kb):
    run_llm("-m", "echo", "hello")
    result = run_llm("til", "--log", "Custom instructions")
    assert result.exit_code == 0, result.output
    # The echo reply has no "# Title" line, so the slug is "note".
    note = kb / note_name("note")
    assert echoed_prompt(note) == f"Custom instructions\n\n{llm_tool_til.TIL_OUTPUT_RULE}"
    rows = logged(run_llm)
    assert len(rows) == 2
    assert rows[0]["conversation_id"] == rows[1]["conversation_id"]


def test_til_command_adds_suffix_and_warns(run_llm, kb):
    run_llm("-m", "echo", "hello")
    run_llm("til", "--slug", "demo")
    for n in (2, 3):
        result = run_llm("til", "--slug", "demo")
        assert result.exit_code == 0, result.output
        warning = f"Warning: {note_name('demo')} exists, so the note is {note_name(f'demo-{n}')}"
        assert warning in result.output
    assert sorted(p.name for p in kb.iterdir()) == sorted(
        note_name(s) for s in ["demo", "demo-2", "demo-3"]
    )


@pytest.mark.parametrize(
    "args, message",
    [
        (["til", "--slug", "a/b"], "Invalid slug"),
        (["til", "--cid", "missing"], "missing"),
        (["til", "-m", "no-such-model"], "no-such-model"),
    ],
)
def test_til_command_fails_before_request(run_llm, kb, args, message):
    run_llm("-m", "echo", "hello")
    result = run_llm(*args)
    assert result.exit_code == 1
    assert message in result.output
    assert list(kb.iterdir()) == []
    assert len(logged(run_llm)) == 1


def test_til_command_fails_without_kb_dir_or_conversation(run_llm, kb):
    result = run_llm("til")
    assert result.exit_code == 1
    assert "No conversation found" in result.output
    run_llm("-m", "echo", "hello")
    kb.rmdir()
    result = run_llm("til")
    assert result.exit_code == 1
    assert "~/.kb/ does not exist" in result.output


def test_til_command_logs_reply_if_note_is_too_large(run_llm, kb):
    run_llm("-m", "echo", "hello")
    result = run_llm("til", "--slug", "big", "x" * 100 * 1024)
    assert result.exit_code == 1
    assert "nothing written. The reply is in: llm logs -n 1" in result.output
    assert list(kb.iterdir()) == []
    assert len(logged(run_llm)) == 2


def test_til_command_logs_reply_if_all_names_are_in_use(run_llm, kb, monkeypatch):
    monkeypatch.setattr(llm_tool_til, "MAX_SUFFIX", 2)
    run_llm("-m", "echo", "hello")
    run_llm("til", "--slug", "demo")
    run_llm("til", "--slug", "demo")
    result = run_llm("til", "--slug", "demo")
    assert result.exit_code == 1
    assert "suffixes -2 to -2 are in use; nothing written" in result.output
    assert len(logged(run_llm)) == 2


def test_til_command_with_log_stores_reply_once_on_failure(run_llm, kb):
    run_llm("-m", "echo", "hello")
    result = run_llm("til", "--log", "--slug", "big", "x" * 100 * 1024)
    assert result.exit_code == 1
    assert len(logged(run_llm)) == 2
