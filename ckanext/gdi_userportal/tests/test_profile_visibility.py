# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Datasets of a harvest source whose metadata profile is not enabled are hidden.

Host test, with SQLAlchemy and an in-memory SQLite database standing in for CKAN's:

    uv run --no-project --with pyyaml --with sqlalchemy --with pytest python -I -m pytest \
        ckanext/gdi_userportal/tests/test_profile_visibility.py
"""

import json

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ckanext.gdi_userportal import profile_visibility as visibility  # noqa: E402

R8_SOURCE, GDI_SOURCE, PLAIN_SOURCE, OTHER_SOURCE = "src-r8", "src-gdi", "src-plain", "src-other"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE harvest_source (id TEXT, title TEXT, active BOOLEAN, config TEXT)"))
        connection.execute(
            text("CREATE TABLE harvest_object (package_id TEXT, harvest_source_id TEXT, current BOOLEAN, gathered TEXT)")
        )
        for source_id, title, config in (
            (R8_SOURCE, "R8", json.dumps({"metadata_profile": "healthdcat_r8", "rdf_format": "text/turtle"})),
            (GDI_SOURCE, "GDI", json.dumps({"metadata_profile": "gdi_current"})),
            (PLAIN_SOURCE, "Plain", json.dumps({"rdf_format": "text/turtle"})),
            (OTHER_SOURCE, "Not json", "not json"),
        ):
            connection.execute(
                text("INSERT INTO harvest_source VALUES (:id, :title, 1, :config)"),
                {"id": source_id, "title": title, "config": config},
            )
        for package_id, source_id, current, gathered in (
            ("pkg-r8", R8_SOURCE, 1, "2026-02"),
            ("pkg-gdi", GDI_SOURCE, 1, "2026-02"),
            ("pkg-plain", PLAIN_SOURCE, 1, "2026-02"),
            ("pkg-moved", R8_SOURCE, 0, "2026-01"),
            ("pkg-moved", GDI_SOURCE, 1, "2026-02"),
        ):
            connection.execute(
                text("INSERT INTO harvest_object VALUES (:p, :s, :c, :g)"),
                {"p": package_id, "s": source_id, "c": current, "g": gathered},
            )
    with Session(engine) as db:
        yield db


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, []),
        ("", []),
        ("gdi_current", ["gdi_current"]),
        ("healthdcat_r8 gdi_current", ["healthdcat_r8", "gdi_current"]),
        ("healthdcat_r8,gdi_current", ["healthdcat_r8", "gdi_current"]),
        (["a", " b "], ["a", "b"]),
    ],
)
def test_the_enabled_profiles_are_read_from_the_option(raw, expected):
    assert visibility.enabled_profiles(raw) == expected


def test_the_source_of_a_retired_profile_is_hidden(session):
    assert visibility.hidden_source_ids(session, ["gdi_current"]) == [R8_SOURCE]


def test_nothing_is_hidden_when_the_profile_is_enabled(session):
    assert visibility.hidden_source_ids(session, ["gdi_current", "healthdcat_r8"]) == []
    assert visibility.hidden_source_ids(session, ["healthdcat_r8"]) == [GDI_SOURCE]


def test_nothing_is_hidden_when_no_profiles_are_configured(session):
    assert visibility.hidden_source_ids(session, []) == []


def test_a_dataset_of_a_hidden_source_is_hidden(session):
    assert visibility.is_hidden(session, ["gdi_current"], "pkg-r8") is True


@pytest.mark.parametrize("package", ["pkg-gdi", "pkg-plain", "pkg-unknown", "pkg-moved", None, ""])
def test_other_datasets_are_not_hidden(session, package):
    assert visibility.is_hidden(session, ["gdi_current"], package) is False


def test_the_current_harvest_object_decides_which_source_a_dataset_belongs_to(session):
    assert visibility.package_source_id(session, "pkg-moved") == GDI_SOURCE


def test_a_deployment_without_harvest_hides_nothing():
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        assert visibility.hidden_source_ids(db, ["gdi_current"]) == []
        assert visibility.is_hidden(db, ["gdi_current"], "pkg") is False


def test_the_search_leaves_out_the_datasets_of_hidden_sources(session):
    params = visibility.hide_from_search({"q": "*:*", "fq_list": ["x:1"]}, session, ["gdi_current"])

    assert params["fq_list"] == ["x:1", '-harvest_source_id:("src-r8")']


def test_the_search_is_unchanged_when_nothing_is_hidden(session):
    params = visibility.hide_from_search({"q": "*:*"}, session, ["gdi_current", "healthdcat_r8"])

    assert params == {"q": "*:*"}


def test_the_exclusion_lists_every_hidden_source():
    assert visibility.search_exclusion(["a", "b"]) == '-harvest_source_id:("a" OR "b")'
    assert visibility.search_exclusion([]) is None


# --- the profile a source names ----------------------------------------------------------------


def test_the_profile_each_source_names_is_read_from_its_config(session):
    profiles = visibility.source_profiles(session, [R8_SOURCE, GDI_SOURCE, PLAIN_SOURCE, OTHER_SOURCE])

    assert profiles == {R8_SOURCE: "healthdcat_r8", GDI_SOURCE: "gdi_current", PLAIN_SOURCE: None, OTHER_SOURCE: None}


def test_a_source_that_does_not_exist_is_left_out_of_the_answer(session):
    assert visibility.source_profiles(session, [R8_SOURCE, "vanished"]) == {R8_SOURCE: "healthdcat_r8"}


def test_a_source_asked_for_twice_is_answered_once(session):
    assert visibility.source_profiles(session, [GDI_SOURCE, GDI_SOURCE]) == {GDI_SOURCE: "gdi_current"}


@pytest.mark.parametrize("ids", [[], [None], ["", None]])
def test_without_a_source_id_nothing_is_asked_of_the_database(ids):
    assert visibility.source_profiles(object(), ids) == {}


def test_a_deployment_without_the_harvest_tables_has_no_source_profiles():
    with Session(create_engine("sqlite://")) as empty:
        assert visibility.source_profiles(empty, ["anything"]) == {}


@pytest.mark.parametrize("config", [None, "", "[]", '{"metadata_profile": ""}', '{"metadata_profile": 5}', '{"metadata_profile": "  "}'])
def test_a_config_that_names_no_usable_profile_maps_to_none(config):
    assert visibility._named_profile(config) is None  # noqa: SLF001


def test_the_profile_name_is_trimmed():
    assert visibility._named_profile('{"metadata_profile": " healthdcat_r8 "}') == "healthdcat_r8"  # noqa: SLF001
