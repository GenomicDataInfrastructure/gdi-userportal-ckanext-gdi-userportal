#!/usr/bin/env python

# SPDX-FileCopyrightText: 2024 Stichting Health-RI
# SPDX-FileContributor: PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

# -*- coding: utf-8 -*-

"""Shared constants for the temporal_coverage indexing/search feature.

Centralized here so plugin.py (indexing side) and logic/action/get.py
(search side) can't drift apart on field/param names.
"""

TEMPORAL_COVERAGE_RANGE_FIELD = "temporal_coverage_range"
TEMPORAL_COVERAGE_MIN_FIELD = "temporal_coverage_min"
TEMPORAL_COVERAGE_MAX_FIELD = "temporal_coverage_max"

TEMPORAL_MIN_PARAM = "ext_temporal_min"
TEMPORAL_MAX_PARAM = "ext_temporal_max"
