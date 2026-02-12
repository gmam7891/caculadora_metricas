import os
import re
import random
import statistics
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from src.twitch_client import TwitchClient
from src import storage
from src.influencer_metrics import influencer_calcs, fee_max_by_roi, fee_max_by_cpa
from src.projections import project_twitch


# -----------------------
# Config helpers
# -----------------------
load_dotenv()

def get_cfg(key: str, default: str = "") -> str:
    v = os.getenv(key)
    if v:
        return v
    try:
        return str(st.secrets[key])
    except Exception:
        return default

client_id = get_cfg("TWITCH_CLIENT_ID", "")
client_secret = get_cfg("TWITCH_CLIENT_SECRET", "")
db_path = get_cfg("APP_DB_PATH", "./data/app.db")

def has_creds() -> bool:
    return bool(client_id) and bool(client_secret)


# -----------------------
# UI helpers
# -----------------------
def fmt_money(v, prefix="R$ "):
    if v is None:
        return "-"
    return f"{prefix}{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")

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

def normalize_twitch_login(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    # aceita URL
    s = re.sub(r"^https?://(www\.)?twitch\.tv/", "", s)
    s = s.split("?")[0].strip("/")
    # remove @
    s = s.replace("@", "")
    return s

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


# -----------------------
# Page config
# -----------------------
st.set_page_config(page_title="Calculadora Métricas", layout="wide")

conn = storage.connect(db_path)
storage.init_db(conn)

# -----------------------
# Sidebar nav
# -----------------------
st.sidebar.title("📌 Calculadora")
page = st.sidebar.radio("Navegação", ["Influenciador", "Twitch", "Ajuda"], index=0)

st.sidebar.markdown("---")
st.sidebar.caption("Dica: seus Twitch secrets ficam em **Manage app → Settings → Secrets** (Cloud).")

# Top header
st.title("📊 Calculadora de Métricas (Influenciador + Twitch)")
if not has_creds():
    st.warning("Sem credenciais Twitch (Secrets/env). VOD summary e status LIVE podem ficar indisponíveis.")


# =======================
# PAGE: INFLUENCIADOR
# =======================
if page == "Influenciador":
    st.subheader("Influenciador — CPM / CPC / CPA(FTD) / ROI / FTD")

    # Sidebar inputs (clean)
    st.sidebar.header("⚙️ Inputs (Influenciador)")

    fee = st.sidebar.number_input(
        "Fee / investimento (R$)",
        min_value=0.0, value=50000.0, step=1000.0, format="%.0f"
    )

    st.sidebar.markdown("### Entregas")
    reels_qty = st.sidebar.number_input("Qtd Reels", min_value=0, value=2, step=1)
    stories_qty = st.sidebar.number_input("Qtd Stories (frames/combos)", min_value=0, value=6, step=1)
    tiktok_qty = st.sidebar.number_input("Qtd TikToks", min_value=0, value=1, step=1)

    st.sidebar.markdown("### Audiência média (views)")
    reels_avg_views = st.sidebar.number_input("Views médias por Reel", min_value=0.0, value=150000.0, step=1000.0, format="%.0f")
    stories_avg_views = st.sidebar.number_input("Views médias por Story", min_value=0.0, value=40000.0, step=1000.0, format="%.0f")
    tiktok_avg_views = st.sidebar.number_input("Views médias por TikTok", min_value=0.0, value=200000.0, step=1000.0, format="%.0f")

    st.sidebar.markdown("### CTR (%)")
    # format %g remove ",00" e não força casas
    reels_ctr_pct = st.sidebar.number_input("CTR Reels (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1, format="%g")
    stories_ctr_pct = st.sidebar.number_input("CTR Stories (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1, format="%g")
    tiktok_ctr_pct = st.sidebar.number_input("CTR TikTok (%)", min_value=0.0, max_value=100.0, value=1.0, step=0.1, format="%g")

    reels_ctr = reels_ctr_pct / 100.0
    stories_ctr = stories_ctr_pct / 100.0
    tiktok_ctr = tiktok_ctr_pct / 100.0

    st.sidebar.markdown("### Funil (FTD)")
    manual_clicks_toggle = st.sidebar.checkbox("Tenho cliques reais", value=False)
    manual_clicks = None
    if manual_clicks_toggle:
        manual_clicks = st.sidebar.number_input("Cliques reais (total)", min_value=0.0, value=1200.0, step=50.0, format="%.0f")

    manual_ftd_toggle = st.sidebar.checkbox("Tenho FTD real", value=False)
    manual_ftd = None
    if manual_ftd_toggle:
        manual_ftd = st.sidebar.number_input("FTD real (total)", min_value=0.0, value=0.0, step=1.0, format="%.0f")

    cvr_ftd_pct = st.sidebar.number_input("CVR para FTD (%)", min_value=0.0, max_value=100.0, value=2.0, step=0.1, format="%g")
    cvr_ftd = cvr_ftd_pct / 100.0

    value_per_ftd = st.sidebar.number_input("Valor por FTD (R$)", min_value=0.0, value=600.0, step=50.0, format="%.0f")

    st.sidebar.markdown("### Metas")
    target_roi_pct = st.sidebar.number_input("ROI alvo (%)", min_value=-100.0, max_value=1000.0, value=30.0, step=1.0, format="%g")
    target_roi = target_roi_pct / 100.0

    target_cpa = st.sidebar.number_input("CPA (FTD) alvo (R$)", value=350.0, step=25.0, format="%.0f")

    # Results
    res = influencer_calcs(
        fee=fee,
        reels_qty=int(reels_qty), reels_avg_views=float(reels_avg_views), reels_ctr=float(reels_ctr),
        stories_qty=int(stories_qty), stories_avg_views=float(stories_avg_views), stories_ctr=float(stories_ctr),
        tiktok_qty=int(tiktok_qty), tiktok_avg_views=float(tiktok_avg_views), tiktok_ctr=float(tiktok_ctr),
        manual_clicks=manual_clicks,
        manual_ftd=manual_ftd,
        cvr_ftd=float(cvr_ftd),
        value_per_ftd=float(value_per_ftd),
    )

    # Layout: cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Views totais (proxy)", fmt_int(res["total_views"]))
    c2.metric("Cliques (estimado/real)", fmt_int(res["clicks"]))
    c3.metric("FTD (proj./real)", fmt_float(res["ftd"], 1))
    c4.metric("Receita (FTD × valor)", fmt_money(res["revenue"]))

    c5, c6, c7, c8, c9 = st.columns(5)
    c5.metric("CPM", fmt_money(res["cpm"]))
    c6.metric("CPC", fmt_money(res["cpc"]))
    c7.metric("CPA (FTD)", fmt_money(res["cpa_ftd"]))
    c8.metric("ROAS", fmt_float(res["roas"], 2))
    c9.metric("ROI", fmt_float(res["roi"], 2))

    st.markdown("---")
    st.subheader("Fee máximo para bater metas")

    max_fee_roi = fee_max_by_roi(res["revenue"], target_roi) if res["revenue"] is not None else None
    max_fee_cpa = fee_max_by_cpa(target_cpa, res["ftd"]) if res["ftd"] is not None else None

    m1, m2, m3 = st.columns([1, 1, 2])
    m1.metric("Fee máx (ROI alvo)", fmt_money(max_fee_roi))
    m2.metric("Fee máx (CPA alvo)", fmt_money(max_fee_cpa))

    verdicts = []
    if res["roi"] is not None:
        verdicts.append(res["roi"] >= target_roi)
    if res["cpa_ftd"] is not None:
        verdicts.append(res["cpa_ftd"] <= target_cpa)

    if verdicts and all(verdicts):
        m3.success("✅ Cenário saudável (bate ROI e CPA).")
    elif verdicts and any(verdicts):
        m3.warning("⚠️ Cenário misto (bate uma meta e falha outra).")
    else:
        m3.error("❌ Cenário ruim (não bate metas) — renegociar fee/entregas ou revisar premissas.")

    with st.expander("Ver premissas e fórmulas (resumo)", expanded=False):
        st.write(
            {
                "Views totais": "Reels(qtd×avg) + Stories(qtd×avg) + TikTok(qtd×avg)",
                "Cliques": "Se informado: cliques reais. Senão: views×CTR por formato",
                "FTD": "Se informado: FTD real. Senão: cliques×CVR",
                "Receita": "FTD×valor_por_FTD",
                "CPM": "fee / views_totais × 1000",
                "CPC": "fee / cliques",
                "CPA": "fee / FTD",
                "ROI": "(receita - fee) / fee",
            }
        )


# =======================
# PAGE: TWITCH
# =======================
elif page == "Twitch":
    st.subheader("Twitch — Avg / Peak + Projeções")

    # Twitch client
    tc = None
    if has_creds():
        try:
            tc = TwitchClient(client_id, client_secret)
        except Exception:
            tc = None

    # Sidebar inputs
    st.sidebar.header("⚙️ Inputs (Twitch)")

    default_list = load_streamers_file("streamers.txt")
    if "channel" not in st.session_state:
        st.session_state.channel = (default_list[0] if default_list else "shroud")

    options = default_list if default_list else ["shroud"]

    colA, colB = st.sidebar.columns([3, 1])
    with colA:
        picked = st.selectbox(
            "Canal (lista)",
            options=options,
            index=options.index(st.session_state.channel) if st.session_state.channel in options else 0
        )
        st.session_state.channel = picked

    with colB:
        if st.button("🎲"):
            st.session_state.channel = random.choice(options)
            st.rerun()

    use_custom = st.sidebar.checkbox("Usar canal fora da lista", value=False)
    if use_custom:
        custom = st.sidebar.text_input("Canal (login ou URL)", value=st.session_state.channel)
        st.session_state.channel = normalize_twitch_login(custom)

    channel = normalize_twitch_login(st.session_state.channel)

    planned_hours = st.sidebar.number_input("Horas contratadas (mês)", min_value=0.0, value=20.0, step=1.0, format="%g")
    churn_factor = st.sidebar.number_input("Fator churn (views únicas)", min_value=0.5, value=2.5, step=0.1, format="%g")

    st.sidebar.markdown("### Bootstrap (se não tem histórico)")
    use_manual = st.sidebar.checkbox("Usar avg/peak manuais", value=False)
    manual_avg = st.sidebar.number_input("Avg viewers manual", min_value=0.0, value=0.0, step=1.0, format="%g") if use_manual else None
    manual_peak = st.sidebar.number_input("Peak manual", min_value=0.0, value=0.0, step=1.0, format="%g") if use_manual else None

    vod_n = st.sidebar.number_input("VODs (últimos N) para média", min_value=1, max_value=100, value=20, step=1)
    refresh_vods = st.sidebar.button("Atualizar VOD summary")

    # Quick links
    sg_url = f"https://sullygnome.com/channel/{channel}"
    tt_url = f"https://twitchtracker.com/{channel}"
    l1, l2 = st.columns(2)
    with l1:
        st.link_button("📊 Abrir SullyGnome", sg_url)
    with l2:
        st.link_button("📈 Abrir TwitchTracker", tt_url)

    st.markdown("---")

    if not channel:
        st.info("Selecione um canal.")
        st.stop()

    stats = storage.get_stream_stats_30d(conn, channel)
    avg_30d = stats["avg_viewers_30d"]
    peak_30d = stats["peak_viewers_30d"]

    avg_used = manual_avg if use_manual else avg_30d
    peak_used = manual_peak if use_manual else peak_30d

    # Live now
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

    # VOD cache
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

    # Top metrics
    top = st.columns(6)
    top[0].metric("Status agora", "LIVE" if is_live_now else ("OFF" if is_live_now is False else "-"))
    top[1].metric("Viewers agora", fmt_int(live_viewers_now))
    top[2].metric("Avg viewers (30d)", fmt_int(avg_30d))
    top[3].metric("Peak (30d)", fmt_int(peak_30d))
    top[4].metric("Amostras LIVE (30d)", fmt_int(stats["live_samples_30d"]))
    top[5].metric("Última amostra", stats["last_any_sample_utc"] or "-")

    st.markdown("---")
    st.subheader("Projeções")

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

    st.caption("‘Views únicas’ é estimativa usando churn factor. Ajuste conforme sua realidade.")

    st.markdown("### VOD summary (cache)")
    if vod_cached:
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("VODs (cache)", fmt_int(vod_cached["vod_count"]))
        v2.metric("Avg views por VOD", fmt_int(vod_cached["avg_vod_views"]))
        v3.metric("Views por hora (VOD)", fmt_int(vod_cached["views_per_hour"]))
        v4.metric("Cache atualizado", vod_cached["updated_at_utc"])
        if proj["projected_vod_views"] is not None:
            st.metric("VOD views (estimado p/ horas)", fmt_int(proj["projected_vod_views"]))
    else:
        st.info("Sem VOD summary em cache. Clique em 'Atualizar VOD summary' (com credenciais).")

    with st.expander("Diagnóstico (não expõe segredo)", expanded=False):
        st.write("Client ID carregado:", bool(client_id), "| tamanho:", len(client_id))
        st.write("Client Secret carregado:", bool(client_secret), "| tamanho:", len(client_secret))
        try:
            st.write("Secrets keys:", list(st.secrets.keys()))
        except Exception as e:
            st.write("Erro lendo st.secrets:", str(e))
        st.write("Canal normalizado:", channel)



