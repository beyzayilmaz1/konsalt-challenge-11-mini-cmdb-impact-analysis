"""
Görev 4 test + sunum senaryosu — API üzerinden (direkt DB yok).

Screenshot / sunum ile aynı değerler:
  ANKARA-DB01 çökerse → 3 etkilenen, 2 kritik yol

Zincir:
  FRONTEND-WEB --bagimli(k=5)--> APP-ORDER --bagimli(k=5)--> ANKARA-DB01
  FRONTEND-WEB --bagimli(k=2)--> APP-BILLING --bagimli(k=2)--> ANKARA-DB01

  python seed_senaryo.py
  python etki.py ANKARA-DB01
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8000"


def api(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        BASE.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload
    except urllib.error.URLError as exc:
        print(f"API kapalı ({BASE}): {exc}")
        print("Önce: python -m uvicorn main:app --port 8000")
        sys.exit(1)


def upsert(name: str, ci_type: str, ozellikler: dict[str, Any] | None = None) -> dict[str, Any]:
    status, payload = api(
        "PUT",
        f"/ci/by-name/{urllib.parse.quote(name, safe='')}",
        {"ci_type": ci_type, "ozellikler": ozellikler or {}},
    )
    if status not in (200, 201):
        raise RuntimeError(f"upsert {name}: {status} {payload}")
    return payload


def iliski(kaynak_id: int, hedef_id: int, tip: str, kritiklik: int = 1) -> None:
    status, payload = api(
        "POST",
        "/iliski",
        {
            "kaynak_ci": kaynak_id,
            "hedef_ci": hedef_id,
            "iliski_tipi": tip,
            "kritiklik": kritiklik,
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"iliski: {status} {payload}")


def main() -> None:
    status, _ = api("GET", "/health")
    if status != 200:
        print("health başarısız")
        sys.exit(1)

    # Screenshot ile aynı isimler
    db = upsert("ANKARA-DB01", "database", {})
    app1 = upsert("APP-ORDER", "application", {})
    app2 = upsert("APP-BILLING", "application", {})
    fe = upsert("FRONTEND-WEB", "application", {})

    # ORDER kritik (5), BILLING düşük (2) → kritik yol sayısı 2 olur
    iliski(app1["id"], db["id"], "bagimli", kritiklik=5)
    iliski(app2["id"], db["id"], "bagimli", kritiklik=2)
    iliski(fe["id"], app1["id"], "bagimli", kritiklik=5)
    iliski(fe["id"], app2["id"], "bagimli", kritiklik=2)

    print("Senaryo hazır (screenshot ile aynı):")
    print("  FRONTEND-WEB --bagimli(k=5)--> APP-ORDER --bagimli(k=5)--> ANKARA-DB01")
    print("  FRONTEND-WEB --bagimli(k=2)--> APP-BILLING --bagimli(k=2)--> ANKARA-DB01")
    print()
    print(f"ANKARA-DB01 id={db['id']}")

    _, etki = api("GET", f"/ci/{db['id']}/etki")
    print(
        f"\nEtki: etkilenen={etki['etkilenen_sayisi']}  "
        f"kritik_yol={etki['kritik_etkilenen_sayisi']}"
    )
    for e in etki["etkilenenler"]:
        flag = " ★" if e.get("kritik_yol") else ""
        print(
            f"  d={e['derinlik']}  {e['name']}  "
            f"yol_krit={e.get('yol_kritikligi')}{flag}"
        )

    if etki["etkilenen_sayisi"] != 3 or etki["kritik_etkilenen_sayisi"] != 2:
        print("HATA: Beklenen 3 etkilenen / 2 kritik yol")
        sys.exit(1)
    print("\nKontrol noktası: 3 etkilenen, 2 kritik yol — OK")


if __name__ == "__main__":
    main()
