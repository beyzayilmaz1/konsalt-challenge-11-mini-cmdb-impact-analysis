# Mini-CMDB ve Etki Analizi — Teknik Rapor (README)

**Program:** KONSALT Staj Programı 2026  
**Challenge:** 11 — CAPSTONE: Mini-CMDB ve Etki Analizi  
**Seviye:** Zor · **Ön koşul:** Challenge 6 (Mini Envanter API)  
**Stack:** Python 3 · FastAPI · SQLite · psutil · Streamlit  

Bu belge, projede yapılan işlerin **aşama aşama** teknik özetidir. Mimari ayrıntılar için [MIMARI.md](MIMARI.md), canlı sunum akışı için [SUNUM.md](SUNUM.md).

**Önemli:** Challenge 6 GitHub reposuna dokunulmadı. Challenge 6’daki FastAPI iskeleti (Pydantic modeller, `{"error": ...}` hata sözleşmesi, logging) bu projeye **yeniden uygulanarak** JSON kalıcılık SQLite + ilişki modeline taşındı.

---

## 0. Hazırlık

### 0.1 Bağımlılıklar

```bash
pip install -r requirements.txt
```

Kurulan paketler: `fastapi`, `uvicorn`, `psutil`, `streamlit`, `httpx`, `requests`.

### 0.2 Veri modeli (kâğıt tasarımı → kod)

İki tablo kararlaştırıldı:

| Tablo | Amaç |
|-------|------|
| `ci` | Configuration Item (düğüm) |
| `iliski` | Yönlü kenar (kaynak → hedef) |

İlişki tipleri: `calisir`, `bagimli`, `baglanir`.  
CI tipleri: `server`, `application`, `database`, `process`, `port`.

---

## 1. Aşama — Veritabanı katmanı (`db.py`)

### Yapılanlar

1. `sqlite3` ile `ci` ve `iliski` tabloları oluşturuldu (ORM yok).
2. `iliski.kaynak_ci` / `hedef_ci` → `ci.id` foreign key.
3. `UNIQUE (kaynak_ci, hedef_ci, iliski_tipi)` ile aynı ilişkinin tekrar eklenmesi engellendi.
4. Her bağlantıda `PRAGMA foreign_keys = ON` (SQLite varsayılanı kapalı).
5. Windows dosya kilidi için bağlantı context manager ile `close()` edildi.
6. Bonus: `kritiklik INTEGER 1..5` kolonu eklendi.

### Yardımcı fonksiyonlar

| Fonksiyon | İş |
|-----------|-----|
| `init_db` | Şema oluşturma |
| `insert_ci` / `upsert_ci` | CI yazma (discovery idempotency) |
| `insert_iliski` | İlişki yazma (çakışmada kritiklik güncelle) |
| `list_iliskiler_okunabilir` | `APP-X --calisir--> SRV-Y` formatı |
| `etki_analizi` | Ters yön BFS |
| `kok_neden_analizi` | İleri yön BFS (bonus) |

### Kontrol noktası (geçildi)

```bash
python db.py
```

Çıktı:

```text
CI sayısı: 3
İlişki sayısı: 2
İlişkiler:
  APP-X --calisir--> SRV-Y
  APP-X --bagimli--> DB-Z
```

---

## 2. Aşama — API katmanı (`main.py`)

### Yapılanlar

Challenge 6 API kalıpları bu şemaya taşındı:

| Endpoint | Açıklama |
|----------|----------|
| `GET /health` | Sağlık |
| `POST /ci` | CI ekle (isim çakışırsa 409) |
| `GET /ci?ci_type=` | Liste + tip filtresi |
| `GET /ci/{id}` | Tek CI |
| `PUT /ci/by-name/{name}` | Upsert (discovery) |
| `POST /iliski` | İlişki kur (CI yoksa 404) |
| `GET /ci/{id}/iliskiler` | Giden + gelen ilişkiler |
| `GET /ci/{id}/etki` | Etki analizi (Aşama 4) |
| `GET /ci/{id}/kok-neden` | Kök neden (bonus) |

Hata gövdesi Challenge 6 ile aynı: `{"error": "..."}`; doğrulama hatalarında 422 + `details`.

### Kontrol noktası (geçildi)

```bash
python -m uvicorn main:app --reload --port 8000
```

Swagger: http://localhost:8000/docs — CI ve ilişki oluşturup sorgulanabiliyor.

---

## 3. Aşama — Discovery (`discovery.py`)

### Yapılanlar

`psutil` ile yerel makine tarandı; yazmalar **yalnızca HTTP API** üzerinden (doğrudan DB yok).

| Keşif | CI tipi | İlişki |
|-------|---------|--------|
| Hostname, OS, RAM, CPU | `server` | — |
| Allowlist süreçler (python, chrome, cursor, …) | `process` | `calisir` → server |
| Dinlenen portlar | `port` | process → `baglanir` → port |

Idempotency: CI adı stabil (`process:chrome`, PID yok); `PUT /ci/by-name/...` ile upsert.  
İkinci koşuda kayıt sayısı artmadı.

### Bu makinede ölçülen sonuç

| Koşu | Toplam CI | Net artış |
|------|-----------|-----------|
| 1. discovery | ~45+ | yeni kayıtlar |
| 2. discovery | aynı | **+0** |
| Multi-node sim (`--node-name ARKADAS-LAPTOP`) | ~100 | ikinci düğüm CI’ları |
| Multi-node 2. koşu | 100 | **+0** |

### Kontrol noktası (geçildi)

15+ CI ve ilişkiler var; ikinci koşu duplicate üretmiyor.

**Not:** Port taraması bazı Windows ortamlarda yönetici izni ister. İzin yoksa süreç listesiyle yetinilir ([MIMARI.md](MIMARI.md)).

---

## 4. Aşama — Etki analizi (`db.etki_analizi` + API)

### Yapılanlar

`GET /ci/{id}/etki`: “Bu CI çökerse ne etkilenir?”

1. İlişkiler **ters** yönde okunur (`WHERE hedef_ci = ?`).
2. BFS ile derinlik hesaplanır.
3. `ziyaret` seti ile A→B→A döngüsü sonsuza girmez.
4. Bonus: yoldaki max `kritiklik` → `yol_kritikligi`; ≥4 ise `kritik_yol`.

Demo zinciri (`seed_senaryo.py`):

```text
FE-Portal --bagimli--> APP-Orders --bagimli--> ANKARA-DB01
APP-Billing --bagimli--> ANKARA-DB01
```

### Kontrol noktası (geçildi)

```bash
python seed_senaryo.py
python etki.py ANKARA-DB01
```

Sonuç: 3 CI — APP-Orders / APP-Billing (d=1), FE-Portal (d=2); kritik yollar ★ ile işaretli.

---

## 5. Aşama — Sunum arayüzü

### 5a. Streamlit (`arayuz.py`)

- CI listesi (tip filtresi)
- Seçilen CI’nın ilişkileri
- Etki analizi sonucu (“şu süreç ölürse ne olur?”)
- Kök neden paneli (bonus)

```bash
python -m streamlit run arayuz.py
```

### 5b. CLI (`etki.py`)

```bash
python etki.py ANKARA-DB01
python etki.py --id 50
```

ASCII ağaç: derinlik girintisi + kritik bayrak.

### Kontrol noktası (geçildi)

Bilgisayarı bilmeyen biri arayüzden etki sorusunun cevabını görebiliyor.

---

## 6. Aşama — Bonuslar

| Bonus | Uygulama | Doğrulama |
|-------|----------|-----------|
| Kritiklik ağırlığı | `iliski.kritiklik` 1–5; etki sıralaması kritik yola göre | `verify_challenge.py` |
| Multi-node discovery | `--api-base`, `--node-name`; CI adı `{node}::...` | `discovery.py --node-name ARKADAS-LAPTOP` |
| Kök neden | `GET /ci/{id}/kok-neden` ileri BFS | FE → APP → DB derinlikleri |

---

## 7. Doğrulama ve teslim

### Otomatik test

```bash
python verify_challenge.py
```

Beklenen kapanış: `TÜM GÖREV VE BONUS TESTLERİ GEÇTİ`.

### Teslim dosyaları

| Dosya | Rol |
|-------|-----|
| `db.py` | Veritabanı katmanı |
| `main.py` | API |
| `discovery.py` | Keşif ajanı |
| `seed_senaryo.py` | Etki demo senaryosu |
| `etki.py` | CLI arayüz |
| `arayuz.py` | Streamlit arayüz |
| `verify_challenge.py` | Kontrol noktaları |
| `MIMARI.md` | Mimari teknik rapor |
| `SUNUM.md` | 5 dk sunum senaryosu |
| `README.md` | Bu belge |

### Çalıştırma özeti (sıra)

```bash
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
python discovery.py
python discovery.py
python seed_senaryo.py
python etki.py ANKARA-DB01
python -m streamlit run arayuz.py
python verify_challenge.py
```
"# konsalt-challenge-11-mini-cmdb-impact-analysis" 
