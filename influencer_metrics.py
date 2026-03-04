from typing import Dict, Optional

def influencer_calcs(
    fee: float,
    reels_qty: int, reels_avg_views: float, reels_ctr: float,
    stories_qty: int, stories_avg_views: float, stories_ctr: float,
    tiktok_qty: int, tiktok_avg_views: float, tiktok_ctr: float,
    manual_clicks: Optional[float] = None,
    manual_ftd: Optional[float] = None,
    cvr_ftd: float = 0.02,
    value_per_ftd: float = 600.0,
) -> Dict:
    total_views = (
        reels_qty * reels_avg_views +
        stories_qty * stories_avg_views +
        tiktok_qty * tiktok_avg_views
    )

    if manual_clicks is not None:
        clicks = manual_clicks
    else:
        clicks = (
            reels_qty * reels_avg_views * reels_ctr +
            stories_qty * stories_avg_views * stories_ctr +
            tiktok_qty * tiktok_avg_views * tiktok_ctr
        )

    if manual_ftd is not None:
        ftd = manual_ftd
    else:
        ftd = clicks * cvr_ftd

    revenue = ftd * value_per_ftd

    cpm = (fee / total_views * 1000) if total_views > 0 else None
    cpc = (fee / clicks) if clicks > 0 else None
    cpa_ftd = (fee / ftd) if ftd > 0 else None
    roas = (revenue / fee) if fee > 0 else 0
    roi = ((revenue - fee) / fee) if fee > 0 else 0

    return {
        "total_views": total_views,
        "clicks": clicks,
        "ftd": ftd,
        "revenue": revenue,
        "cpm": cpm,
        "cpc": cpc,
        "cpa_ftd": cpa_ftd,
        "roas": roas,
        "roi": roi,
    }


def fee_max_by_roi(revenue: float, target_roi: float) -> Optional[float]:
    if revenue is None or revenue <= 0:
        return None
    return revenue / (1 + target_roi)


def fee_max_by_cpa(target_cpa: float, ftd: float) -> Optional[float]:
    if ftd is None or ftd <= 0:
        return None
    return target_cpa * ftd