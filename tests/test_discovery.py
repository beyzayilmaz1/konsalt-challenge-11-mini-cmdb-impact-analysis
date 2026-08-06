"""Discovery yardımcıları — idempotency ve isimlendirme (psutil/API yok)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db
import discovery
import main


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    path = tmp_path / "disc_cmdb.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db(path)
    return TestClient(main.app)


def test_process_allowlist() -> None:
    assert discovery.is_interesting("chrome.exe")
    assert discovery.is_interesting("python")
    assert discovery.is_interesting("Cursor")
    assert not discovery.is_interesting("random_noise_xyz")


def test_namespaced_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery, "NODE_NAME", "LAPTOP-A")
    assert discovery.namespaced("process:chrome") == "LAPTOP-A::process:chrome"
    assert discovery.namespaced("LAPTOP-A") == "LAPTOP-A"
    assert discovery.namespaced("LAPTOP-A::process:chrome") == "LAPTOP-A::process:chrome"


def test_discovery_upsert_idempotent_via_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """İki kez aynı CI yazınca kayıt sayısı artmamalı (Challenge 7 dersi)."""

    def fake_api(method: str, path: str, data: dict | None = None):
        if method == "PUT":
            name = path.split("/ci/by-name/", 1)[1]
            # urllib quote geri çözülmüş gibi davran
            from urllib.parse import unquote

            name = unquote(name)
            r = client.put(f"/ci/by-name/{name}", json=data)
            return r.status_code, r.json()
        if method == "POST" and path == "/iliski":
            r = client.post("/iliski", json=data)
            return r.status_code, r.json() if r.content else None
        if method == "GET" and path == "/ci":
            r = client.get("/ci")
            return r.status_code, r.json()
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        raise AssertionError(f"beklenmeyen çağrı: {method} {path}")

    monkeypatch.setattr(discovery, "api", fake_api)
    monkeypatch.setattr(discovery, "NODE_NAME", "TEST-NODE")
    monkeypatch.setattr(discovery, "BASE_URL", "http://test")

    server = discovery.upsert_ci("TEST-NODE", "server", {"ram_gb": 8})
    proc = discovery.upsert_ci(
        discovery.namespaced("process:python"),
        "process",
        {"base_name": "python"},
    )
    discovery.ensure_iliski(proc["id"], server["id"], "calisir")

    before = len(client.get("/ci").json())
    before_rel = db.count_iliski()

    # İkinci koşu — aynı isimler
    discovery.upsert_ci("TEST-NODE", "server", {"ram_gb": 8})
    discovery.upsert_ci(
        discovery.namespaced("process:python"),
        "process",
        {"base_name": "python"},
    )
    discovery.ensure_iliski(proc["id"], server["id"], "calisir")

    after = len(client.get("/ci").json())
    after_rel = db.count_iliski()
    assert after == before == 2
    assert after_rel == before_rel == 1
