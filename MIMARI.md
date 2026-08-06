# Mini-CMDB — Mimari Teknik Rapor

**Proje:** KONSALT Challenge 11 Capstone — Mini-CMDB ve Etki Analizi  
**Stack:** FastAPI · SQLite · psutil · Streamlit / CLI  
**Belge amacı:** Bu sistem **neden** böyle kuruldu, adım adım hangi kararlar alındı?

Aşağıdaki metin checklist değil; mimariyi anlatan teknik rapordur. Çalıştırma adımları için [README.md](README.md).

---

## 1. Önce problem netleştirildi

Konsalt’ın ana ürün alanı CMDB’dir. CMDB yalnızca “sunucu listesi” değildir; varlıklar **ve** aralarındaki ilişkilerdir. Asıl değer şu sorudadır:

> ANKARA-DB01 çökerse hangi uygulamalar etkilenir?

Bu soruyu Excel satırlarıyla cevaplamak yavaştır. UCMDB / ServiceNow gibi ürünler ilişki grafı tuttuğu için saniyelerde cevap verir. Capstone’da yapılmak istenen, bunun çalışan bir minyatürünü kurmaktı: envanteri elle değil **discovery** ile doldurmak, etkiyi **graf gezinmesi** ile hesaplamak.

Kapsam bilerek dar tutuldu: tek SQLite dosyası, beş CI tipi, üç ilişki tipi, HTTP API, Streamlit/CLI sunum. Çok kiracılılık, federasyon, change/incident entegrasyonu bilinçli olarak dışarıda bırakıldı.

Challenge 6 Mini Envanter API ön koşuldur. Oradaki FastAPI + Pydantic + hata sözleşmesi bu projeye taşındı; `envanter.json` kalıcılığı SQLite + ilişki modeline evrildi. Challenge 6 reposuna yazılmadı.

---

## 2. Veri modeli adım adım tasarlandı

İlk iş kâğıtta iki varlık çizmekti:

1. **CI (configuration item)** — grafın düğümü  
2. **İlişki** — grafın yönlü kenarı  

Sonra bu model `db.py` içinde SQLite tablolarına indirgendi. ORM kullanılmadı; challenge SQL’i görünür kılmayı istediği için `sqlite3` tercih edildi.

```text
┌─────────────────────────┐         ┌──────────────────────────────┐
│           ci            │         │           iliski             │
├─────────────────────────┤         ├──────────────────────────────┤
│ id          INTEGER PK  │◄── FK ──│ kaynak_ci   INTEGER           │
│ name        TEXT UNIQUE │◄── FK ──│ hedef_ci    INTEGER           │
│ ci_type     TEXT CHECK  │         │ iliski_tipi TEXT CHECK        │
│ ozellikler  TEXT (JSON) │         │ kritiklik   INTEGER 1..5      │
└─────────────────────────┘         │ UNIQUE(kaynak, hedef, tip)    │
                                    └──────────────────────────────┘
```

`ci_type` değerleri: `server`, `application`, `database`, `process`, `port`.  
İlişki tipleri: `calisir` (kaynak hedefte çalışır), `bagimli` (kaynak hedefe bağımlı), `baglanir` (kaynak porta bağlanır).

Bu aşamada alınan kritik kararlar şunlardı:

- **`name` benzersiz olsun.** Discovery aynı varlığı tekrar gördüğünde “yeni kayıt” değil “güncelle” demek için doğal anahtar gerekti.
- **Aynı ilişki iki kez eklenemesin.** `UNIQUE(kaynak, hedef, tip)` ile sağlandı; tekrar gelirse kritiklik güncellenir.
- **Foreign key her bağlantıda açılsın.** SQLite varsayılanı kapalıdır; unutulursa sahte CI id’leriyle ilişki yazılabilir.
- **Özellikler JSON text olsun.** RAM, OS, port numarası gibi alanlar sabit kolon yapmak yerine esnek tutuldu.
- **Bağlantı kapatılsın.** Windows’ta açık bırakılan SQLite bağlantısı dosya kilidine yol açabiliyordu.

İlişki ok yönü bilerek “bağımlılık / yerleşim” anlamında kaydedildi. Etki analizi ise okun **tersini** izler: `APP --bagimli--> DB` kaydında çöken taraf DB ise etkilenen APP’dir. Bu yüzden etki sorgusu `WHERE hedef_ci = ?` ile yazıldı.

Şema doğrulaması elle yapıldı: 3 CI, 2 ilişki, JOIN çıktısı `APP-X --calisir--> SRV-Y` formatında okundu. Ancak bu geçildikten sonra API katmanına geçildi.

---

## 3. Servis katmanı neden ayrı tutuldu?

İkinci adımda `main.py` yazıldı. Katmanlı mimari bilerek şöyle kuruldu:

```text
  [discovery.py] --HTTP--> [FastAPI / main.py] --SQL--> [SQLite cmdb.db]
                                   |
                    +--------------+--------------+
                    |              |              |
                 Portal/Swagger  Streamlit     CLI (etki.py)
```

Discovery’nin veya Streamlit’in doğrudan `cmdb.db` dosyasına yazması engellendi. Tek yazma otoritesi API’dir. Bunun gerekçesi pratiktir: aynı keşif scripti başka bir laptopta çalışıp sizin API’nize yazabilsin; CMDB tek “gerçek kaynak” kalsın.

API uçları Challenge 6 alışkanlığıyla eklendi. Önce CI oluşturma/listeleme/detay, sonra discovery için isimle upsert, sonra ilişki kurma ve her iki yönde ilişki okuma. En sonda analiz uçları (`/etki`, `/kok-neden`) bağlandı.

Hata gövdesi bilinçli olarak Challenge 6 ile aynı bırakıldı (`{"error": "..."}`). Böylece staj boyunca öğrenilen API sözleşmesi bozulmadı; yalnızca veri modeli büyüdü.

Portal (`static/index.html`) ve özel Swagger teması, sunumda “ürün gibi” giriş noktası olsun diye eklendi. `/docs` ve `/redoc` özel route’larla sunulur.

---

## 4. Discovery mimarisi nasıl kuruldu?

Üçüncü adımda envanteri elle doldurmak yerine `discovery.py` yazıldı. Akış tek yönlüdür:

```text
psutil ile hostu oku → CI/ilişki adayı üret → HTTP PUT/POST → API kaydetsin
```

Keşif üç katmanda yapılır:

1. **Sunucu:** hostname, işletim sistemi, RAM, CPU sayısı bir `server` CI olur.  
2. **Süreç:** Tüm process’ler alınmaz. Allowlist (python, chrome, cursor, node, sqlservr…) ile “ilginç” olanlar seçilir; her biri `process` CI olur ve sunucuya `calisir` ile bağlanır.  
3. **Port:** Dinleyen soketler `port` CI olur; hangi süreç dinliyorsa `baglanir` ilişkisi kurulur.

Idempotency (Challenge 7 dersi) özellikle tasarlandı. Süreç CI adında PID kullanılmadı; aksi halde her restart yeni CI doğururdu. Bunun yerine `process:chrome` gibi stabil isim + upsert kullanıldı. İkinci discovery koşusunda CI sayısı artmaz.

Multi-node için isimler `{node}::process:chrome` biçiminde namespace’lendi. Böylece iki makinedeki aynı chrome süreci çakışmaz. `--api-base` ile uzak CMDB’ye yazmak mümkündür.

Windows’ta `net_connections` yönetici izni isteyebilir. İzin yoksa port adımı atlanır; server ve process kayıtları yine yazılır. Challenge metni bunu açıkça kabul eder; mimari rapor da bunu belgeler.

Bu ortamda yerel discovery 15+ CI üretti; ikinci koşu net +0 verdi. `ARKADAS-LAPTOP` ile yapılan simülasyonda ikinci düğüm CI’ları eklendi ve o düğüm için de ikinci koşu +0 kaldı.

---

## 5. Etki analizi neden BFS ve neden ters yön?

Dördüncü adım projenin kalbidir. `db.etki_analizi` bir BFS uygular:

- Kuyruk `(ci_id, derinlik, yol_kritikligi)` tutar.  
- Ziyaret seti döngüyü keser.  
- Komşular **ters** yönden gelir: bu CI hedef ise, ona kenar çizen kaynaklar etkilenir.  
- Derinlik > 0 olanlar sonuca yazılır (başlangıç CI “etkilenen” sayılmaz).  

Bonus kritiklik şöyle işler: yolda görülen kenarların maksimum kritikliği `yol_kritikligi` olur; 4 ve üzeriyse `kritik_yol=True` olur. Sonuç listesi önce kritik yola, sonra derinliğe göre sıralanır. Böylece operatör “önce nereye bakmalı?”yu listeden okur.

Test senaryosu (`seed_senaryo.py`) bilerek küçük tutuldu ve ekran görüntüsüyle aynı isimler kullanıldı:

```text
FRONTEND-WEB --bagimli(k=5)--> APP-ORDER --bagimli(k=5)--> ANKARA-DB01
FRONTEND-WEB --bagimli(k=2)--> APP-BILLING --bagimli(k=2)--> ANKARA-DB01
```

`ANKARA-DB01` sorgulandığında **3 etkilenen** ve **2 kritik yol** döner:
APP-ORDER (d=1, kritik), APP-BILLING (d=1, kritik değil), FRONTEND-WEB (d=2, kritik).
Bu, challenge’ın istediği “1 DB ← 2 uygulama ← 1 frontend” kontrolüdür.

Kök neden (`/kok-neden`) aynı motorun ileri yönüdür. Soru tersine döner: “uygulama yavaşsa altındaki hangi CI’lara bakmalıyım?” FRONTEND-WEB için cevap APP’ler (d=1) ve DB (d=2) olur.

---

## 6. Sunum katmanı neden API’nin üstünde kaldı?

Beşinci adımda iki tüketici yazıldı:

- **Streamlit (`arayuz.py`):** CI seçilir; ilişkiler, etki ve kök neden aynı ekranda gösterilir. “Şu süreç ölürse ne olur?” sorusu bilinçli olarak metne gömüldü.  
- **CLI (`etki.py`):** ASCII ağaç ile ters bağımlılık basılır; yanında API BFS listesi (derinlik + kritiklik) yer alır.

İkisi de DB dosyasını açmaz; HTTP okur. Bu sayede sunum katmanı, keşif katmanı gibi, servisten bağımsız değiştirilebilir.

---

## 7. Gerçek UCMDB bundan farklı olarak neler yapıyordur?

Bu Mini-CMDB ile üretim CMDB aynı çekirdeği paylaşır: **keşif → ilişki grafı → etki**. Fark ölçek ve süreçtedir.

Üretim UCMDB / ServiceNow tarafında tipik olarak şunlar vardır: yüzlerce federasyonlu discovery probe, zengin CI tip hiyerarşisi, reconciliation (aynı varlığın birden fazla kaynaktan gelince birleştirilmesi), change/incident/SLA bağları, RBAC ve audit, tarihçe / baseline / drift. Bizde tek SQLite, beş tip, üç ilişki, basit upsert ve eğitim API’si vardır.

Yani bu proje “UCMDB’nin tamamı” değildir; UCMDB’nin **neden var olduğunu** staj ölçeğinde kanıtlayan bir mimari egzersizdir.

---

## 8. Dosyalar mimaride nereye oturur?

| Dosya | Mimari rolü | Hangi adımda doğdu |
|-------|-------------|--------------------|
| `db.py` | Kalıcılık + BFS motoru | Veri modeli / etki |
| `main.py` | System of record API | Servis katmanı |
| `discovery.py` | Keşif ajanı (HTTP yazıcı) | Discovery |
| `seed_senaryo.py` | Kontrollü demo grafı | Etki testi |
| `etki.py` / `arayuz.py` | Operatör arayüzü | Sunum |
| `static/` | Portal / docs yüzeyi | Sunum |
| `tests/` · `verify_challenge.py` | Doğrulama ağı | Tüm aşamalar |

---

## Sonuç

Mimari, challenge’ın istediği sırayla kuruldu: önce ilişkisel model, sonra API, sonra discovery, sonra graf üzerinde etki, en sonda sunum. Katmanlar birbirine HTTP veya SQL sözleşmesiyle bağlıdır; discovery DB’ye, UI da DB’ye doğrudan inmez. Bonus kritiklik, multi-node ve kök-neden aynı çekirdeğin üzerine eklendi; mimariyi bozmadan genişletildi.
