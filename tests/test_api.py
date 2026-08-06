"""FastAPI uç noktaları — TestClient ile (sunucu gerekmez)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db
import main


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    path = tmp_path / "api_cmdb.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db(path)
    return TestClient(main.app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_list_get_ci(client: TestClient) -> None:
    r = client.post(
        "/ci",
        json={"name": "SRV-Y", "ci_type": "server", "ozellikler": {"ram_gb": 16}},
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    r2 = client.post(
        "/ci",
        json={"name": "SRV-Y", "ci_type": "server", "ozellikler": {}},
    )
    assert r2.status_code == 409

    listed = client.get("/ci", params={"ci_type": "server"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = client.get(f"/ci/{cid}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "SRV-Y"

    missing = client.get("/ci/99999")
    assert missing.status_code == 404


def test_iliski_404_and_both_directions(client: TestClient) -> None:
    app = client.post(
        "/ci", json={"name": "APP-X", "ci_type": "application", "ozellikler": {}}
    ).json()
    srv = client.post("/ci", json={"name": "SRV-Y", "ci_type": "server", "ozellikler": {}}).json()

    bad = client.post(
        "/iliski",
        json={"kaynak_ci": app["id"], "hedef_ci": 99999, "iliski_tipi": "calisir"},
    )
    assert bad.status_code == 404

    ok = client.post(
        "/iliski",
        json={
            "kaynak_ci": app["id"],
            "hedef_ci": srv["id"],
            "iliski_tipi": "calisir",
            "kritiklik": 3,
        },
    )
    assert ok.status_code == 201

    rels = client.get(f"/ci/{app['id']}/iliskiler").json()
    assert len(rels) == 1
    assert rels[0]["yon"] == "giden"

    rels_srv = client.get(f"/ci/{srv['id']}/iliskiler").json()
    assert len(rels_srv) == 1
    assert rels_srv[0]["yon"] == "gelen"


def test_upsert_idempotent_via_api(client: TestClient) -> None:
    r1 = client.put(
        "/ci/by-name/process:python",
        json={"ci_type": "process", "ozellikler": {"sample_pid": 1}},
    )
    r2 = client.put(
        "/ci/by-name/process:python",
        json={"ci_type": "process", "ozellikler": {"sample_pid": 2}},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert len(client.get("/ci").json()) == 1


def test_etki_endpoint(client: TestClient) -> None:
    db_ci = client.put(
        "/ci/by-name/ANKARA-DB01",
        json={"ci_type": "database", "ozellikler": {}},
    ).json()
    app = client.put(
        "/ci/by-name/APP-ORDER",
        json={"ci_type": "application", "ozellikler": {}},
    ).json()
    fe = client.put(
        "/ci/by-name/FRONTEND-WEB",
        json={"ci_type": "application", "ozellikler": {}},
    ).json()
    client.post(
        "/iliski",
        json={
            "kaynak_ci": app["id"],
            "hedef_ci": db_ci["id"],
            "iliski_tipi": "bagimli",
            "kritiklik": 5,
        },
    )
    client.post(
        "/iliski",
        json={
            "kaynak_ci": fe["id"],
            "hedef_ci": app["id"],
            "iliski_tipi": "bagimli",
            "kritiklik": 5,
        },
    )
    etki = client.get(f"/ci/{db_ci['id']}/etki").json()
    names = {e["name"] for e in etki["etkilenenler"]}
    assert names == {"APP-ORDER", "FRONTEND-WEB"}
    assert etki["etkilenen_sayisi"] == 2
