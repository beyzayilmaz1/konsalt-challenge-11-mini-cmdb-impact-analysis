"""
Görev 5 — Streamlit sunum arayüzü (profesyonel tema).

  python -m streamlit run arayuz.py
"""

from __future__ import annotations

import html
from typing import Any

import httpx
import streamlit as st

BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Mini-CMDB · Etki Analizi",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap');

:root {
  --ink: #0b1220;
  --muted: #5b6578;
  --line: #d8dee8;
  --bg: #eef2f6;
  --card: #ffffff;
  --accent: #0f766e;
  --accent-soft: #ccfbf1;
  --crit: #b45309;
  --crit-soft: #ffedd5;
}

html, body, [class*="css"] {
  font-family: "DM Sans", "Segoe UI", sans-serif !important;
}

.stApp {
  background:
    radial-gradient(900px 420px at 8% -12%, rgba(15, 118, 110, 0.14), transparent 55%),
    radial-gradient(700px 360px at 100% 0%, rgba(15, 23, 42, 0.06), transparent 48%),
    var(--bg);
}

[data-testid="stSidebar"] {
  background: #0f172a !important;
  border-right: 1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] label { color: #94a3b8 !important; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: #f8fafc !important;
}

#MainMenu, footer, header { visibility: hidden; }
div[data-testid="stToolbar"] { display: none; }

.block-container {
  padding-top: 1.4rem !important;
  padding-bottom: 2.5rem !important;
  max-width: 1180px;
}

.hero {
  background: linear-gradient(135deg, #0f172a 0%, #134e4a 100%);
  color: #f8fafc;
  border-radius: 16px;
  padding: 22px 26px;
  margin-bottom: 18px;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.18);
}
.hero .eyebrow {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #99f6e4;
  font-weight: 600;
  margin-bottom: 6px;
}
.hero h1 {
  margin: 0;
  font-size: 1.85rem;
  letter-spacing: -0.02em;
  font-weight: 700;
  color: #fff !important;
}
.hero p {
  margin: 8px 0 0;
  color: #cbd5e1;
  font-size: 0.98rem;
  max-width: 42rem;
  line-height: 1.45;
}

.panel {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px 18px;
  margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.panel h3 {
  margin: 0 0 10px;
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--ink);
  letter-spacing: -0.01em;
}

.stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.stat {
  flex: 1;
  min-width: 120px;
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
}
.stat .lbl { font-size: 0.75rem; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
.stat .val { font-size: 1.55rem; font-weight: 700; color: var(--ink); margin-top: 2px; letter-spacing: -0.02em; }
.stat.accent { background: var(--accent-soft); border-color: #99f6e4; }
.stat.accent .val { color: var(--accent); }
.stat.warn { background: var(--crit-soft); border-color: #fdba74; }
.stat.warn .val { color: var(--crit); }

.ci-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: #f1f5f9;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--ink);
  margin: 0 6px 6px 0;
}
.ci-chip .type {
  background: var(--accent);
  color: #fff;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 0.72rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.edge {
  font-family: "IBM Plex Mono", Consolas, monospace;
  font-size: 0.82rem;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.edge .arrow { color: #5eead4; }
.edge .meta { color: #94a3b8; font-size: 0.75rem; margin-top: 4px; }

.impact-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  margin-bottom: 8px;
  background: #fff;
}
.impact-item.critical {
  border-color: #fdba74;
  background: linear-gradient(90deg, #fff7ed, #ffffff);
}
.impact-item .depth {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: var(--accent);
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.85rem;
  flex-shrink: 0;
}
.impact-item .body { flex: 1; min-width: 0; }
.impact-item .name { font-weight: 650; color: var(--ink); font-size: 0.95rem; }
.impact-item .sub { color: var(--muted); font-size: 0.8rem; margin-top: 2px; }
.badge {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--crit-soft);
  color: var(--crit);
  white-space: nowrap;
}

.empty {
  color: var(--muted);
  font-size: 0.92rem;
  padding: 8px 0;
}

div[data-testid="stTabs"] button {
  font-weight: 600 !important;
}
</style>
""",
    unsafe_allow_html=True,
)


def api_get(path: str) -> Any:
    try:
        r = httpx.get(f"{BASE_URL}{path}", timeout=10.0)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        st.error(f"API hatası: {exc}")
        st.info("Önce API'yi başlatın: `python -m uvicorn main:app --port 8000`")
        st.stop()


def esc(value: Any) -> str:
    return html.escape(str(value))


health = api_get("/health")
if health.get("status") != "ok":
    st.error("API health başarısız")
    st.stop()

cis = api_get("/ci")
if not cis:
    st.warning("CMDB boş. Önce `python discovery.py` veya `python test_etki.py` çalıştırın.")
    st.stop()

with st.sidebar:
    st.markdown("### Mini-CMDB")
    st.caption("Konsalt Challenge 11")
    st.markdown("---")
    tipler = sorted({c["ci_type"] for c in cis})
    secili_tipler = st.multiselect("CI tipi", tipler, default=tipler)
    arama = st.text_input("İsim ara", placeholder="ANKARA-DB01…")
    st.markdown("---")
    st.markdown(f"**{len(cis)}** CI kayıtlı")
    st.caption(BASE_URL)

filtreli = [
    c
    for c in cis
    if c["ci_type"] in secili_tipler and (arama.lower() in c["name"].lower() if arama else True)
]
filtreli.sort(key=lambda c: c["name"].lower())

if not filtreli:
    st.warning("Filtreye uyan CI yok.")
    st.stop()

# Prefer demo CI when present
varsayilan_idx = 0
for i, c in enumerate(filtreli):
    if c["name"] == "ANKARA-DB01":
        varsayilan_idx = i
        break

etiketler = [f"{c['name']}  ·  {c['ci_type']}" for c in filtreli]

st.markdown(
    """
<div class="hero">
  <div class="eyebrow">Konsalt · Capstone</div>
  <h1>Mini-CMDB — Etki Analizi</h1>
  <p>Bir CI seçin. Ters BFS ile çökme etkisini, ileri BFS ile kök neden adaylarını görün.</p>
</div>
""",
    unsafe_allow_html=True,
)

secim = st.selectbox("Hangi CI çökerse?", etiketler, index=varsayilan_idx)
ci = filtreli[etiketler.index(secim)]

iliskiler = api_get(f"/ci/{ci['id']}/iliskiler")
etki = api_get(f"/ci/{ci['id']}/etki")
kok = api_get(f"/ci/{ci['id']}/kok-neden")

ozellik_txt = ", ".join(f"{k}={v}" for k, v in (ci.get("ozellikler") or {}).items()) or "—"

st.markdown(
    f"""
<div class="panel">
  <h3>Seçilen CI</h3>
  <div class="ci-chip"><span class="type">{esc(ci["ci_type"])}</span> {esc(ci["name"])} · id={esc(ci["id"])}</div>
  <div class="empty">Özellikler: {esc(ozellik_txt)}</div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("##### İnceleme sekmeleri")
st.caption("Ortadaki **İlişkiler** sekmesine tıkla — gelen/giden kenarları görürsün.")
tab_etki, tab_iliski, tab_kok = st.tabs(
    ["1 · Etki analizi", "2 · İlişkiler", "3 · Kök neden"]
)

with tab_etki:
    n = etki["etkilenen_sayisi"]
    k = etki.get("kritik_etkilenen_sayisi", 0)
    st.markdown(
        f"""
<div class="stat-row">
  <div class="stat accent"><div class="lbl">Etkilenen CI</div><div class="val">{n}</div></div>
  <div class="stat warn"><div class="lbl">Kritik yol</div><div class="val">{k}</div></div>
  <div class="stat"><div class="lbl">Başlangıç</div><div class="val" style="font-size:1.05rem;padding-top:8px;">{esc(ci["name"])}</div></div>
</div>
""",
        unsafe_allow_html=True,
    )

    if not etki["etkilenenler"]:
        st.markdown('<div class="panel"><div class="empty">Ters bağımlılık yok — başka CI etkilenmiyor.</div></div>', unsafe_allow_html=True)
    else:
        cards = []
        for e in etki["etkilenenler"]:
            krit = bool(e.get("kritik_yol"))
            cls = "impact-item critical" if krit else "impact-item"
            badge = '<span class="badge">Kritik</span>' if krit else ""
            pad = max(0, int(e["derinlik"]) - 1) * 18
            cards.append(
                f"""
<div class="{cls}" style="margin-left:{pad}px">
  <div class="depth">d{esc(e["derinlik"])}</div>
  <div class="body">
    <div class="name">{esc(e["name"])}</div>
    <div class="sub">{esc(e["ci_type"])} · yol kritiklik {esc(e.get("yol_kritikligi", "-"))}</div>
  </div>
  {badge}
</div>
"""
            )
        st.markdown('<div class="panel"><h3>Etki zinciri</h3>' + "".join(cards) + "</div>", unsafe_allow_html=True)

with tab_iliski:
    if not iliskiler:
        st.markdown('<div class="panel"><div class="empty">İlişki yok.</div></div>', unsafe_allow_html=True)
    else:
        blocks = []
        for r in iliskiler:
            blocks.append(
                f"""
<div class="edge">
  {esc(r["kaynak_name"])} <span class="arrow">--{esc(r["iliski_tipi"])}--&gt;</span> {esc(r["hedef_name"])}
  <div class="meta">yön: {esc(r.get("yon", "-"))} · kritiklik: {esc(r.get("kritiklik", 1))}</div>
</div>
"""
            )
        st.markdown('<div class="panel"><h3>Gelen / giden kenarlar</h3>' + "".join(blocks) + "</div>", unsafe_allow_html=True)

with tab_kok:
    st.markdown(
        f"""
<div class="stat-row">
  <div class="stat accent"><div class="lbl">Aday CI</div><div class="val">{kok["aday_sayisi"]}</div></div>
  <div class="stat warn"><div class="lbl">Kritik aday</div><div class="val">{kok.get("kritik_aday_sayisi", 0)}</div></div>
</div>
""",
        unsafe_allow_html=True,
    )
    if not kok["adaylar"]:
        st.markdown('<div class="panel"><div class="empty">Alt bağımlılık yok.</div></div>', unsafe_allow_html=True)
    else:
        cards = []
        for a in kok["adaylar"]:
            krit = bool(a.get("kritik_yol"))
            cls = "impact-item critical" if krit else "impact-item"
            badge = '<span class="badge">Kritik</span>' if krit else ""
            pad = max(0, int(a["derinlik"]) - 1) * 18
            cards.append(
                f"""
<div class="{cls}" style="margin-left:{pad}px">
  <div class="depth">d{esc(a["derinlik"])}</div>
  <div class="body">
    <div class="name">{esc(a["name"])}</div>
    <div class="sub">{esc(a["ci_type"])} · yol kritiklik {esc(a.get("yol_kritikligi", "-"))}</div>
  </div>
  {badge}
</div>
"""
            )
        st.markdown(
            '<div class="panel"><h3>Nereye bakmalı?</h3>' + "".join(cards) + "</div>",
            unsafe_allow_html=True,
        )

st.caption("Sunum ipucu: ANKARA-DB01 → Etki · FRONTEND-WEB → Kök neden")
