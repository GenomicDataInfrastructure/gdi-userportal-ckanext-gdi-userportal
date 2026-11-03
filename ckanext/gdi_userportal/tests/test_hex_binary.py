# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

import pytest
from ckantoolkit import Invalid, missing

from ckanext.gdi_userportal.validation import gdi_hex_binary


@pytest.mark.parametrize("value, expected", [("abc123", "abc123"), ("ABC123", "abc123"), (" 00ff ", "00ff")])
def test_a_hexadecimal_digest_is_stored_in_lower_case(value, expected):
    assert gdi_hex_binary(value) == expected


@pytest.mark.parametrize("value", [None, "", missing])
def test_nothing_is_left_as_it_is(value):
    assert gdi_hex_binary(value) is value or gdi_hex_binary(value) == value


@pytest.mark.parametrize("value", ["xyz", "abc", "12 34", "0x1234", "g0"])
def test_a_value_that_is_not_an_even_number_of_hexadecimal_digits_is_rejected(value):
    with pytest.raises(Invalid):
        gdi_hex_binary(value)
