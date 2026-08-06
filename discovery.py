"""
Challenge 11 — Discovery.

psutil ile kendi makinenizi tarar; CI/ilişkileri API ÜZERİNDEN yazar (doğrudan DB yok).

  python discovery.py
  python discovery.py --api-base http://192.168.1.10:8000
  python discovery.py --node-name ARKADAS-LAPTOP
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import psutil

DEFAULT_API = "http://127.0.0.1:8000"

# Stabil isimler için PID kullanmıyoruz — her restart'ta yeni CI doğmasın.
PROCESS_ALLOWLIST = {
    "python",
    "pythonw",
    "chrome",
    "msedge",
    "firefox",
    "code",
    "cursor",
    "node",
    "docker",
    "postgres",
    "mysql",
    "mysqld",
    "redis",
    "redis-server",
    "nginx",
    "httpd",
    "apache",
    "sqlservr",
    "mongod",
    "powershell",
    "pwsh",
    "explorer",
    "teams",
    "slack",
    "discord",
    "spotify",
    "outlook",
    "idea64",
    "pycharm64",
    "devenv",
    "svchost",
}

BASE_URL = DEFAULT_API
NODE_NAME = socket.gethostname()


def api(method: str, path: str, data: dict[str, Any] | None = None) -> tuple[int, Any]:
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
        print(f"API'ye ulaşılamıyor ({BASE_URL}): {exc}")
        print("Önce API'yi başlatın: python -m uvicorn main:app --reload --port 8000")
        sys.exit(1)


def namespaced(local_name: str) -> str:
    """Multi-node: aynı process/port farklı makinelerde çakışmasın."""
    prefix = f"{NODE_NAME}::"
    if local_name == NODE_NAME or local_name.startswith(prefix):
        return local_name
    return f"{prefix}{local_name}"


def upsert_ci(name: str, ci_type: str, ozellikler: dict[str, Any] | None = None) -> dict[str, Any]:
    props = dict(ozellikler or {})
    props.setdefault("node", NODE_NAME)
    encoded = urllib.parse.quote(name, safe="")
    status, payload = api(
        "PUT",
        f"/ci/by-name/{encoded}",
        {"ci_type": ci_type, "ozellikler": props},
    )
    if status not in (200, 201):
        raise RuntimeError(f"CI upsert başarısız ({status}): {name} -> {payload}")
    return payload


def ensure_iliski(
    kaynak_id: int,
    hedef_id: int,
    iliski_tipi: str,
    kritiklik: int = 1,
) -> None:
    status, payload = api(
        "POST",
        "/iliski",
        {
            "kaynak_ci": kaynak_id,
            "hedef_ci": hedef_id,
            "iliski_tipi": iliski_tipi,
            "kritiklik": kritiklik,
        },
    )
    if status in (200, 201, 409):
        return
    raise RuntimeError(f"İlişki başarısız ({status}): {kaynak_id}->{hedef_id} {payload}")


def process_base_name(proc_name: str) -> str:
    name = (proc_name or "").strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def is_interesting(proc_name: str) -> bool:
    base = process_base_name(proc_name)
    if not base:
        return False
    if base in PROCESS_ALLOWLIST:
        return True
    return any(base.startswith(p) for p in ("code", "cursor", "chrome", "msedge", "com.docker"))


def discover_server() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    ozellikler = {
        "hostname": NODE_NAME,
        "os": platform.platform(),
        "system": platform.system(),
        "ram_gb": round(vm.total / (1024**3), 2),
        "cpu_count": psutil.cpu_count(logical=True),
        "discovery_source": BASE_URL,
    }
    return upsert_ci(NODE_NAME, "server", ozellikler)


def discover_processes(
    server_id: int,
) -> tuple[dict[str, dict[str, Any]], dict[int, str]]:
    found: dict[str, dict[str, Any]] = {}
    pid_to_ci_name: dict[int, str] = {}

    for proc in psutil.process_iter(["pid", "name", "exe", "username", "status"]):
        try:
            info = proc.info
            pname = info.get("name") or ""
            if not is_interesting(pname):
                continue
            base = process_base_name(pname)
            ci_name = namespaced(f"process:{base}")
            if ci_name not in found:
                found[ci_name] = upsert_ci(
                    ci_name,
                    "process",
                    {
                        "process_name": pname,
                        "base_name": base,
                        "sample_pid": info.get("pid"),
                        "exe": info.get("exe"),
                        "status": info.get("status"),
                    },
                )
                # DB / runtime süreçleri biraz daha kritik
                krit = 3 if base in {"postgres", "mysql", "mysqld", "sqlservr", "mongod", "redis", "redis-server"} else 1
                ensure_iliski(found[ci_name]["id"], server_id, "calisir", kritiklik=krit)
            pid_to_ci_name[int(info["pid"])] = ci_name
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    return found, pid_to_ci_name


def discover_ports(
    process_cis: dict[str, dict[str, Any]],
    pid_to_ci_name: dict[int, str],
) -> int:
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError) as exc:
        print(f"Port taraması atlandı (yönetici izni gerekebilir): {exc}")
        print("Not: Süreç + sunucu CI'ları yine yazıldı; MIMARI.md'de belgelendi.")
        return 0

    seen_ports: set[str] = set()
    for conn in conns:
        try:
            if conn.status != psutil.CONN_LISTEN:
                continue
            if not conn.laddr:
                continue
            port = int(conn.laddr.port)
            family = "tcp" if conn.type == socket.SOCK_STREAM else "udp"
            ci_name = namespaced(f"port:{family}:{port}")
            port_ci = upsert_ci(
                ci_name,
                "port",
                {
                    "protocol": family,
                    "port": port,
                    "address": str(getattr(conn.laddr, "ip", "")),
                },
            )
            seen_ports.add(ci_name)

            if conn.pid and conn.pid in pid_to_ci_name:
                proc_ci = process_cis[pid_to_ci_name[conn.pid]]
                ensure_iliski(proc_ci["id"], port_ci["id"], "baglanir", kritiklik=2)
        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            continue

    return len(seen_ports)


def count_ci() -> int:
    status, items = api("GET", "/ci")
    if status != 200 or not isinstance(items, list):
        raise RuntimeError(f"CI listesi alınamadı: {status} {items}")
    return len(items)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mini-CMDB discovery (yerel / uzak API)")
    p.add_argument(
        "--api-base",
        default=os.getenv("CMDB_API_BASE", DEFAULT_API),
        help="CMDB API kök URL",
    )
    p.add_argument(
        "--node-name",
        default=None,
        help="CI isim öneki / server adı (varsayılan: hostname)",
    )
    return p.parse_args()


def main() -> None:
    global BASE_URL, NODE_NAME

    args = parse_args()
    BASE_URL = args.api_base.rstrip("/")
    NODE_NAME = args.node_name or socket.gethostname()

    print(f"Discovery node={NODE_NAME} -> {BASE_URL}")
    status, _ = api("GET", "/health")
    if status != 200:
        print("API health başarısız")
        sys.exit(1)

    before = count_ci()
    server = discover_server()
    print(f"  server:  {server['name']} (id={server['id']})")

    process_cis, pid_map = discover_processes(server["id"])
    print(f"  process: {len(process_cis)} CI")

    port_count = discover_ports(process_cis, pid_map)
    print(f"  port:    {port_count} CI")

    after = count_ci()
    print(f"Toplam CI: {after} (önce: {before}, bu koşuda net +{after - before})")
    if after < 15:
        print(
            "Uyarı: 15 CI altındasınız. Allowlist'e süreç ekleyin "
            "veya yönetici olarak port keşfini açın."
        )
    else:
        print("Kontrol noktası (15+ CI): OK")
    print("İkinci koşu kayıt sayısını artırmamalı (idempotent upsert).")


if __name__ == "__main__":
    main()
