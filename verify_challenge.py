"""
Challenge 11 — tüm görev + bonus kontrol noktaları.

  python -m uvicorn main:app --port 8000
  python verify_challenge.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import requests

import db

BASE = "http://127.0.0.1:8000"
H = {"Content-Type": "application/json"}


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")
    sys.exit(1)


def upsert(name: str, tip: str, oz: dict | None = None) -> dict:
    r = requests.put(
        f"{BASE}/ci/by-name/{name}",
        json={"ci_type": tip, "ozellikler": oz or {}},
        headers=H,
        timeout=10,
    )
    if r.status_code not in (200, 201):
        fail(f"upsert {name}: {r.status_code} {r.text}")
    return r.json()


def post_iliski(kaynak: int, hedef: int, tip: str, kritiklik: int = 1) -> None:
    r = requests.post(
        f"{BASE}/iliski",
        json={
            "kaynak_ci": kaynak,
            "hedef_ci": hedef,
            "iliski_tipi": tip,
            "kritiklik": kritiklik,
        },
        headers=H,
        timeout=10,
    )
    if r.status_code not in (200, 201):
        fail(f"iliski: {r.status_code} {r.text}")


def test_db_layer() -> None:
    print("\n[Görev 1] Veritabanı katmanı")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "t.db"
        db.init_db(path)
        srv = db.insert_ci("SRV-Y", "server", {"os": "win"}, path)
        app = db.insert_ci("APP-X", "application", {}, path)
        db_ = db.insert_ci("DB-Z", "database", {}, path)
        db.insert_iliski(app, srv, "calisir", db_path=path)
        db.insert_iliski(app, db_, "bagimli", kritiklik=5, db_path=path)
        lines = db.list_iliskiler_okunabilir(path)
        if not any("APP-X --calisir--> SRV-Y" in L for L in lines):
            fail(f"JOIN formatı yok: {lines}")
        # UNIQUE: ikinci ekleme IntegrityError / None
        again = db.insert_iliski(app, srv, "calisir", db_path=path)
        if again is not None:
            fail("UNIQUE ihlali: aynı ilişki tekrar eklendi")
        ok("3 CI + 2 ilişki; JOIN 'APP-X --calisir--> SRV-Y'; UNIQUE çalışıyor")


def test_api_and_etki() -> None:
    print("\n[Görev 2] API katmanı")
    r = requests.get(f"{BASE}/health", timeout=5)
    if r.status_code != 200:
        fail("API ayakta değil — uvicorn main:app --port 8000")

    # Tip filtresi
    upsert("_t_server", "server")
    filtered = requests.get(f"{BASE}/ci", params={"ci_type": "server"}, timeout=5).json()
    if not any(c["name"] == "_t_server" for c in filtered):
        fail("ci_type filtresi çalışmıyor")
    ok("POST/PUT /ci, GET /ci?ci_type=, GET /ci/{id}")

    print("\n[Görev 4] Etki analizi (1 DB ← 2 APP ← 1 FE)")
    prefix = "_verify_"
    db_ci = upsert(f"{prefix}DB", "database")
    app1 = upsert(f"{prefix}APP1", "application")
    app2 = upsert(f"{prefix}APP2", "application")
    fe = upsert(f"{prefix}FE", "application")

    post_iliski(app1["id"], db_ci["id"], "bagimli", 5)
    post_iliski(app2["id"], db_ci["id"], "bagimli", 4)
    post_iliski(fe["id"], app1["id"], "bagimli", 3)

    rels = requests.get(f"{BASE}/ci/{db_ci['id']}/iliskiler", timeout=5).json()
    if len(rels) < 2:
        fail("GET /ci/{id}/iliskiler yetersiz")
    ok("POST /iliski + GET /ci/{id}/iliskiler (her iki yön)")

    etki = requests.get(f"{BASE}/ci/{db_ci['id']}/etki", timeout=5).json()
    names = {e["name"]: e for e in etki["etkilenenler"]}
    expected = {f"{prefix}APP1", f"{prefix}APP2", f"{prefix}FE"}
    if not expected.issubset(set(names)):
        fail(f"Beklenen {expected}, gelen {set(names)}")
    if names[f"{prefix}APP1"]["derinlik"] != 1 or names[f"{prefix}APP2"]["derinlik"] != 1:
        fail(f"APP derinlikleri yanlış: {names}")
    if names[f"{prefix}FE"]["derinlik"] != 2:
        fail(f"FE derinlik 2 olmalı: {names}")
    ok("Zincir: 3 CI, derinlikler doğru")

    # Kritik yollar öne çıksın (yol_kritikligi sıralaması)
    ordered = etki["etkilenenler"]
    if ordered[0]["yol_kritikligi"] < ordered[-1]["yol_kritikligi"]:
        fail("Kritik yollar öne sıralanmamış")
    if not names[f"{prefix}APP1"]["kritik_yol"]:
        fail("APP1 kritik_yol=True olmalı (k=5)")
    ok(f"Bonus kritiklik: kritik_etkilenen={etki['kritik_etkilenen_sayisi']}")

    # Döngü
    post_iliski(db_ci["id"], fe["id"], "bagimli", 1)
    etki2 = requests.get(f"{BASE}/ci/{db_ci['id']}/etki", timeout=5).json()
    ok(f"Döngü sonsuza girmedi ({etki2['etkilenen_sayisi']} etkilenen)")

    print("\n[Bonus] GET /ci/{{id}}/kok-neden")
    kok = requests.get(f"{BASE}/ci/{fe['id']}/kok-neden", timeout=5).json()
    adaylar = {a["name"] for a in kok["adaylar"]}
    if f"{prefix}APP1" not in adaylar or f"{prefix}DB" not in adaylar:
        fail(f"kok-neden adayları eksik: {adaylar}")
    depths = {a["name"]: a["derinlik"] for a in kok["adaylar"]}
    if depths.get(f"{prefix}APP1") != 1 or depths.get(f"{prefix}DB") != 2:
        fail(f"kok-neden derinlikleri yanlış: {depths}")
    ok("FE → APP1 (d=1) → DB (d=2)")


def test_discovery_and_multinode() -> None:
    print("\n[Görev 3] Discovery durumu")
    items = requests.get(f"{BASE}/ci", timeout=5).json()
    n = len(items)
    print(f"  Mevcut CI: {n}")
    if n < 15:
        fail("15+ CI yok — önce: python discovery.py")
    ok("15+ CI mevcut")

    print("\n[Bonus] Multi-node isimlendirme simülasyonu")
    # Aynı API'ye ikinci düğüm gibi yaz (arkadaş laptopu senaryosu)
    node = "ARKADAS-LAPTOP"
    srv = upsert(node, "server", {"hostname": node, "node": node})
    proc = upsert(
        f"{node}::process:chrome",
        "process",
        {"base_name": "chrome", "node": node},
    )
    post_iliski(proc["id"], srv["id"], "calisir", 1)
    got = requests.get(f"{BASE}/ci/{proc['id']}", timeout=5).json()
    if not got["name"].startswith(f"{node}::"):
        fail("multi-node namespace yok")
    # İkinci upsert duplicate üretmesin
    before = len(requests.get(f"{BASE}/ci", timeout=5).json())
    upsert(f"{node}::process:chrome", "process", {"base_name": "chrome", "node": node})
    after = len(requests.get(f"{BASE}/ci", timeout=5).json())
    if after != before:
        fail("multi-node upsert duplicate üretti")
    ok(f"Multi-node CI: {got['name']} (idempotent)")


def main() -> None:
    print("Challenge 11 — tam doğrulama (görevler + bonuslar)")
    test_db_layer()
    test_api_and_etki()
    test_discovery_and_multinode()
    print("\nTÜM GÖREV VE BONUS TESTLERİ GEÇTİ")


if __name__ == "__main__":
    main()
