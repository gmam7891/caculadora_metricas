import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
import statistics
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from twitch_client import TwitchClient
from storage import connect, init_db, get_stream_stats_30d, upsert_vod_summary, get_cached_vod_summary
from influencer_metrics import influencer_calcs, fee_max_by_roi, fee_max_by_cpa
from projections import project_twitch

load_dotenv()


# ==================== FUNÇÕES DE FORMATAÇÃO ====================
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
    if mh:
        h = int(mh.group(1))
    if mm:
        m = int(mm.group(1))
    if ms:
        sec = int(ms.group(1))
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


# ==================== CONFIGURAÇÃO DO APP ====================
st.set_page_config(page_title="Valuation Instagram & Twitch", layout="wide")
st.image("logo_gmcr.png", width=180)
st.title("Valuation Instagram & Twitch")

client_id = os.getenv("TWITCH_CLIENT_ID", "")
client_secret = os.getenv("TWITCH_CLIENT_SECRET", "")
db_path = os.getenv("APP_DB_PATH", "./data/app.db")

conn = connect(db_path)
init_db(conn)

tabs = st.tabs(["Instagram", "Twitch (Avg/Peak + Projeções)"])

# ==================== ABA INSTAGRAM ====================
with tabs[0]:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("Instagram + TikTok")
        fee_instagram = st.number_input("Fee / investimento (R$)", min_value=0, value=0, step=1000, key="fee_instagram")
        st.markdown("### Reels")
        reels_qty = st.number_input("Qtd Reels", min_value=0, value=0, step=1, key="reels_qty")
        reels_avg_views = st.number_input("Views médias por Reel", min_value=0, value=0, step=1000, key="reels_views")
        reels_ctr_percent = st.number_input("CTR Reels (%)", min_value=0, value=0, step=1, key="reels_ctr")
        st.markdown("### Stories")
        stories_qty = st.number_input("Qtd Stories", min_value=0, value=0, step=1, key="stories_qty")
        stories_avg_views = st.number_input("Views médias por Story", min_value=0, value=0, step=1000, key="stories_views")
        stories_ctr_percent = st.number_input("CTR Stories (%)", min_value=0, value=0, step=1, key="stories_ctr")
        st.markdown("### TikTok")
        tiktok_qty = st.number_input("Qtd TikToks", min_value=0, value=0, step=1, key="tiktok_qty")
        tiktok_avg_views = st.number_input("Views médias por TikTok", min_value=0, value=0, step=1000, key="tiktok_views")
        tiktok_ctr_percent = st.number_input("CTR TikTok (%)", min_value=0, value=0, step=1, key="tiktok_ctr")
        st.markdown("### Funil (FTD)")
        manual_clicks = st.number_input("Cliques reais (total) — deixe 0 para usar CTR", min_value=0, value=0, step=50, key="manual_clicks")
        manual_ftd = st.number_input("FTD real (total) — deixe 0 para usar projeção", min_value=0, value=0, step=1, key="manual_ftd")
        cvr_percent = st.number_input("CVR para FTD (%)", min_value=0, value=0, step=1, key="cvr_percent")
        value_per_ftd = st.number_input("Valor por FTD (R$)", min_value=0, value=0, step=50, key="value_per_ftd")

        st.markdown("### Metas")
        roi_percent = st.number_input("ROI alvo (%)", min_value=0, value=0, step=5, key="roi_percent")
        target_cpa = st.number_input("CPA alvo (R$)", min_value=0, value=0, step=25, key="target_cpa")

    with c2:
        st.subheader("Resultados")
        reels_ctr = reels_ctr_percent / 100.0
        stories_ctr = stories_ctr_percent / 100.0
        tiktok_ctr = tiktok_ctr_percent / 100.0
        cvr_ftd = cvr_percent / 100.0
        target_roi = roi_percent / 100.0

        res = influencer_calcs(
            fee=fee_instagram,
            reels_qty=reels_qty, reels_avg_views=reels_avg_views, reels_ctr=reels_ctr,
            stories_qty=stories_qty, stories_avg_views=stories_avg_views, stories_ctr=stories_ctr,
            tiktok_qty=tiktok_qty, tiktok_avg_views=tiktok_avg_views, tiktok_ctr=tiktok_ctr,
            manual_clicks=manual_clicks if manual_clicks > 0 else None,
            manual_ftd=manual_ftd if manual_ftd > 0 else None,
            cvr_ftd=cvr_ftd,
            value_per_ftd=value_per_ftd,
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Views totais", fmt_int(res["total_views"]))
        k2.metric("Cliques", fmt_int(res["clicks"]))
        k3.metric("FTD", fmt_int(res["ftd"]))
        k4.metric("Receita", fmt_money(res["revenue"]))

        k5, k6, k7, k8, k9 = st.columns(5)
        k5.metric("CPM", fmt_money(res["cpm"]))
        k6.metric("CPC", fmt_money(res["cpc"]))
        k7.metric("CPA", fmt_money(res["cpa_ftd"]))
        k8.metric("ROAS", fmt_int(res["roas"]))
        k9.metric("ROI", f"{res['roi']*100:.0f}%")

        st.markdown("### Fee máximo para bater metas")
        max_fee_roi = fee_max_by_roi(res["revenue"], target_roi) if res["revenue"] else 0
        max_fee_cpa = fee_max_by_cpa(target_cpa, res["ftd"]) if res["ftd"] else 0

        a, b = st.columns(2)
        a.metric("Fee máx p/ ROI alvo", fmt_money(max_fee_roi))
        b.metric("Fee máx p/ CPA alvo", fmt_money(max_fee_cpa))

        if res["roi"] >= target_roi and (res["cpa_ftd"] is None or res["cpa_ftd"] <= target_cpa):
            st.success("✅ LUCRATIVO")
        elif res["roi"] >= 0:
            st.warning("⚠️ Margem positiva")
        else:
            st.error("❌ PREJUÍZO")

# ==================== ABA TWITCH ====================
with tabs[1]:
    st.subheader("Twitch — Virtual Casino")
    tc = None
    if client_id and client_secret:
        try:
            tc = TwitchClient(client_id, client_secret)
        except Exception:
            tc = None

    left, right = st.columns([1, 2])
    with left:
        channel = st.text_input("Canal (login)", value="", placeholder="Digite o login aqui").lower().strip()
        fee = st.number_input("Fee / investimento (R$)", min_value=0, value=0, step=1000)
        planned_hours = st.number_input("Horas contratadas (mês)", min_value=0, value=0, step=1)
        churn_factor = st.number_input("Fator de churn (views únicas)", min_value=0, value=0, step=1)
        vod_n = st.number_input("VODs para média (últimos N)", min_value=0, value=0, step=1)

    with right:
        if not channel:
            st.info("Digite o login do canal acima.")
        else:
            stats = get_stream_stats_30d(conn, channel)
            avg_30d = stats["avg_viewers_30d"]
            peak_30d = stats["peak_viewers_30d"]

            is_live_now = False
            live_viewers_now = None
            is_casino = False
            if tc:
                try:
                    live_map = tc.get_streams_by_logins([channel])
                    s = live_map.get(channel)
                    if s:
                        is_live_now = True
                        live_viewers_now = int(s.get("viewer_count", 0))
                        is_casino = str(s.get("game_id")) == "29452"
                except Exception:
                    pass

            vod_cached = get_cached_vod_summary(conn, channel, max_age_hours=12)

            top = st.columns(6)
            top[0].metric("Status agora", "✅ LIVE" if is_live_now else "⭕ OFF")
            top[1].metric("Viewers agora", fmt_int(live_viewers_now))
            top[2].metric("Avg viewers (30d)", fmt_int(avg_30d))
            top[3].metric("Peak (30d)", fmt_int(peak_30d))

            if not is_casino and is_live_now:
                st.error("❌ Canal não está em Virtual Casino.")

            st.markdown("---")
            st.subheader("💰 Valuation Financeiro (Fee Independente)")

            roi_percent_tw = st.number_input("ROI alvo (%)", min_value=0, value=0, step=5, key="roi_tw")
            target_roi_tw = roi_percent_tw / 100.0

            target_cpa_tw = st.number_input("CPA alvo (R$)", min_value=0, value=0, step=25, key="cpa_tw")

            ctr_percent_tw = st.number_input("CTR Twitch (%)", min_value=0, value=0, step=1, key="ctr_tw")
            cvr_percent_tw = st.number_input("CVR para FTD (%)", min_value=0, value=0, step=1, key="cvr_tw")
            value_per_ftd_tw = st.number_input("Valor por FTD (R$)", min_value=0, value=0, step=50, key="vftd_tw")

            twitch_ctr = ctr_percent_tw / 100.0
            twitch_cvr = cvr_percent_tw / 100.0

            proj = project_twitch(
                planned_hours=planned_hours,
                avg_viewers_30d=avg_30d,
                peak_30d=peak_30d,
                churn_factor=churn_factor,
                vod_views_per_hour=vod_cached["views_per_hour"] if vod_cached else None,
            )

            unique_views = proj.get("projected_unique_views", 0) or 0
            clicks = unique_views * twitch_ctr
            ftd = clicks * twitch_cvr
            revenue = ftd * value_per_ftd_tw
            roi = ((revenue - fee) / fee) if fee > 0 else 0
            cpa = (fee / ftd) if ftd > 0 else None

            tc1, tc2, tc3, tc4 = st.columns(4)
            tc1.metric("Cliques estimados", fmt_int(clicks))
            tc2.metric("FTD projetado", fmt_int(ftd))
            tc3.metric("Receita projetada", fmt_money(revenue))
            tc4.metric("ROAS", fmt_int(revenue / fee if fee > 0 else 0))

            td1, td2, td3, td4 = st.columns(4)
            td1.metric("CPA (FTD)", fmt_money(cpa))
            td2.metric("ROI", f"{roi*100:.0f}%")
            td3.metric("Lucro/Prejuízo", fmt_money(revenue - fee))
            td4.metric("Fee máximo", fmt_money(fee_max_by_roi(revenue, target_roi_tw)))

            if fee > 0:
                if roi >= target_roi_tw and (cpa is None or cpa <= target_cpa_tw):
                    st.success("✅ LUCRATIVO")
                elif roi >= 0:
                    st.warning("⚠️ Margem positiva")
                else:
                    st.error("❌ PREJUÍZO")

