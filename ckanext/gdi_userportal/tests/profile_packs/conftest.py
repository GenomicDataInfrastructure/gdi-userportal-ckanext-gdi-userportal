# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Fixtures for the profile pack tests.

These tests run on the host with only PyYAML and pytest, without CKAN:

    uv run --no-project --with pyyaml --with pytest python -I -m pytest \
        ckanext/gdi_userportal/tests/profile_packs

``python -I`` ignores the working directory, so the generator is loaded by file
path instead of being imported as ``ckanext.gdi_userportal.profile_packs``.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[2]
GENERATOR_PATH = PACKAGE_DIR / "profile_packs" / "generator.py"
STATIC_DATASET_SCHEMA = PACKAGE_DIR / "scheming" / "schemas" / "dataset_multilingual.yaml"


def load_generator():
    spec = importlib.util.spec_from_file_location("profile_pack_generator", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    # Registered so dataclasses can resolve their own module while it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def generator():
    return load_generator()
