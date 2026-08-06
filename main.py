"""
KONSALT Challenge 11 — Mini-CMDB API
Challenge 6 iskeleti: FastAPI + Pydantic + tutarlı hatalar.
Kalıcılık: JSON yerine SQLite (db.py).
"""

from __future__ import annotations

import logging
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

API_DESCRIPTION = """
Kurumsal CMDB'nin minyatürü: **Configuration Item** envanteri, yönlü ilişkiler ve BFS etki analizi.

| Katman | Rol |
|--------|-----|
| Discovery | `psutil` ile host tarar, yalnızca HTTP API'ye yazar |
| API | CI / ilişki CRUD, upsert, analiz uçları |
| Analiz | Ters BFS etki · ileri BFS kök neden · kritiklik |

**İlişki tipleri:** `calisir` · `bagimli` · `baglanir`
**CI tipleri:** `server` · `application` · `database` · `process` · `port`

Hata gövdesi: `{"error": "..."}` (Challenge 6 sözleşmesi).
"""

app = FastAPI(
    title="Konsalt Mini-CMDB API",
    description=API_DESCRIPTION,
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_tags=[
        {"name": "Sistem", "description": "Sağlık ve operasyon kontrolleri"},
        {"name": "CI", "description": "Configuration Item oluşturma, listeleme, upsert"},
        {"name": "İlişki", "description": "Yönlü kenarlar (kaynak → hedef)"},
        {"name": "Analiz", "description": "Etki analizi ve kök neden (BFS)"},
    ],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Modeller -----------------------------------------------------------------


class CIType(str, Enum):
    server = "server"
    application = "application"
    database = "database"
    process = "process"
    port = "port"


class IliskiTipi(str, Enum):
    calisir = "calisir"
    bagimli = "bagimli"
    baglanir = "baglanir"


class CICreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    ci_type: CIType
    ozellikler: dict[str, Any] = Field(default_factory=dict)


class CIUpsert(BaseModel):
    """Discovery için: isim yolda, tip + özellikler gövdede."""

    ci_type: CIType
    ozellikler: dict[str, Any] = Field(default_factory=dict)


class CIResponse(BaseModel):
    id: int
    name: str
    ci_type: CIType
    ozellikler: dict[str, Any]


class IliskiCreate(BaseModel):
    kaynak_ci: int = Field(gt=0, description="Kaynak CI id")
    hedef_ci: int = Field(gt=0, description="Hedef CI id")
    iliski_tipi: IliskiTipi
    kritiklik: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Kenar kritikliği 1 (düşük) .. 5 (kritik)",
    )


class IliskiResponse(BaseModel):
    id: int
    kaynak_ci: int
    hedef_ci: int
    iliski_tipi: IliskiTipi
    kritiklik: int = 1
    kaynak_name: Optional[str] = None
    hedef_name: Optional[str] = None
    yon: Optional[str] = None


class HealthResponse(BaseModel):
    status: str


class EtkiItem(BaseModel):
    id: int
    name: str
    ci_type: CIType
    ozellikler: dict[str, Any]
    derinlik: int = Field(description="Başlangıç CI'dan kaç adım uzakta")
    yol_kritikligi: int = Field(
        default=1,
        description="Bu düğüme giden yoldaki en yüksek kenar kritikliği (1-5)",
    )
    kritik_yol: bool = Field(default=False, description="yol_kritikligi >= 4 ise True")


class EtkiResponse(BaseModel):
    baslangic: CIResponse
    etkilenen_sayisi: int
    kritik_etkilenen_sayisi: int
    etkilenenler: list[EtkiItem]


class KokNedenResponse(BaseModel):
    baslangic: CIResponse
    aday_sayisi: int
    kritik_aday_sayisi: int
    adaylar: list[EtkiItem]


# --- Hata formatı (Challenge 6 sözleşmesi) ------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        body = detail
    else:
        body = {"error": detail if isinstance(detail, str) else str(detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "Doğrulama başarısız", "details": exc.errors()},
    )


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    logger.info("CMDB hazır: %d CI, %d ilişki", db.count_ci(), db.count_iliski())


# --- Portal & docs (önceki Mini-CMDB UI) --------------------------------------


@app.get("/", include_in_schema=False)
def portal() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Portal bulunamadı")
    return FileResponse(index)


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    ui = get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title="Mini-CMDB API · Docs",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger.css",
        swagger_ui_parameters={
            "docExpansion": "list",
            "defaultModelsExpandDepth": -1,
            "filter": True,
            "tryItOutEnabled": True,
            "displayRequestDuration": True,
            "syntaxHighlight": {"activate": True, "theme": "obsidian"},
        },
    )
    body = (
        bytes(ui.body).decode("utf-8")
        if isinstance(ui.body, (bytes, bytearray, memoryview))
        else str(ui.body)
    )
    chrome = """
    <div class="cmdb-docs-chrome">
      <div class="cmdb-docs-brand">
        <strong>Mini-CMDB API</strong>
        <span>OpenAPI 3 · Etki analizi &amp; discovery</span>
      </div>
      <div style="display:flex;gap:18px;align-items:center;">
        <a href="/">Portal</a>
        <a href="/redoc">ReDoc</a>
        <a href="/health">Health</a>
      </div>
    </div>
    """
    body = body.replace("<body>", "<body>" + chrome, 1)
    return HTMLResponse(content=body)


@app.get("/redoc", include_in_schema=False)
def redoc_ui() -> HTMLResponse:
    return get_redoc_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title="Mini-CMDB API · ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    )


# --- Endpoint'ler -------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Sağlık kontrolü",
    description="Servisin ayakta olup olmadığını döner.",
    tags=["Sistem"],
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/ci",
    status_code=201,
    response_model=CIResponse,
    summary="CI ekle",
    description="Yeni Configuration Item oluşturur. Aynı isim varsa 409.",
    tags=["CI"],
)
def create_ci(body: CICreate) -> CIResponse:
    try:
        ci_id = db.insert_ci(body.name, body.ci_type.value, body.ozellikler)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"'{body.name}' zaten kayıtlı")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    created = db.get_ci_by_id(ci_id)
    assert created is not None
    logger.info("CI created: %s (%s)", body.name, body.ci_type.value)
    return CIResponse(**created)


@app.get(
    "/ci",
    response_model=list[CIResponse],
    summary="CI listele",
    description="Tüm CI'ları döner. `ci_type` ile filtreleyebilirsiniz.",
    tags=["CI"],
)
def list_cis(
    ci_type: Optional[CIType] = Query(
        default=None,
        description="CI tipine göre filtre (server, application, database, process, port)",
    ),
) -> list[CIResponse]:
    tip = ci_type.value if ci_type else None
    return [CIResponse(**row) for row in db.list_ci(tip)]


@app.put(
    "/ci/by-name/{name:path}",
    response_model=CIResponse,
    summary="CI upsert (isimle)",
    description=(
        "Discovery için idempotent yazma: isim yoksa ekler, varsa tip/özellikleri günceller. "
        "İkinci discovery koşusunda duplicate üretmez."
    ),
    tags=["CI"],
)
def upsert_ci(name: str, body: CIUpsert) -> CIResponse:
    try:
        ci_id = db.upsert_ci(name, body.ci_type.value, body.ozellikler)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = db.get_ci_by_id(ci_id)
    assert row is not None
    logger.info("CI upsert: %s (%s)", name, body.ci_type.value)
    return CIResponse(**row)


@app.get(
    "/ci/{ci_id}",
    response_model=CIResponse,
    summary="CI detayı",
    description="id ile tek CI. Yoksa 404.",
    tags=["CI"],
)
def get_ci(ci_id: int) -> CIResponse:
    row = db.get_ci_by_id(ci_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"CI id={ci_id} bulunamadı")
    return CIResponse(**row)


@app.post(
    "/iliski",
    status_code=201,
    response_model=IliskiResponse,
    summary="İlişki kur",
    description=(
        "İki CI arasında ilişki oluşturur. Kaynak veya hedef yoksa 404. "
        "Aynı üçlü varsa kritiklik güncellenir (idempotent)."
    ),
    tags=["İlişki"],
)
def create_iliski(body: IliskiCreate) -> IliskiResponse:
    kaynak = db.get_ci_by_id(body.kaynak_ci)
    hedef = db.get_ci_by_id(body.hedef_ci)
    if kaynak is None:
        raise HTTPException(status_code=404, detail=f"Kaynak CI id={body.kaynak_ci} bulunamadı")
    if hedef is None:
        raise HTTPException(status_code=404, detail=f"Hedef CI id={body.hedef_ci} bulunamadı")

    try:
        iliski_id = db.insert_iliski(
            body.kaynak_ci,
            body.hedef_ci,
            body.iliski_tipi.value,
            kritiklik=body.kritiklik,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if iliski_id is None:
        rels = db.list_iliskiler_for_ci(body.kaynak_ci)
        mevcut = next(
            (
                r
                for r in rels
                if r["hedef_ci"] == body.hedef_ci and r["iliski_tipi"] == body.iliski_tipi.value
            ),
            None,
        )
        logger.info(
            "İlişki güncellendi: %s --%s--> %s",
            kaynak["name"],
            body.iliski_tipi.value,
            hedef["name"],
        )
        return IliskiResponse(
            id=mevcut["id"] if mevcut else 0,
            kaynak_ci=body.kaynak_ci,
            hedef_ci=body.hedef_ci,
            iliski_tipi=body.iliski_tipi,
            kritiklik=body.kritiklik,
            kaynak_name=kaynak["name"],
            hedef_name=hedef["name"],
        )

    logger.info(
        "İlişki: %s --%s--> %s (kritiklik=%s)",
        kaynak["name"],
        body.iliski_tipi.value,
        hedef["name"],
        body.kritiklik,
    )
    return IliskiResponse(
        id=iliski_id,
        kaynak_ci=body.kaynak_ci,
        hedef_ci=body.hedef_ci,
        iliski_tipi=body.iliski_tipi,
        kritiklik=body.kritiklik,
        kaynak_name=kaynak["name"],
        hedef_name=hedef["name"],
    )


@app.get(
    "/ci/{ci_id}/iliskiler",
    response_model=list[IliskiResponse],
    summary="CI ilişkileri",
    description="Bir CI'ın hem giden hem gelen tüm ilişkilerini döner.",
    tags=["İlişki"],
)
def get_ci_iliskiler(ci_id: int) -> list[IliskiResponse]:
    if db.get_ci_by_id(ci_id) is None:
        raise HTTPException(status_code=404, detail=f"CI id={ci_id} bulunamadı")
    rows = db.list_iliskiler_for_ci(ci_id)
    return [IliskiResponse(**row) for row in rows]


@app.get(
    "/ci/{ci_id}/etki",
    response_model=EtkiResponse,
    summary="Etki analizi",
    description=(
        "Bu CI çökerse kim etkilenir? İlişkileri TERS yönde BFS ile gezer "
        "(APP --bagimli--> DB ise DB'nin etkisi APP'yi kapsar). "
        "Her etkilenen için derinlik döner; döngüler ziyaret seti ile kesilir."
    ),
    tags=["Analiz"],
)
def get_ci_etki(ci_id: int) -> EtkiResponse:
    baslangic = db.get_ci_by_id(ci_id)
    if baslangic is None:
        raise HTTPException(status_code=404, detail=f"CI id={ci_id} bulunamadı")
    etkilenenler = db.etki_analizi(ci_id)
    logger.info("Etki analizi CI=%s -> %d etkilenen", baslangic["name"], len(etkilenenler))
    items = [EtkiItem(**e) for e in etkilenenler]
    return EtkiResponse(
        baslangic=CIResponse(**baslangic),
        etkilenen_sayisi=len(items),
        kritik_etkilenen_sayisi=sum(1 for i in items if i.kritik_yol),
        etkilenenler=items,
    )


@app.get(
    "/ci/{ci_id}/kok-neden",
    response_model=KokNedenResponse,
    summary="Kök neden adayları",
    description=(
        "Etki analizinin tersi: bu uygulama yavaşsa altındaki hangi CI'lara bakılmalı? "
        "İlişkileri İLERİ yönde BFS ile gezer."
    ),
    tags=["Analiz"],
)
def get_ci_kok_neden(ci_id: int) -> KokNedenResponse:
    baslangic = db.get_ci_by_id(ci_id)
    if baslangic is None:
        raise HTTPException(status_code=404, detail=f"CI id={ci_id} bulunamadı")
    adaylar = db.kok_neden_analizi(ci_id)
    logger.info("Kok-neden CI=%s -> %d aday", baslangic["name"], len(adaylar))
    items = [EtkiItem(**a) for a in adaylar]
    return KokNedenResponse(
        baslangic=CIResponse(**baslangic),
        aday_sayisi=len(items),
        kritik_aday_sayisi=sum(1 for i in items if i.kritik_yol),
        adaylar=items,
    )
