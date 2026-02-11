from typing import Optional, Dict

def project_twitch(
    planned_hours: float,
    avg_viewers_30d: Optional[float],
    peak_30d: Optional[int],
    churn_factor: float = 2.5,
    vod_views_per_hour: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    if avg_viewers_30d is None:
        return {
            "projected_avg_viewers": None,
            "projected_peak": float(peak_30d) if peak_30d is not None else None,
            "projected_hours_watched": None,
            "projected_unique_views": None,
            "projected_vod_views": None,
        }

    projected_hours_watched = avg_viewers_30d * planned_hours
    projected_unique_views = avg_viewers_30d * planned_hours * churn_factor
    projected_vod_views = (vod_views_per_hour * planned_hours) if (vod_views_per_hour is not None) else None

    return {
        "projected_avg_viewers": avg_viewers_30d,
        "projected_peak": float(peak_30d) if peak_30d is not None else None,
        "projected_hours_watched": projected_hours_watched,
        "projected_unique_views": projected_unique_views,
        "projected_vod_views": projected_vod_views,
    }
