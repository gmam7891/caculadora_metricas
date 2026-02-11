import os
import re
import statistics
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from src.twitch_client import TwitchClient
from src import storage
from src.influencer_metrics import influencer_calcs, fee_max_by_roi, fee_max_by_cpa
from src.projections import project_twitch


def fmt_money(v, prefix="R$ "):
    if v is None:
        return "-"
    return f"{prefix}{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_int(v):
    if v is None:
        return "-"
    try:
        return f"{int(round(v)):,}".replace(",", ".")
    except Exception:
        return "-"

def fmt_float(v, nd=2):
    if v is None:
        return "-"
    return f"{v:.{nd}f}".replace(".", ",")

def parse_twitch_duration_to_hours(s: str) -> float:
    if not s:
        return 0.0
    h = m = sec = 0
    mh = re.search(r"(\d+)h", s)
    mm = re.search(r"(\d+)m", s)
    ms = re.search(r"(\d+)s", s)
    if mh: h = int(mh.group(1))
    if mm: m = int(mm.group(1))
    if ms: sec = int(ms.group(1))
    return h + (m / 60) + (sec / 3600)

def vod_summary(vods: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    if not vods:
        return {"vod_count": 0, "avg_vod_views": None, "median_vod_views": None, "views_per_hour": None}

    views = [int(v.get("view_count", 0)) for v in vods]
    hours = [parse_twitch_duration_to_hours(v.get("duration", "")) for v in vods]
    total_views = sum(views)
    total_hours = sum(hours)

    avg_v = (total_views / len(views)) if views else None
    med_v = float(statistics.median(views)) if views else None
    vph = (total_views / total_hours) if total_hours > 0 else None

    return {"vod_count": len(vods), "avg_vod_views": avg_v, "median_vod_views": med_v, "views_per_hour": vph}

def load_streamers_file(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s.lower())
    seen = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


load_dotenv()

st.set_page_config(page_title="Valuation Influenciadores + Twitch", layout="wide")
st.title("Valuation Influenciadores + Twitch")

def get_cfg(key: str, default: str = "") -> str:
    # 1) .env / env vars
    v = os.getenv(key)
    if v:
        return v
    # 2) Streamlit Secrets (Cloud)
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default

client_id = get_cfg("TWITCH_CLIENT_ID", "")
client_secret = get_cfg("TWITCH_CLIENT_SECRET", "")
db_path = get_cfg("APP_DB_PATH", "./data/app.db")


conn = storage.connect(db_path)
storage.init_db(conn)

tabs = st.tabs(["Influenciador", "Twitch (Avg/Peak + Projeções)", "Como rodar"])

# -------------------
# Influenciador
# -------------------
with tabs[0]:
    c1, c2 = st.columns([1, 1])

    with c1:
        st.subheader("Inputs (manual)")
        fee = st.number_input("Fee / investimento (R$)", min_value=0.0, value=50000.0, step=1000.0)

        st.markdown("### Instagram Reels")
        reels_qty = st.number_input("Qtd Reels", min_value=0, value=2, step=1)
        reels_avg_views = st.number_input("Views médias por Reel", min_value=0.0, value=150000.0, step=1000.0)
        reels_ctr = st.number_input("CTR Reels (0,003 = 0,3%)", min_value=0.0, value=0.003, step=0.001, format="%.6f")

        st.markdown("### Instagram Stories")
        stories_qty = st.number_input("Qtd Stories (frames/combos)", min_value=0, value=6, step=1)
        stories_avg_views = st.number_input("Views médias por Story", min_value=0.0, value=40000.0, step=1000.0)
        stories_ctr = st.number_input("CTR Stories (0,01 = 1%)", min_value=0.0, value=0.01, step=0.001, format="%.6f")

        st.markdown("### TikTok")
        tiktok_qty = st.number_input("Qtd TikToks", min_value=0, value=1, step=1)
        tiktok_avg_views = st.number_input("Views médias por TikTok", min_value=0.0, value=200000.0, step=1000.0)
        tiktok_ctr = st.number_input("CTR TikTok", min_value=0.0, value=0.002, step=0.001, format="%.6f")

        st.markdown("### Funil (FTD)")
        manual_clicks_toggle = st.checkbox("Tenho cliques reais (sobrescrever CTR)", value=False)
        manual_clicks = None
        if manual_clicks_toggle:
            manual_clicks = st.number_input("Cliques reais (total)", min_value=0.0, value=1200.0, step=50.0)

        manual_ftd_toggle = st.checkbox("Tenho FTD real (sobrescrever projeção)", value=False)
        manual_ftd = None
        if manual_ftd_toggle:
            manual_ftd = st.number_input("FTD real (total)", min_value=0.0, value=0.0, step=1.0)

        cvr_ftd = st.number_input("CVR para FTD (0,02 = 2%)", min_value=0.0, value=0.02, step=0.005, format="%.6f")
        value_per_ftd = st.number_input("Valor por FTD (R$) — LTV/NGR médio", min_value=0.0, value=600.0, step=50.0)

        st.markdown("### Metas")
        target_roi = st.number_input("ROI alvo (0,30 = +30%)", value=0.30, step=0.05, format="%.2f")
        target_cpa = st.number_input("CPA (FTD) alvo (R$)", value=350.0, step=25.0)

    with c2:
        st.subheader("Resultados")
        res = influencer_calcs(
            fee=fee,
            reels_qty=reels_qty, reels_avg_views=reels_avg_views, reels_ctr=reels_ctr,
            stories_qty=stories_qty, stories_avg_views=stories_avg_views, stories_ctr=stories_ctr,
            tiktok_qty=tiktok_qty, tiktok_avg_views=tiktok_avg_views, tiktok_ctr=tiktok_ctr,
            manual_clicks=manual_clicks,
            manual_ftd=manual_ftd,
            cvr_ftd=cvr_ftd,
            value_per_ftd=value_per_ftd,
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Views totais (proxy impressões)", fmt_int(res["total_views"]))
        k2.metric("Cliques (estimado/real)", fmt_int(res["clicks"]))
        k3.metric("FTD (proj./real)", fmt_float(res["ftd"], 1))
        k4.metric("Receita (FTD * valor)", fmt_money(res["revenue"]))

        k5, k6, k7, k8, k9 = st.columns(5)
        k5.metric("CPM", fmt_money(res["cpm"]))
        k6.metric("CPC", fmt_money(res["cpc"]))
        k7.metric("CPA (FTD)", fmt_money(res["cpa_ftd"]))
        k8.metric("ROAS", fmt_float(res["roas"], 2))
        k9.metric("ROI", fmt_float(res["roi"], 2))

        st.markdown("### Fee máximo para bater metas")
        max_fee_roi = fee_max_by_roi(res["revenue"], target_roi) if res["revenue"] is not None else None
        max_fee_cpa = fee_max_by_cpa(target_cpa, res["ftd"]) if res["ftd"] is not None else None

        a, b = st.columns(2)
        a.metric("Fee máx p/ ROI alvo", fmt_money(max_fee_roi))
        b.metric("Fee máx p/ CPA alvo", fmt_money(max_fee_cpa))

        verdicts = []
        if res["roi"] is not None:
            verdicts.append(res["roi"] >= target_roi)
        if res["cpa_ftd"] is not None:
            verdicts.append(res["cpa_ftd"] <= target_cpa)

        if verdicts and all(verdicts):
            st.success("✅ Cenário saudável (bate ROI e CPA).")
        elif verdicts and any(verdicts):
            st.warning("⚠️ Cenário misto (bate uma meta e falha outra).")
        else:
            st.error("❌ Cenário ruim (não bate metas) — renegociar fee/entregas ou revisar premissas.")

# -------------------
# Twitch
# -------------------
with tabs[1]:
    st.subheader("Twitch — Avg Viewers / Peak (30d) + Projeções")
    tc = None
    if client_id and client_secret:
        try:
            tc = TwitchClient(client_id, client_secret)
        except Exception:
            tc = None
    else:
        st.warning("Sem credenciais no .env: VOD summary e status LIVE ficarão indisponíveis.")

    left, right = st.columns([1, 2])

    with left:
        default_list = load_streamers_file("streamers.txt")
        channel = st.text_input("Canal (login)", value=(default_list[0] if default_list else "shroud")).lower().strip()

        planned_hours = st.number_input("Horas contratadas (mês)", min_value=0.0, value=20.0, step=1.0)
        churn_factor = st.number_input("Fator de churn (estimativa p/ views únicas)", min_value=0.5, value=2.5, step=0.1)

        st.markdown("### Bootstrap (se ainda não tem histórico)")
        use_manual = st.checkbox("Usar valores manuais (até o coletor formar base)", value=False)
        manual_avg = st.number_input("Avg viewers manual", min_value=0.0, value=0.0, step=50.0) if use_manual else None
        manual_peak = st.number_input("Peak manual", min_value=0, value=0, step=100) if use_manual else None

        vod_n = st.number_input("VODs (últimos N) para média", min_value=1, max_value=100, value=20, step=1)
        refresh_vods = st.button("Atualizar VOD summary")

    with right:
        if not channel:
            st.info("Digite um login de canal.")
        else:
            stats = storage.get_stream_stats_30d(conn, channel)
            avg_30d = stats["avg_viewers_30d"]
            peak_30d = stats["peak_viewers_30d"]

            is_live_now = None
            live_viewers_now = None
            if tc:
                try:
                    live_map = tc.get_streams_by_logins([channel])
                    s = live_map.get(channel)
                    if s:
                        is_live_now = True
                        live_viewers_now = int(s.get("viewer_count", 0))
                    else:
                        is_live_now = False
                except Exception:
                    is_live_now = None

            vod_cached = storage.get_cached_vod_summary(conn, channel, max_age_hours=12)

            if refresh_vods:
                if not tc:
                    st.error("Sem credenciais válidas para atualizar VOD summary.")
                else:
                    try:
                        users = tc.get_users_by_logins([channel])
                        u = users.get(channel)
                        if not u:
                            st.error("Canal não encontrado na Twitch API.")
                        else:
                            vods = tc.get_vods_by_user_id(u["id"], first=int(vod_n))
                            vs = vod_summary(vods)
                            if vs["vod_count"] > 0 and vs["avg_vod_views"] is not None and vs["views_per_hour"] is not None:
                                storage.upsert_vod_summary(
                                    conn,
                                    channel,
                                    vs["vod_count"],
                                    float(vs["avg_vod_views"]),
                                    float(vs["median_vod_views"] or 0.0),
                                    float(vs["views_per_hour"]),
                                )
                                vod_cached = storage.get_cached_vod_summary(conn, channel, max_age_hours=999999)
                            else:
                                st.warning("Não foi possível calcular VOD summary (sem VODs suficientes).")
                    except Exception as e:
                        st.error(f"Erro ao atualizar VOD summary: {e}")

            avg_used = manual_avg if use_manual else avg_30d
            peak_used = manual_peak if use_manual else peak_30d

            top = st.columns(6)
            top[0].metric("Status agora", "LIVE" if is_live_now else ("OFF" if is_live_now is False else "-"))
            top[1].metric("Viewers agora", fmt_int(live_viewers_now))
            top[2].metric("Avg viewers (30d)", fmt_int(avg_30d))
            top[3].metric("Peak (30d)", fmt_int(peak_30d))
            top[4].metric("Amostras LIVE (30d)", fmt_int(stats["live_samples_30d"]))
            top[5].metric("Última amostra", stats["last_any_sample_utc"] or "-")

            st.markdown("---")
            st.subheader("Projeções (com base no histórico local)")

            vod_vph = vod_cached["views_per_hour"] if vod_cached else None
            proj = project_twitch(
                planned_hours=planned_hours,
                avg_viewers_30d=avg_used,
                peak_30d=int(peak_used) if peak_used is not None else None,
                churn_factor=churn_factor,
                vod_views_per_hour=vod_vph,
            )

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Avg viewers projetado", fmt_int(proj["projected_avg_viewers"]))
            p2.metric("Peak projetado", fmt_int(proj["projected_peak"]))
            p3.metric("Hours watched (proj.)", fmt_int(proj["projected_hours_watched"]))
            p4.metric("Views únicas (proj.)", fmt_int(proj["projected_unique_views"]))

            st.caption("Obs.: ‘views únicas’ é uma estimativa usando churn_factor. Ajuste conforme sua realidade.")

            st.markdown("### VOD summary (Twitch API)")
            if vod_cached:
                v1, v2, v3, v4 = st.columns(4)
                v1.metric("VODs (cache)", fmt_int(vod_cached["vod_count"]))
                v2.metric("Avg views por VOD", fmt_int(vod_cached["avg_vod_views"]))
                v3.metric("Views por hora (VOD)", fmt_int(vod_cached["views_per_hour"]))
                v4.metric("Cache atualizado", vod_cached["updated_at_utc"])
                if proj["projected_vod_views"] is not None:
                    st.metric("VOD views (estimado p/ horas contratadas)", fmt_int(proj["projected_vod_views"]))
            else:
                st.info("Sem VOD summary em cache. Clique em 'Atualizar VOD summary' (com credenciais no .env).")

# -------------------
# Como rodar
# -------------------
with tabs[2]:
    st.subheader("Rodar no VS Code (local)")

    st.markdown(
        '''
### 1) Instalar deps
```bash
python -m venv .venv
source .venv/bin/activate   # mac/linux
pip install -r requirements.txt
```

### 2) Configurar .env
Copie `.env.example` -> `.env` e preencha TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET.

### 3) Rodar coletor (Terminal A)
```bash
python src/collector.py --channels-file streamers.txt --interval 120
```

### 4) Rodar app (Terminal B)
```bash
streamlit run app.py
```
        '''
    )
