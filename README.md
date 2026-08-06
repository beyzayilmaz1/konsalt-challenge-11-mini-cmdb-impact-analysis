# Mini-CMDB ve Etki Analizi

**KONSALT Staj Programı 2026 — Challenge 11 (Capstone)**  
Seviye: Zor · Stack: Python 3, FastAPI, SQLite, psutil, Streamlit  

Bu README, projede **ne yapıldığını adım adım anlatır**. Mimari gerekçeler için [MIMARI.md](MIMARI.md).

Challenge 6 Mini Envanter API bu işin ön koşuludur. O projedeki FastAPI iskeleti (Pydantic, hata gövdesi, logging) buraya taşındı; kalıcılık JSON dosyasından SQLite’a geçirildi. Challenge 6 reposuna **dokunulmadı**.

---

## Adım 0 — Projeye nasıl başlandı?

Önce challenge’ın istediği veri modeli kâğıda çizildi: bir tarafta CI’lar (sunucu, uygulama, veritabanı, süreç, port), diğer tarafta aralarındaki yönlü ilişkiler (`calisir`, `bagimli`, `baglanir`). Amaç, “liste tutmak” değil; **ilişki grafı** kurup “şu CI çökerse kim etkilenir?” sorusuna cevap vermekti.

Bağımlılıklar kuruldu:

```bash
pip install -r requirements.txt
```

Ardından işler challenge görev sırasına göre yapıldı: önce veritabanı, sonra API, sonra discovery, sonra etki analizi, en sonda arayüz ve bonuslar.

---

## Adım 1 — Veritabanı katmanı nasıl kuruldu?

`db.py` yazıldı. ORM kullanılmadı; Python’un yerleşik `sqlite3` modülüyle SQL doğrudan görülsün istendi.

İki tablo oluşturuldu:

- **`ci`:** her varlık bir satır. `id`, benzersiz `name`, `ci_type`, JSON `ozellikler`.
- **`iliski`:** kaynak CI → hedef CI, ilişki tipi. Aynı üçlünün ikinci kez eklenmesini `UNIQUE` engeller. Kaynak/hedef `ci.id`’ye foreign key ile bağlıdır.

SQLite’ta foreign key’ler varsayılan kapalı olduğu için her bağlantıda `PRAGMA foreign_keys = ON` çalıştırıldı. Windows’ta dosya kilidi yaşamamak için bağlantı iş bitince kapatıldı.

Bonus olarak ilişkilere `kritiklik` (1–5) eklendi; ileride etki analizinde kritik yolları öne çıkarmak için.

Kontrol için elle 3 CI ve 2 ilişki eklendi, JOIN ile okundu:

```bash
python db.py
```

Beklenen çıktı:

```text
APP-X --calisir--> SRV-Y
APP-X --bagimli--> DB-Z
```

Bu kontrol noktası geçildiğinde bir sonraki adıma geçildi.

---

## Adım 2 — API katmanı nasıl taşındı?

Challenge 6’daki envanter API düşüncesi SQLite şemasına uyarlandı. `main.py` FastAPI uygulaması oldu. Bellekteki `dict` + `envanter.json` yerine tüm okuma/yazma `db.py` üzerinden gitti.

Yapılan uçlar şöyle:

Önce CI tarafı eklendi: yeni CI oluşturma (`POST /ci`), tip filtreli liste (`GET /ci`), tek kayıt (`GET /ci/{id}`). Discovery’nin aynı CI’yı tekrar tekrar yazabilmesi için isimle upsert (`PUT /ci/by-name/{name}`) eklendi.

Sonra ilişki tarafı eklendi: iki CI arasında kenar kurma (`POST /iliski` — CI yoksa 404), bir CI’nın her iki yöndeki ilişkileri (`GET /ci/{id}/iliskiler`).

Hata formatı Challenge 6 ile aynı bırakıldı: `{"error": "..."}`. Böylece önceki challenge’daki sözleşme bozulmadı.

API şöyle ayağa kalkar:

```bash
python -m uvicorn main:app --reload --port 8000
```

- Portal: http://localhost:8000/
- Swagger: http://localhost:8000/docs  

Swagger’dan CI ve ilişki oluşturup sorgulamak bu adımın kontrol noktasıydı; geçildi.

---

## Adım 3 — Discovery nasıl yazıldı?

Envanteri elle doldurmak yerine `discovery.py` yazıldı. Script `psutil` ile makineyi tarar ama **doğrudan veritabanına yazmaz**; her şeyi HTTP ile API’ye gönderir. Bu, gerçek CMDB’lerde ajanın ayrı, CMDB’nin system of record olması kuralının minyatürüdür.

Keşif sırası şöyle işler:

1. Makinenin kendisi bir `server` CI olur (hostname, OS, RAM, CPU).
2. Tüm süreçler değil; izin listesindeki ilginç süreçler (`python`, `chrome`, `cursor`, `node` vb.) `process` CI olur ve sunucuya `calisir` ilişkisiyle bağlanır.
3. Dinleyen portlar `port` CI olur; hangi süreç dinliyorsa ona `baglanir` ilişkisi kurulur.

İkinci kez çalıştırınca duplicate oluşmaması için CI adları stabil tutuldu (isimde PID yok) ve upsert kullanıldı. Bu makinede birinci koşuda 15’ten fazla CI oluştu; ikinci koşuda net artış **sıfır** oldu.

```bash
python discovery.py
python discovery.py   # net +0 beklenir
```

Port bilgisi bazı Windows kurulumlarında yönetici izni ister. İzin yoksa port adımı atlanır; süreç ve sunucu kayıtları yine yazılır. Bu durum mimari raporda da belirtilmiştir.

---

## Adım 4 — Etki analizi nasıl eklendi?

Projenin kalbi `GET /ci/{id}/etki` uçudur. Soru: “Bu CI çökerse ne etkilenir?”

İlişkiler kayıtta `APP --bagimli--> DB` yönünde tutulduğu için etki, okun **tersinden** okunur: DB çökünce DB’ye bağımlı olanlar etkilenir. Bu gezinme BFS ile yapıldı; her etkilenen için derinlik tutuldu. Aynı düğüme tekrar gelinmesin diye ziyaret seti kullanıldı (döngüde sonsuza düşülmesin diye).

Test için `seed_senaryo.py` ile küçük bir zincir kuruldu: bir veritabanı, iki uygulama, bir frontend. Sonra:

```bash
python seed_senaryo.py
python etki.py ANKARA-DB01
```

Beklenen (ekran görüntüsü / sunum ile aynı):

```text
FRONTEND-WEB --bagimli(k=5)--> APP-ORDER --bagimli(k=5)--> ANKARA-DB01
FRONTEND-WEB --bagimli(k=2)--> APP-BILLING --bagimli(k=2)--> ANKARA-DB01
```

`ANKARA-DB01` etkisi: **3 etkilenen**, **2 kritik yol**  
(APP-ORDER d=1★, APP-BILLING d=1, FRONTEND-WEB d=2★). Döngü senaryosu sonsuza girmedi. Kontrol noktası geçildi.

---

## Adım 5 — Sunum arayüzü nasıl yapıldı?

Challenge en az bir arayüz istedi; ikisi de yapıldı.

**Streamlit (`arayuz.py`):** Koyu sidebar, tip/isim filtresi, “Hangi CI çökerse?” seçimi; sekmeler: Etki analizi / İlişkiler / Kök neden. Özet kartlarda etkilenen ve kritik yol sayıları görünür.

```bash
python -m streamlit run arayuz.py
```

**CLI (`etki.py`):** ASCII ağaç basar. Ters bağımlılık ağacı + API’den gelen derinlik/kritiklik listesi birlikte gösterilir.

```bash
python etki.py ANKARA-DB01
```

Böylece bilgisayarı bilmeyen biri de arayüzden etkiyi okuyabilir.

---

## Adım 6 — Bonuslar nasıl eklendi?

Erken bitince üç bonus da uygulandı:

**Kritiklik:** İlişkiye 1–5 ağırlık verildi. Etki sonucunda yoldaki en yüksek kritiklik taşınır; 4 ve üzeri `kritik_yol` olur ve listede öne çıkar.

**Multi-node:** Discovery’ye `--api-base` ve `--node-name` eklendi. İkinci bir makine (veya aynı makinede simülasyon) API’ye yazınca CI adları `ARKADAS-LAPTOP::process:chrome` gibi namespace’lenir; düğümler çakışmaz. İkinci koşu yine +0 verir.

**Kök neden:** `GET /ci/{id}/kok-neden` eklendi. Etki analizinin tersi: “bu uygulama yavaşsa altına bak” — ileri yön BFS.

---

## Adım 7 — Nasıl doğrulandı ve ne teslim edildi?

Uçtan uca kontrol:

```bash
python verify_challenge.py
python test_etki.py
python -m pytest -q
```

Beklenen: görev + bonus testlerinin geçmesi ve pytest’in yeşil olması.

Teslim edilen başlıca parçalar:

| Dosya / klasör | Ne işe yarar |
|----------------|--------------|
| `db.py` | SQLite şema, CRUD, BFS |
| `main.py` | API, portal, Swagger |
| `discovery.py` | psutil keşif (yalnızca HTTP) |
| `seed_senaryo.py` | Etki demo zinciri |
| `etki.py` / `arayuz.py` | CLI + Streamlit |
| `static/` | Portal ve Swagger teması |
| `tests/` | pytest testleri |
| `MIMARI.md` | Mimari teknik rapor |

### Sıfırdan çalıştırma sırası

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

Port 8000 doluysa (`WinError 10013`) eski Python sürecini kapatın veya `--port 8001` kullanın.
