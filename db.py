"""
Mini-CMDB veritabanı katmanı — SQLite, ham SQL (ORM yok).
Challenge 11 Görev 1.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent / "cmdb.db"

CI_TYPES = ("server", "application", "database", "process", "port")
ILISKI_TIPLERI = ("calisir", "bagimli", "baglanir")


@contextmanager
def get_connection(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Bağlantı aç/kapat; foreign key'ler her bağlantıda açık (SQLite varsayılanı OFF)."""
    path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """ci ve iliski tablolarını oluştur."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ci (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                ci_type    TEXT    NOT NULL CHECK (ci_type IN (
                    'server', 'application', 'database', 'process', 'port'
                )),
                ozellikler TEXT    NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS iliski (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                kaynak_ci   INTEGER NOT NULL,
                hedef_ci    INTEGER NOT NULL,
                iliski_tipi TEXT    NOT NULL CHECK (iliski_tipi IN (
                    'calisir', 'bagimli', 'baglanir'
                )),
                kritiklik   INTEGER NOT NULL DEFAULT 1
                            CHECK (kritiklik BETWEEN 1 AND 5),
                FOREIGN KEY (kaynak_ci) REFERENCES ci(id) ON DELETE CASCADE,
                FOREIGN KEY (hedef_ci)  REFERENCES ci(id) ON DELETE CASCADE,
                UNIQUE (kaynak_ci, hedef_ci, iliski_tipi)
            );
            """
        )


def _row_to_ci(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "ci_type": row["ci_type"],
        "ozellikler": json.loads(row["ozellikler"]),
    }


def insert_ci(
    name: str,
    ci_type: str,
    ozellikler: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Yeni CI ekle. İsim çakışırsa IntegrityError."""
    if ci_type not in CI_TYPES:
        raise ValueError(f"Geçersiz ci_type: {ci_type}. İzinliler: {CI_TYPES}")
    props = json.dumps(ozellikler or {}, ensure_ascii=False)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO ci (name, ci_type, ozellikler) VALUES (?, ?, ?)",
            (name, ci_type, props),
        )
        return int(cur.lastrowid)


def upsert_ci(
    name: str,
    ci_type: str,
    ozellikler: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> int:
    """İsimle bul; yoksa ekle, varsa güncelle. Discovery idempotency için."""
    if ci_type not in CI_TYPES:
        raise ValueError(f"Geçersiz ci_type: {ci_type}. İzinliler: {CI_TYPES}")
    props = json.dumps(ozellikler or {}, ensure_ascii=False)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT id FROM ci WHERE name = ?", (name,)).fetchone()
        if row:
            conn.execute(
                "UPDATE ci SET ci_type = ?, ozellikler = ? WHERE id = ?",
                (ci_type, props, row["id"]),
            )
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO ci (name, ci_type, ozellikler) VALUES (?, ?, ?)",
            (name, ci_type, props),
        )
        return int(cur.lastrowid)


def insert_iliski(
    kaynak_ci: int,
    hedef_ci: int,
    iliski_tipi: str,
    kritiklik: int = 1,
    db_path: Path | str | None = None,
) -> int | None:
    """
    İlişki ekle. Aynı üçlü varsa kritiklik güncellenir ve None döner (idempotent).
    """
    if iliski_tipi not in ILISKI_TIPLERI:
        raise ValueError(f"Geçersiz iliski_tipi: {iliski_tipi}. İzinliler: {ILISKI_TIPLERI}")
    if not 1 <= int(kritiklik) <= 5:
        raise ValueError("kritiklik 1..5 aralığında olmalı")
    with get_connection(db_path) as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO iliski (kaynak_ci, hedef_ci, iliski_tipi, kritiklik)
                VALUES (?, ?, ?, ?)
                """,
                (kaynak_ci, hedef_ci, iliski_tipi, int(kritiklik)),
            )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            mevcut = conn.execute(
                """
                SELECT id FROM iliski
                WHERE kaynak_ci = ? AND hedef_ci = ? AND iliski_tipi = ?
                """,
                (kaynak_ci, hedef_ci, iliski_tipi),
            ).fetchone()
            if mevcut:
                conn.execute(
                    "UPDATE iliski SET kritiklik = ? WHERE id = ?",
                    (int(kritiklik), mevcut["id"]),
                )
                return None
            raise


def get_ci_by_id(ci_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM ci WHERE id = ?", (ci_id,)).fetchone()
    return _row_to_ci(row) if row else None


def get_ci_by_name(name: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM ci WHERE name = ?", (name,)).fetchone()
    return _row_to_ci(row) if row else None


def list_ci(
    ci_type: str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        if ci_type:
            rows = conn.execute(
                "SELECT * FROM ci WHERE ci_type = ? ORDER BY id", (ci_type,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ci ORDER BY id").fetchall()
    return [_row_to_ci(r) for r in rows]


def list_iliskiler_okunabilir(db_path: Path | str | None = None) -> list[str]:
    """Kontrol noktası formatı: APP-X --calisir--> SRV-Y"""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT k.name AS kaynak, i.iliski_tipi, h.name AS hedef
            FROM iliski i
            JOIN ci k ON k.id = i.kaynak_ci
            JOIN ci h ON h.id = i.hedef_ci
            ORDER BY i.id
            """
        ).fetchall()
    return [f"{r['kaynak']} --{r['iliski_tipi']}--> {r['hedef']}" for r in rows]


def list_iliskiler_for_ci(
    ci_id: int,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Bir CI'ın her iki yöndeki ilişkileri."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                i.id,
                i.iliski_tipi,
                i.kritiklik,
                i.kaynak_ci,
                i.hedef_ci,
                k.name AS kaynak_name,
                h.name AS hedef_name,
                CASE
                    WHEN i.kaynak_ci = ? THEN 'giden'
                    ELSE 'gelen'
                END AS yon
            FROM iliski i
            JOIN ci k ON k.id = i.kaynak_ci
            JOIN ci h ON h.id = i.hedef_ci
            WHERE i.kaynak_ci = ? OR i.hedef_ci = ?
            ORDER BY i.kritiklik DESC, i.id
            """,
            (ci_id, ci_id, ci_id),
        ).fetchall()
    return [dict(r) for r in rows]


def list_etki_komsulari(
    ci_id: int,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """
    Etki analizi için TERS yön komşuları.
    APP --bagimli--> DB ise DB çökünce APP etkilenir (WHERE hedef_ci = ?).
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                k.id, k.name, k.ci_type, k.ozellikler,
                i.iliski_tipi, i.kritiklik
            FROM iliski i
            JOIN ci k ON k.id = i.kaynak_ci
            WHERE i.hedef_ci = ?
            ORDER BY i.kritiklik DESC
            """,
            (ci_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "ci_type": r["ci_type"],
            "ozellikler": json.loads(r["ozellikler"]),
            "iliski_tipi": r["iliski_tipi"],
            "kritiklik": int(r["kritiklik"]),
        }
        for r in rows
    ]


def list_bagimlilik_komsulari(
    ci_id: int,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Kök neden için İLERİ yön: bu CI'nın bağımlı olduğu hedefler."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                h.id, h.name, h.ci_type, h.ozellikler,
                i.iliski_tipi, i.kritiklik
            FROM iliski i
            JOIN ci h ON h.id = i.hedef_ci
            WHERE i.kaynak_ci = ?
            ORDER BY i.kritiklik DESC
            """,
            (ci_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "ci_type": r["ci_type"],
            "ozellikler": json.loads(r["ozellikler"]),
            "iliski_tipi": r["iliski_tipi"],
            "kritiklik": int(r["kritiklik"]),
        }
        for r in rows
    ]


def etki_analizi(
    baslangic_id: int,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """
    BFS ile etki zinciri (ters yön). Başlangıç CI dahil edilmez.
    yol_kritikligi = yoldaki max kenar kritikliği; kritik_yol = yol_kritikligi >= 4.
    """
    kuyruk: deque[tuple[int, int, int]] = deque([(baslangic_id, 0, 0)])
    ziyaret: set[int] = set()
    sonuclar: list[dict[str, Any]] = []

    while kuyruk:
        mevcut_id, derinlik, yol_krit = kuyruk.popleft()
        if mevcut_id in ziyaret:
            continue
        ziyaret.add(mevcut_id)

        if derinlik > 0:
            ci = get_ci_by_id(mevcut_id, db_path)
            if ci is None:
                continue
            sonuclar.append(
                {
                    **ci,
                    "derinlik": derinlik,
                    "yol_kritikligi": yol_krit,
                    "kritik_yol": yol_krit >= 4,
                }
            )

        for komsu in list_etki_komsulari(mevcut_id, db_path):
            if komsu["id"] not in ziyaret:
                yeni_yol = max(yol_krit, int(komsu["kritiklik"]))
                kuyruk.append((komsu["id"], derinlik + 1, yeni_yol))

    sonuclar.sort(key=lambda x: (-x["yol_kritikligi"], x["derinlik"], x["id"]))
    return sonuclar


def kok_neden_analizi(
    baslangic_id: int,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Etki analizinin tersi: ileri yön BFS — sorun varsa nereye bakmalı?"""
    kuyruk: deque[tuple[int, int, int]] = deque([(baslangic_id, 0, 0)])
    ziyaret: set[int] = set()
    sonuclar: list[dict[str, Any]] = []

    while kuyruk:
        mevcut_id, derinlik, yol_krit = kuyruk.popleft()
        if mevcut_id in ziyaret:
            continue
        ziyaret.add(mevcut_id)

        if derinlik > 0:
            ci = get_ci_by_id(mevcut_id, db_path)
            if ci is None:
                continue
            sonuclar.append(
                {
                    **ci,
                    "derinlik": derinlik,
                    "yol_kritikligi": yol_krit,
                    "kritik_yol": yol_krit >= 4,
                }
            )

        for komsu in list_bagimlilik_komsulari(mevcut_id, db_path):
            if komsu["id"] not in ziyaret:
                yeni_yol = max(yol_krit, int(komsu["kritiklik"]))
                kuyruk.append((komsu["id"], derinlik + 1, yeni_yol))

    sonuclar.sort(key=lambda x: (-x["yol_kritikligi"], x["derinlik"], x["id"]))
    return sonuclar


def count_ci(db_path: Path | str | None = None) -> int:
    with get_connection(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM ci").fetchone()[0])


def count_iliski(db_path: Path | str | None = None) -> int:
    with get_connection(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM iliski").fetchone()[0])


if __name__ == "__main__":
    # Görev 1 kontrol noktası: 3 CI + 2 ilişki, JOIN ile okuma
    demo_db = Path(__file__).resolve().parent / "cmdb_demo.db"
    if demo_db.exists():
        demo_db.unlink()

    init_db(demo_db)
    srv = insert_ci("SRV-Y", "server", {"os": "Windows"}, demo_db)
    app = insert_ci("APP-X", "application", {"lang": "python"}, demo_db)
    db_ = insert_ci("DB-Z", "database", {"engine": "sqlite"}, demo_db)
    insert_iliski(app, srv, "calisir", db_path=demo_db)
    insert_iliski(app, db_, "bagimli", kritiklik=5, db_path=demo_db)

    print("CI sayısı:", count_ci(demo_db))
    print("İlişki sayısı:", count_iliski(demo_db))
    print("İlişkiler:")
    for line in list_iliskiler_okunabilir(demo_db):
        print(" ", line)
