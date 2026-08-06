"""db.py birim testleri — şema, UNIQUE, FK, upsert, etki BFS."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import db


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    path = tmp_path / "test_cmdb.db"
    db.init_db(path)
    return path


def test_init_creates_tables(tmp_db: Path) -> None:
    with db.get_connection(tmp_db) as conn:
        names = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "ci" in names
    assert "iliski" in names


def test_insert_and_list_ci(tmp_db: Path) -> None:
    cid = db.insert_ci("SRV-1", "server", {"os": "Windows"}, tmp_db)
    assert cid > 0
    row = db.get_ci_by_id(cid, tmp_db)
    assert row is not None
    assert row["name"] == "SRV-1"
    assert row["ci_type"] == "server"
    assert row["ozellikler"]["os"] == "Windows"
    assert len(db.list_ci(db_path=tmp_db)) == 1
    assert len(db.list_ci("server", tmp_db)) == 1
    assert db.list_ci("port", tmp_db) == []


def test_duplicate_ci_name_raises(tmp_db: Path) -> None:
    db.insert_ci("APP-X", "application", db_path=tmp_db)
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_ci("APP-X", "application", db_path=tmp_db)


def test_upsert_ci_idempotent(tmp_db: Path) -> None:
    id1 = db.upsert_ci("process:chrome", "process", {"pid": 1}, tmp_db)
    id2 = db.upsert_ci("process:chrome", "process", {"pid": 2}, tmp_db)
    assert id1 == id2
    assert db.count_ci(tmp_db) == 1
    row = db.get_ci_by_id(id1, tmp_db)
    assert row is not None
    assert row["ozellikler"]["pid"] == 2


def test_duplicate_iliski_updates_kritiklik(tmp_db: Path) -> None:
    a = db.insert_ci("APP-A", "application", db_path=tmp_db)
    b = db.insert_ci("DB-B", "database", db_path=tmp_db)
    first = db.insert_iliski(a, b, "bagimli", kritiklik=2, db_path=tmp_db)
    assert first is not None
    second = db.insert_iliski(a, b, "bagimli", kritiklik=5, db_path=tmp_db)
    assert second is None  # aynı üçlü → güncelleme
    assert db.count_iliski(tmp_db) == 1
    rels = db.list_iliskiler_for_ci(a, tmp_db)
    assert len(rels) == 1
    assert rels[0]["kritiklik"] == 5


def test_foreign_key_rejects_missing_ci(tmp_db: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_iliski(999, 1000, "bagimli", db_path=tmp_db)


def test_join_readable_format(tmp_db: Path) -> None:
    srv = db.insert_ci("SRV-Y", "server", db_path=tmp_db)
    app = db.insert_ci("APP-X", "application", db_path=tmp_db)
    db.insert_iliski(app, srv, "calisir", db_path=tmp_db)
    lines = db.list_iliskiler_okunabilir(tmp_db)
    assert "APP-X --calisir--> SRV-Y" in lines


def test_etki_bfs_depth_and_cycle(tmp_db: Path) -> None:
    db_ci = db.insert_ci("ANKARA-DB01", "database", db_path=tmp_db)
    app1 = db.insert_ci("APP-ORDER", "application", db_path=tmp_db)
    app2 = db.insert_ci("APP-BILLING", "application", db_path=tmp_db)
    fe = db.insert_ci("FRONTEND-WEB", "application", db_path=tmp_db)
    db.insert_iliski(app1, db_ci, "bagimli", kritiklik=5, db_path=tmp_db)
    db.insert_iliski(app2, db_ci, "bagimli", kritiklik=2, db_path=tmp_db)
    db.insert_iliski(fe, app1, "bagimli", kritiklik=5, db_path=tmp_db)
    db.insert_iliski(fe, app2, "bagimli", kritiklik=2, db_path=tmp_db)

    etki = db.etki_analizi(db_ci, tmp_db)
    by_name = {e["name"]: e for e in etki}
    assert set(by_name) >= {"APP-ORDER", "APP-BILLING", "FRONTEND-WEB"}
    assert by_name["APP-ORDER"]["derinlik"] == 1
    assert by_name["FRONTEND-WEB"]["derinlik"] == 2
    assert by_name["APP-ORDER"]["kritik_yol"] is True
    assert etki[0]["name"] == "APP-ORDER"  # kritik yol öne

    a = db.insert_ci("CYCLE-A", "application", db_path=tmp_db)
    b = db.insert_ci("CYCLE-B", "application", db_path=tmp_db)
    db.insert_iliski(a, b, "bagimli", db_path=tmp_db)
    db.insert_iliski(b, a, "bagimli", db_path=tmp_db)
    cycle = db.etki_analizi(a, tmp_db)
    assert len(cycle) == 1
    assert cycle[0]["name"] == "CYCLE-B"


def test_kok_neden_forward_bfs(tmp_db: Path) -> None:
    db_ci = db.insert_ci("DB1", "database", db_path=tmp_db)
    app = db.insert_ci("APP1", "application", db_path=tmp_db)
    fe = db.insert_ci("FE1", "application", db_path=tmp_db)
    db.insert_iliski(app, db_ci, "bagimli", db_path=tmp_db)
    db.insert_iliski(fe, app, "bagimli", db_path=tmp_db)
    adaylar = db.kok_neden_analizi(fe, tmp_db)
    names = {a["name"]: a for a in adaylar}
    assert names["APP1"]["derinlik"] == 1
    assert names["DB1"]["derinlik"] == 2
