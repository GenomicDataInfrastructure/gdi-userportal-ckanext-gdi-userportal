# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: MIT

"""
This module tests the scheming related parts of the GDI userportal plugin (validation.py)
"""

from datetime import datetime, timezone

import ckanext.gdi_userportal.validation as validation
import pytest
from zoneinfo import ZoneInfo


@pytest.fixture
def time_nye():
    return datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "time",
    [
        # No timezone defined
        datetime(2020, 1, 1),
        # Time ahead (using canonical IANA timezone 'Europe/Amsterdam' instead of 'CET')
        datetime(2020, 1, 1, 1, 0).replace(tzinfo=ZoneInfo("Europe/Amsterdam")),
        # Time behind
        datetime(2019, 12, 31, 18, 0, 0).replace(tzinfo=ZoneInfo("America/Chicago")),
        # Timezone with half hour offset and microseconds
        datetime(2020, 1, 1, 5, 30, 0, 987654).replace(tzinfo=ZoneInfo("Asia/Kolkata")),
    ],
)
def test_utc_enforcer(time, time_nye):
    result = validation.enforce_utc_time(time)
    assert result == time_nye
    assert result.tzinfo == timezone.utc
