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
PACKS_DIR = PACKAGE_DIR / "profile_packs"
GENERATOR_PATH = PACKS_DIR / "generator.py"
STATIC_DATASET_SCHEMA = PACKAGE_DIR / "scheming" / "schemas" / "dataset_multilingual.yaml"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Registered so dataclasses can resolve their own module while it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_generator():
    return load_module("profile_pack_generator", GENERATOR_PATH)


@pytest.fixture(scope="session")
def generator():
    return load_generator()


@pytest.fixture(scope="session")
def conformance():
    return load_module("profile_pack_conformance", PACKS_DIR / "conformance.py")


@pytest.fixture(scope="session")
def conformance_build():
    return load_module("profile_pack_conformance_build", PACKS_DIR / "conformance_build.py")


@pytest.fixture(scope="session")
def r8_rules(generator):
    """The shipped conformance rules of the healthdcat_r8 pack."""
    registry = generator.Registry()
    return registry.conformance(registry.pack("healthdcat_r8"))
