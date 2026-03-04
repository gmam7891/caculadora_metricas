from typing import Dict, Optional

def project_twitch(
    planned_hours: float,
    avg_viewers_30d: Optional[float],
    peak_30d: Optional[int],
    churn_factor: float = 2.5,
    vod_views_per_hour: Optional[float] = None,
) -> Dict:
    projected_avg = avg_viewers_30d or 0
    projected_peak = peak_30d or int(projected_avg * 1.8)

    hours_watched = planned_hours * projected_avg
    unique_views = hours_watched / churn_factor if churn_factor > 0 else 0

    projected_vod_views = None
    if vod_views_per_hour and planned_hours:
        projected_vod_views = vod_views_per_hour * planned_hours

    return {
        "projected_avg_viewers": round(projected_avg),
        "projected_peak": round(projected_peak),
        "projected_hours_watched": round(hours_watched),
        "projected_unique_views": round(unique_views),
        "projected_vod_views": round(projected_vod_views) if projected_vod_views else None,
    }