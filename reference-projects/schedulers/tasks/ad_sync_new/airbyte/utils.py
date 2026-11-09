"""Ported from airbyte source-facebook-marketing/utils.py.

Only DateInterval is needed by async_job.py — kept verbatim.
The validate_start_date / validate_end_date helpers depend on AirbyteDateTime
and are not needed by the leaf jobs, so they are dropped.
"""

from datetime import date


class DateInterval:
    """Simple date interval"""

    def __init__(self, start: date, end: date):
        self.start = start
        self.end = end

    def to_date_string(self, date_obj: date) -> str:
        """Convert date to string format expected by Facebook API"""
        return date_obj.strftime("%Y-%m-%d")

    def __str__(self):
        return f"DateInterval({self.start} to {self.end})"
