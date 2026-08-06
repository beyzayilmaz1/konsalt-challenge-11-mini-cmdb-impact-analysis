"""
Görev 5 — CLI etki zinciri (önceki Mini-CMDB ASCII ağaç + kritiklik).

  python etki.py ANKARA-DB01
  python etki.py 50
  python etki.py --id 50
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_API = "http://127.0.0.1:8000"


def api_get(base: str, path: str) -> Any:
    try:
        with urllib.request.urlopen(base.rstrip("/") + path, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        print(f"HTTP {exc.code}: {body}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"API yok ({base}): {exc}")
        print("Önce: python -m uvicorn main:app --reload --port 8000")
        sys.exit(1)


def find_ci(base: str, ref: str) -> dict[str, Any]:
    if ref.isdigit():
        return api_get(base, f"/ci/{ref}")
    items = api_get(base, "/ci")
    for ci in items:
        if ci["name"].lower() == ref.lower():
            return ci
    matches = [c for c in items if ref.lower() in c["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        print(f"Birden fazla eşleşme ({len(matches)}):")
        for m in matches[:20]:
            print(f"  id={m['id']}  {m['name']} ({m['ci_type']})")
        sys.exit(1)
    print(f"CI bulunamadı: {ref}")
    sys.exit(1)


def gelen_bagimlilari(base: str, ci_id: int) -> list[dict[str, Any]]:
    """Bu CI hedef ise kaynak etkilenir (ters yön)."""
    rels = api_get(base, f"/ci/{ci_id}/iliskiler")
    out = []
    for r in rels:
        if r.get("yon") == "gelen":
            out.append(
                {
                    "id": r["kaynak_ci"],
                    "name": r["kaynak_name"],
                    "iliski_tipi": r["iliski_tipi"],
                    "kritiklik": r.get("kritiklik", 1),
                }
            )
    return out


def print_tree(
    base: str,
    node_id: int,
    node_name: str,
    node_type: str,
    prefix: str = "",
    is_last: bool = True,
    visited: set[int] | None = None,
    derinlik: int = 0,
    via: str | None = None,
    kritiklik: int | None = None,
) -> None:
    visited = visited if visited is not None else set()
    branch = "└── " if is_last else "├── "
    via_txt = f" via {via}" if via else ""
    krit_txt = f" k={kritiklik}" if kritiklik is not None and derinlik > 0 else ""
    if derinlik == 0:
        print(f"{node_name} ({node_type})")
    else:
        print(f"{prefix}{branch}{node_name} ({node_type}){via_txt}{krit_txt}  [d={derinlik}]")

    if node_id in visited:
        cont = "    " if is_last else "│   "
        print(f"{prefix}{cont}(döngü — atlandı)")
        return
    visited = visited | {node_id}

    kids = gelen_bagimlilari(base, node_id)
    child_prefix = "" if derinlik == 0 else prefix + ("    " if is_last else "│   ")
    for i, kid in enumerate(kids):
        last = i == len(kids) - 1
        detail = api_get(base, f"/ci/{kid['id']}")
        print_tree(
            base,
            kid["id"],
            kid["name"],
            detail["ci_type"],
            prefix=child_prefix,
            is_last=last,
            visited=visited,
            derinlik=derinlik + 1,
            via=kid["iliski_tipi"],
            kritiklik=kid.get("kritiklik"),
        )


def print_depth_list(etki: dict[str, Any]) -> None:
    print("--- Derinlik listesi (API BFS, kritiklik sıralı) ---")
    if not etki["etkilenenler"]:
        print("(etkilenen yok)")
        return
    for e in etki["etkilenenler"]:
        flag = " ★KRİTİK" if e.get("kritik_yol") else ""
        print(
            f"  d={e['derinlik']}: {e['name']} ({e['ci_type']}) "
            f"yol_krit={e.get('yol_kritikligi', 1)}{flag}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mini-CMDB etki zinciri (ASCII ağaç)")
    parser.add_argument("name", nargs="?", help="CI adı veya sayısal id")
    parser.add_argument("--id", type=int, help="CI id")
    parser.add_argument("--api-base", default=DEFAULT_API)
    args = parser.parse_args()

    if args.id is None and not args.name:
        parser.error("CI adı veya --id gerekli (ör. python etki.py ANKARA-DB01)")

    base = args.api_base
    if args.id is not None:
        ci = api_get(base, f"/ci/{args.id}")
    else:
        ci = find_ci(base, args.name)

    etki = api_get(base, f"/ci/{ci['id']}/etki")

    print(f"Etki analizi: {ci['name']} çökerse ne olur?")
    print(
        f"Etkilenen: {etki['etkilenen_sayisi']}  |  "
        f"Kritik yol: {etki.get('kritik_etkilenen_sayisi', 0)}"
    )
    print()
    print("--- ASCII ağaç (ters bağımlılık) ---")
    print_tree(base, ci["id"], ci["name"], ci["ci_type"])
    print()
    print_depth_list(etki)


if __name__ == "__main__":
    main()
