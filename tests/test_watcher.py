import os
import time

from conftest import FIXTURES

from fleur.db import Database
from fleur.watcher import HistoryWatcher, complete_prefix_length


def test_incremental_reads(tmp_path):
    full = (FIXTURES / "cash_6max.txt").read_bytes()
    third = full.rindex(b"Winamax Poker")
    cut = full.index(b"*** FLOP ***", third)  # la 3e main est en cours d'écriture
    hist = tmp_path / "history"
    hist.mkdir()
    f = hist / "20261120_Nice 05_real_holdem_no-limit.txt"
    f.write_bytes(b"\xef\xbb\xbf" + full[:cut])
    (hist / "20261120_summary.txt").write_text("ignored")

    db = Database(":memory:")
    w = HistoryWatcher(db, [hist])
    got = w.poll()
    assert [h.hand_id for h in got] == ["18334871-1001-1700000001", "18334871-1002-1700000060"]
    assert w.poll() == []

    with open(f, "ab") as fh:
        fh.write(full[cut:])
    got = w.poll()
    assert [h.hand_id for h in got] == ["18334871-1003-1700000120"]
    assert db.hand_count() == 3


def test_last_hand_needs_summary_and_settle():
    data = (FIXTURES / "cash_6max.txt").read_bytes().rstrip()
    first_end = data.index(b"Winamax Poker", 10)
    assert complete_prefix_length(data, settled=False) == data.rindex(b"Winamax Poker")
    assert complete_prefix_length(data, settled=True) == len(data)
    assert complete_prefix_length(data + b"\n\n", settled=False) == len(data) + 2
    assert complete_prefix_length(data[: first_end - 200], settled=True) == 0


def test_find_history_dirs_current_client(tmp_path, monkeypatch):
    # Client Winamax actuel : %APPDATA%\winamax\documents\accounts\<pseudo>\history
    from fleur.watcher import find_history_dirs
    hist = tmp_path / "winamax" / "documents" / "accounts" / "pseudo" / "history"
    hist.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert hist in find_history_dirs()
