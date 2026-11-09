"""Thin entry point on top of airbyte's ported async-job machinery.

Given a consumer-style message and a target day, this builds one
InsightAsyncJob (level=ad, single-day time_range) and drives it through
InsightAsyncJobManager. Failures are handled by airbyte's split policy:
account → campaign → adset → ad → bisect-by-fields. Rate limits are handled
inside MyFacebookAdsApi.call (retry_pattern + Utilization-driven sleep).

Returns a list[dict] of FB insights rows (each row from .export_all_data()).
No business transforms, no DB write — purely raw extraction.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from facebook_business.adobjects.adsinsights import AdsInsights

from conf.api_conf import get_proxies

from .api import API
from .async_job import InsightAsyncJob
from .async_job_manager import InsightAsyncJobManager
from .utils import DateInterval


logger = logging.getLogger(__name__)


def build_insight_params(
    fields: List[str],
    timezone_name: str,
    level: str = "ad",
    breakdowns: Optional[List[str]] = None,
    action_attribution_windows: Optional[List[str]] = None,
    action_breakdowns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the params dict for AdAccount.get_insights(is_async=True).

    NOTE: time_range is intentionally NOT set here — InsightAsyncJob writes it
    from its DateInterval. Same convention as airbyte upstream.
    """
    params: Dict[str, Any] = {
        "level": level,
        "fields": fields,
        "time_zone": timezone_name,
        "time_increment": "all_days",
        "action_attribution_windows": action_attribution_windows
        or [AdsInsights.ActionAttributionWindows.value_1d_click],
        "action_breakdowns": action_breakdowns
        or [AdsInsights.ActionBreakdowns.action_type],
    }
    if breakdowns:
        params["breakdowns"] = breakdowns
    return params


def fetch_account_insights(
    message: Dict[str, Any],
    day: str,
    fields: List[str],
    level: str = "ad",
    breakdowns: Optional[List[str]] = None,
    primary_key: Optional[List[str]] = None,
    job_timeout_minutes: int = 60,
    throttle_limit: float = 90.0,
    max_jobs_in_queue: int = 100,
) -> List[Dict[str, Any]]:
    """Pull one day of insights for one account using airbyte's async machinery.

    Args:
        message: ConsumerMsg-shaped dict, must contain
                 account_id / app_id / app_secret / access_token / proxy
        day: "YYYY-MM-DD" in the account's local timezone
        fields: insights fields to request — add as many as needed; on failure
                the leaf job will bisect by fields automatically
        level: account / campaign / adset / ad (default ad)
        breakdowns: e.g. ["age","gender"]; row volume balloons, more likely to
                    trigger split-by-id
        primary_key: PK preserved across the field-bisection split. Default
                     is [<level>_id, "date_start"] (+ breakdown columns).
        job_timeout_minutes: hard timeout per single AdReportRun
        throttle_limit: APILimit's x-fb-ads-insights-throttle ceiling (%); above
                        this, manager stops scheduling new jobs
        max_jobs_in_queue: APILimit's max concurrent in-flight async reports

    Returns:
        list of dict rows produced by row.export_all_data().
    """
    account_id_raw = message["account_id"]
    account_id = account_id_raw[len("act_"):] if account_id_raw.startswith("act_") else account_id_raw

    proxies = get_proxies(message["proxy"])
    api = API(
        app_id=message["app_id"],
        app_secret=message["app_secret"],
        access_token=message["access_token"],
        proxies=proxies,
    )
    account = api.get_account(account_id=account_id)
    tz_name = account.get("timezone_name")
    if not tz_name:
        raise RuntimeError(f"account {account_id_raw} has no timezone_name")

    params = build_insight_params(
        fields=fields,
        timezone_name=tz_name,
        level=level,
        breakdowns=breakdowns,
    )

    if primary_key is None:
        primary_key = [f"{level}_id", "date_start"]
        if breakdowns:
            primary_key = primary_key + list(breakdowns)

    day_dt = datetime.strptime(day, "%Y-%m-%d").date()
    interval = DateInterval(start=day_dt, end=day_dt)

    job = InsightAsyncJob(
        api=api.api,
        edge_object=account,
        interval=interval,
        params=params,
        job_timeout=timedelta(minutes=job_timeout_minutes),
        primary_key=primary_key,
    )

    manager = InsightAsyncJobManager(
        api=api,
        jobs=iter([job]),
        account_id=account_id,
        throttle_limit=throttle_limit,
        max_jobs_in_queue=max_jobs_in_queue,
    )

    rows: List[Dict[str, Any]] = []
    for completed_job in manager.completed_jobs():
        for obj in completed_job.get_result():
            data = obj.export_all_data() if hasattr(obj, "export_all_data") else dict(obj)
            rows.append(dict(data))

    logger.info(
        "fetch_account_insights: account=%s day=%s level=%s → %d rows",
        account_id_raw, day, level, len(rows),
    )
    return rows
