"""
Görev 4 kontrol noktası: zincirli senaryo + döngü testi.

Zincir: FRONTEND --bagimli--> APP1/APP2 --bagimli--> ANKARA-DB01
DB çökerse 3 CI etkilenmeli (APP1, APP2, FRONTEND), doğru derinliklerle.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8000"


def api(method: str, path: str, data: dict[str, Any] | None = None) -> tuple[int, Any]:
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw) if raw else None


def upsert(name: str, ci_type: str) -> dict[str, Any]:
    st, payload = api("PUT", f"/ci/by-name/{name}", {"ci_type": ci_type, "ozellikler": {}})
    assert st == 200, payload
    return payload


def link(kaynak: int, hedef: int, tip: str = "bagimli", kritiklik: int = 1) -> None:
    st, payload = api(
        "POST",
        "/iliski",
        {
            "kaynak_ci": kaynak,
            "hedef_ci": hedef,
            "iliski_tipi": tip,
            "kritiklik": kritiklik,
        },
    )
    assert st in (200, 201, 409), payload


def main() -> None:
    st, _ = api("GET", "/health")
    if st != 200:
        print("API ayakta degil")
        sys.exit(1)

    db_ci = upsert("ANKARA-DB01", "database")
    app1 = upsert("APP-ORDER", "application")
    app2 = upsert("APP-BILLING", "application")
    fe = upsert("FRONTEND-WEB", "application")

    # ORDER kritik (5), BILLING dusuk (2) — etki listesinde kritik yol one cikmali
    link(app1["id"], db_ci["id"], kritiklik=5)
    link(app2["id"], db_ci["id"], kritiklik=2)
    link(fe["id"], app1["id"], kritiklik=5)
    link(fe["id"], app2["id"], kritiklik=2)

    # Dongu tuzagi: A <-> B sonsuza girmemeli
    a = upsert("CYCLE-A", "application")
    b = upsert("CYCLE-B", "application")
    link(a["id"], b["id"], kritiklik=3)
    link(b["id"], a["id"], kritiklik=3)

    st, etki = api("GET", f"/ci/{db_ci['id']}/etki")
    assert st == 200, etki
    names = {e["name"]: e for e in etki["etkilenenler"]}
    print(
        "DB etki:",
        [
            (e["name"], e["derinlik"], e.get("yol_kritikligi"), e.get("kritik_yol"))
            for e in etki["etkilenenler"]
        ],
    )
    assert set(names) >= {"APP-ORDER", "APP-BILLING", "FRONTEND-WEB"}, names
    assert names["APP-ORDER"]["derinlik"] == 1
    assert names["APP-BILLING"]["derinlik"] == 1
    assert names["FRONTEND-WEB"]["derinlik"] == 2
    assert etki["etkilenen_sayisi"] >= 3

    # Bonus 1: kritik yollar one cikar (ORDER yol_kritikligi >= BILLING)
    assert names["APP-ORDER"]["yol_kritikligi"] == 5
    assert names["APP-ORDER"]["kritik_yol"] is True
    assert names["APP-BILLING"]["yol_kritikligi"] == 2
    assert names["APP-BILLING"]["kritik_yol"] is False
    assert etki["etkilenenler"][0]["name"] == "APP-ORDER"
    assert etki["kritik_etkilenen_sayisi"] >= 1

    st, cycle = api("GET", f"/ci/{a['id']}/etki")
    assert st == 200, cycle
    print("Dongu etki:", [(e["name"], e["derinlik"]) for e in cycle["etkilenenler"]])
    assert cycle["etkilenen_sayisi"] == 1
    assert cycle["etkilenenler"][0]["name"] == "CYCLE-B"

    # Bonus 3: FRONTEND yavassa altina bak — APP'ler + DB
    st, kok = api("GET", f"/ci/{fe['id']}/kok-neden")
    assert st == 200, kok
    kok_names = {a["name"]: a for a in kok["adaylar"]}
    print(
        "Kok-neden FRONTEND:",
        [(a["name"], a["derinlik"], a.get("yol_kritikligi")) for a in kok["adaylar"]],
    )
    assert set(kok_names) >= {"APP-ORDER", "APP-BILLING", "ANKARA-DB01"}, kok_names
    assert kok_names["APP-ORDER"]["derinlik"] == 1
    assert kok_names["APP-BILLING"]["derinlik"] == 1
    assert kok_names["ANKARA-DB01"]["derinlik"] == 2
    assert kok["aday_sayisi"] >= 3

    print("Gorev 4 + Bonus 1 + Bonus 3 kontrol noktasi: OK")


if __name__ == "__main__":
    main()
