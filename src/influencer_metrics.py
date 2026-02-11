from typing import Optional, Dict

def safe_div(a: float, b: float) -> Optional[float]:
    if b is None or b == 0:
        return None
    return a / b

def influencer_calcs(
    fee: float,
    reels_qty: int, reels_avg_views: float, reels_ctr: float,
    stories_qty: int, stories_avg_views: float, stories_ctr: float,
    tiktok_qty: int, tiktok_avg_views: float, tiktok_ctr: float,
    manual_clicks: Optional[float],
    manual_ftd: Optional[float],
    cvr_ftd: float,
    value_per_ftd: float,
) -> Dict[str, Optional[float]]:
    reels_views = reels_qty * reels_avg_views
    stories_views = stories_qty * stories_avg_views
    tiktok_views = tiktok_qty * tiktok_avg_views
    total_views = reels_views + stories_views + tiktok_views

    est_clicks = (reels_views * reels_ctr) + (stories_views * stories_ctr) + (tiktok_views * tiktok_ctr)
    clicks = manual_clicks if (manual_clicks is not None and manual_clicks >= 0) else est_clicks

    est_ftd = clicks * cvr_ftd
    ftd = manual_ftd if (manual_ftd is not None and manual_ftd >= 0) else est_ftd

    revenue = ftd * value_per_ftd

    cpm = (safe_div(fee, total_views) * 1000) if total_views > 0 else None
    cpc = safe_div(fee, clicks) if clicks > 0 else None
    cpa = safe_div(fee, ftd) if ftd > 0 else None
    roas = safe_div(revenue, fee) if fee > 0 else None
    roi = safe_div((revenue - fee), fee) if fee > 0 else None

    return {
        "total_views": total_views,
        "clicks": clicks,
        "ftd": ftd,
        "revenue": revenue,
        "cpm": cpm,
        "cpc": cpc,
        "cpa_ftd": cpa,
        "roas": roas,
        "roi": roi,
    }

def fee_max_by_roi(revenue: float, target_roi: float) -> Optional[float]:
    denom = 1.0 + target_roi
    if revenue is None or denom <= 0:
        return None
    return revenue / denom

def fee_max_by_cpa(target_cpa: float, ftd: float) -> Optional[float]:
    if target_cpa is None or ftd is None:
        return None
    return target_cpa * ftd
