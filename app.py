import os
import re
import statistics
from typing import Dict, Any, List, Optional

import random

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from src.twitch_client import TwitchClient
from src import storage
from src.influencer_metrics import influencer_calcs, fee_max_by_roi, fee_max_by_cpa
from src.projections import project_twitch

from io import BytesIO
from datetime import datetime, timezone
from openpyxl.utils import get_column_letter

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

def df_to_xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Gera um .xlsx em memória com 1+ abas (sheets)."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            safe_name = sheet_name[:31]  # limite Excel
            df.to_excel(writer, index=False, sheet_name=safe_name)
            ws = writer.sheets[safe_name]

            # Ajuste de largura
            for col_idx, col_name in enumerate(df.columns, start=1):
                values = df[col_name].astype(str).values.tolist()
                max_len = max([len(str(col_name))] + [len(v) for v in values])
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 45)

    return output.getvalue()

load_dotenv()

st.set_page_config(page_title="Validação de Influenciadores", layout="wide")
st.title("Validação de Influenciadores")

def get_cfg(key: str, default: str = "") -> str:
    # 1) Variáveis de ambiente (local)
    v = os.getenv(key)
    if v:
        return v

    # 2) Streamlit Secrets (Cloud)
    try:
        return str(st.secrets[key])
    except Exception:
        return default

client_id = get_cfg("d2evugowek4wfnwn8hcki9gpprlxpy", "")
client_secret = get_cfg("ud5ks4z31r7stjtanemv75t1kplnar", "")
db_path = get_cfg("APP_DB_PATH", "./data/app.db")


conn = storage.connect(db_path)
storage.init_db(conn)

tabs = st.tabs(["Instagram & Tik Tok", "Twitch", "YouTube", "LinkedIn"])

# -------------------
# Influenciador
# -------------------
with tabs[0]:
    c1, c2 = st.columns([1, 1])

    with c1:
        st.subheader("Inputs (manual)")
        influencer_name = st.text_input("Nome do influenciador", placeholder="Ex:Fulano")
        fee = st.number_input("Fee / investimento (R$)", min_value=0.0, value=0.0, step=1000.0, format="%.0f")
        
        st.markdown("### Instagram Reels")
        reels_qty = st.number_input("Qtd Reels", min_value=0, value=0, step=1)
        reels_avg_views = st.number_input("Views médias por Reel", min_value=0.0, value=0.0, step=1000.0, format="%.0f")
        reels_ctr_pct = st.number_input("CTR Reels (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.1, format="%.0f")
        reels_ctr = reels_ctr_pct / 100.0
        st.markdown("### Instagram Stories")
        stories_qty = st.number_input("Qtd Stories (frames/combos)", min_value=0, value=0, step=1)
        stories_avg_views = st.number_input("Views médias por Story", min_value=0.0, value=0.0, step=1000.0)
        stories_ctr_pct = st.number_input("CTR Stories (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.1, format="%.0f")
        stories_ctr = stories_ctr_pct / 100.0

        st.markdown("### TikTok")
        tiktok_qty = st.number_input("Qtd TikToks", min_value=0, value=0, step=1)
        tiktok_avg_views = st.number_input("Views médias por TikTok", min_value=0.0, value=0.0, step=1000.0)  
        tiktok_ctr_pct = st.number_input("CTR TikTok (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
        tiktok_ctr = tiktok_ctr_pct / 100.0

        st.markdown("### Funil (FTD)")
        manual_clicks_toggle = st.checkbox("Tenho cliques reais (sobrescrever CTR)", value=False)
        manual_clicks = None
        if manual_clicks_toggle:
            manual_clicks = st.number_input("Cliques reais (total)", min_value=0.0, value=0.0, step=50.0, format="%.0f")

        manual_ftd_toggle = st.checkbox("Tenho FTD real (sobrescrever projeção)", value=False)
        manual_ftd = None
        if manual_ftd_toggle:
            manual_ftd = st.number_input("FTD real (total)", min_value=0.0, value=0.0, step=1.0, format="%.0f")

        cvr_ftd_pct = st.number_input("CVR para FTD (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0, format="%.0f")
        cvr_ftd = cvr_ftd_pct / 100.0
        value_per_ftd = st.number_input("Valor por FTD (R$) — LTV/NGR médio", min_value=0.0, value=0.0, step=50.0, format="%.0f")

        st.markdown("### Metas")
        target_roi_pct = st.number_input("ROI alvo (%)", min_value=-100.0, max_value=1000.0, value=0.0, step=5.0)
        target_roi = target_roi_pct / 100.0
        target_cpa = st.number_input("CPA (FTD) alvo (R$)", value=0.0, step=25.0, format="%.0f")

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

    # ===== Relatório Excel (Influenciador) =====
    influencer_row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    
        # Inputs principais
        "influencer_name": influencer_name,
        "fee": float(fee),
        "reels_qty": int(reels_qty),
        "stories_qty": int(stories_qty),
        "tiktok_qty": int(tiktok_qty),
    
        "reels_avg_views": float(reels_avg_views),
        "stories_avg_views": float(stories_avg_views),
        "tiktok_avg_views": float(tiktok_avg_views),
    
        "reels_ctr_pct": float(reels_ctr_pct),
        "stories_ctr_pct": float(stories_ctr_pct),
        "tiktok_ctr_pct": float(tiktok_ctr_pct),
    
        "manual_clicks": float(manual_clicks) if manual_clicks is not None else None,
        "manual_ftd": float(manual_ftd) if manual_ftd is not None else None,
    
        "cvr_ftd_pct": float(cvr_ftd_pct),
        "value_per_ftd": float(value_per_ftd),
    
        "target_roi_pct": float(target_roi_pct),
        "target_cpa": float(target_cpa),
    
        # Outputs
        "total_views": res.get("total_views"),
        "clicks": res.get("clicks"),
        "ftd": res.get("ftd"),
        "revenue": res.get("revenue"),
    
        "cpm": res.get("cpm"),
        "cpc": res.get("cpc"),
        "cpa_ftd": res.get("cpa_ftd"),
        "roas": res.get("roas"),
        "roi": res.get("roi"),
    
        # Fee máximo (se você já calcula esses)
        "max_fee_roi": max_fee_roi if "max_fee_roi" in locals() else None,
        "max_fee_cpa": max_fee_cpa if "max_fee_cpa" in locals() else None,
    }
    
    xlsx_bytes = df_to_xlsx_bytes({"Influenciador": pd.DataFrame([influencer_row])})
    
    st.download_button(
        "📥 Baixar relatório Excel (Instagram/TikTok)",
        data=xlsx_bytes,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# -------------------
# Twitch (MANUAL)
# -------------------
with tabs[1]:
    st.subheader("Twitch — Projeções (manual)")

    left, right = st.columns([1, 2])

    # ---------- LEFT: inputs ----------
    with left:
        default_list = load_streamers_file("streamers.txt")

        # Canal: select + aleatório + custom (login ou URL)
        if "twitch_channel" not in st.session_state:
            st.session_state.twitch_channel = (default_list[0] if default_list else "shroud")

        colA, colB = st.columns([3, 1])
        with colA:
            if default_list:
                picked = st.selectbox(
                    "Canal (lista)",
                    options=default_list,
                    index=default_list.index(st.session_state.twitch_channel)
                    if st.session_state.twitch_channel in default_list else 0
                )
                st.session_state.twitch_channel = picked
            else:
                st.session_state.twitch_channel = st.text_input("Canal (login)", value=st.session_state.twitch_channel)

        with colB:
            if default_list and st.button("🎲", help="Escolher um canal aleatório da lista"):
                st.session_state.twitch_channel = random.choice(default_list)
                st.rerun()

        use_custom = st.checkbox("Usar canal fora da lista", value=False)
        if use_custom:
            raw = st.text_input("Canal (login ou URL)", value=st.session_state.twitch_channel)
            st.session_state.twitch_channel = raw

        # Normaliza caso a pessoa cole URL
        channel = (st.session_state.twitch_channel or "").lower().strip()
        channel = re.sub(r"^https?://(www\.)?twitch\.tv/", "", channel)
        channel = channel.split("?")[0].strip("/").replace("@", "")

        planned_hours = st.number_input(
            "Horas contratadas (mês)",
            min_value=0.0, value=0.0, step=1.0, format="%.0f"
        )
        churn_factor = st.number_input(
            "Fator de churn (estimativa p/ views únicas)",
            min_value=0.5, value=1.0, step=1.0, format="%.0f"
        )

        st.markdown("### Dados do streamer (manual)")
        # keys por canal, pra não precisar digitar tudo de novo quando trocar
        def k(name: str) -> str:
            return f"tw_{channel}_{name}"

        avg_viewers = st.number_input("Average viewers", min_value=0.0, value=0.0, step=1.0, format="%.0f", key=k("avg"))
        hours_watched = st.number_input("Hours watched (30d)", min_value=0.0, value=0.0, step=1000.0, format="%.0f", key=k("hw"))
        followers_gained = st.number_input("Followers gained (30d)", min_value=0.0, value=0.0, step=10.0, format="%.0f", key=k("fg"))
        peak_viewers = st.number_input("Peak viewers (30d)", min_value=0.0, value=0.0, step=1.0, format="%.0f", key=k("peak"))
        hours_streamed = st.number_input("Hours streamed (30d)", min_value=0.0, value=0.0, step=1.0, format="%.0f", key=k("hs"))
        streams = st.number_input("Streams (30d)", min_value=0.0, value=0.0, step=1.0, format="%.0f", key=k("streams"))

    
    # ---------- RIGHT: dashboard ----------
    with right:
        if not channel:
            st.info("Selecione/cole um canal (login ou URL).")
        else:
            # Mostra os dados manuais (seis campos)
            top = st.columns(6)
            top[0].metric("Average viewers", fmt_int(avg_viewers))
            top[1].metric("Hours watched (30d)", fmt_int(hours_watched))
            top[2].metric("Followers gained (30d)", fmt_int(followers_gained))
            top[3].metric("Peak viewers (30d)", fmt_int(peak_viewers))
            top[4].metric("Hours streamed (30d)", fmt_int(hours_streamed))
            top[5].metric("Streams (30d)", fmt_int(streams))

            st.markdown("---")
            st.subheader("Projeções (com base nos dados manuais)")

            proj = project_twitch(
                planned_hours=float(planned_hours),
                avg_viewers_30d=float(avg_viewers) if avg_viewers is not None else None,
                peak_30d=int(peak_viewers) if peak_viewers is not None else None,
                churn_factor=float(churn_factor),
                vod_views_per_hour=None,
            )

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Avg viewers projetado", fmt_int(proj["projected_avg_viewers"]))
            p2.metric("Peak projetado", fmt_int(proj["projected_peak"]))
            p3.metric("Hours watched (proj.)", fmt_int(proj["projected_hours_watched"]))
            p4.metric("Views únicas (proj.)", fmt_int(proj["projected_unique_views"]))

            st.caption("Obs.: ‘views únicas’ é uma estimativa usando churn_factor.")

            # ===== Relatório Excel (Twitch) =====
        twitch_row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "channel": channel,
        
            # Inputs (imagem 1)
            "planned_hours_month": float(planned_hours),
            "churn_factor": float(churn_factor),
        
            # Dados manuais (se você reestruturou p/ manual)
            "avg_viewers_30d": float(avg_viewers),
            "hours_watched_30d": float(hours_watched),
            "followers_gained_30d": float(followers_gained),
            "peak_viewers_30d": float(peak_viewers),
            "hours_streamed_30d": float(hours_streamed),
            "streams_30d": float(streams),
        
            # Outputs (imagem 2)
            "projected_avg_viewers": proj.get("projected_avg_viewers"),
            "projected_peak": proj.get("projected_peak"),
            "projected_hours_watched": proj.get("projected_hours_watched"),
            "projected_unique_views": proj.get("projected_unique_views"),
        }
        
        xlsx_bytes = df_to_xlsx_bytes({"Twitch": pd.DataFrame([twitch_row])})
        
        st.download_button(
            "📥 Baixar relatório Excel (Twitch)",
            data=xlsx_bytes,
            file_name=f"relatorio_twitch_{channel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )




    
