# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Finding and removing the extras of retired profiles.

Runs on SQLite with the columns CKAN's ``package``, ``package_extra`` and ``harvest_source``
tables have, so it needs SQLAlchemy and nothing else:

    uv run --no-project --with pyyaml --with sqlalchemy --with pytest python -I -m pytest ...
"""

import json

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from conftest import PACKS_DIR, load_module  # noqa: E402


@pytest.fixture(scope="module")
def prune():
    return load_module("profile_pack_prune", PACKS_DIR / "prune.py")


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE package (id TEXT PRIMARY KEY, name TEXT, type TEXT, state TEXT, private BOOLEAN)"))
        connection.execute(
            text("CREATE TABLE package_extra (id TEXT PRIMARY KEY, key TEXT, value TEXT, state TEXT, package_id TEXT)")
        )
    with Session(engine) as db:
        yield db


def add_package(session, package_id, name, type_="dataset", state="active", private=False, extras=None):
    session.execute(
        text("INSERT INTO package VALUES (:id, :name, :type, :state, :private)"),
        {"id": package_id, "name": name, "type": type_, "state": state, "private": private},
    )
    for key, value in (extras or {}).items():
        session.execute(
            text("INSERT INTO package_extra VALUES (:id, :key, :value, 'active', :package_id)"),
            {"id": f"{package_id}-{key}", "key": key, "value": value, "package_id": package_id},
        )
    session.commit()


def extras_of(session, package_id):
    rows = session.execute(text("SELECT key FROM package_extra WHERE package_id = :p ORDER BY key"), {"p": package_id})
    return [key for (key,) in rows]


RETIRED = {"custodian", "variables"}


# --- finding -------------------------------------------------------------------------


def test_only_datasets_carrying_a_retired_extra_are_found(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x", "variables": "[]", "guid": "g"})
    add_package(session, "2", "b", extras={"guid": "g"})
    add_package(session, "3", "c")

    assert prune.find_orphaned_extras(session, RETIRED) == [
        prune.Orphan("1", "a", "active", False, ("custodian", "variables"))
    ]


def test_extras_that_are_not_retired_are_not_listed(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x", "guid": "g", "related_resource": "r"})

    assert prune.find_orphaned_extras(session, RETIRED)[0].keys == ("custodian",)


def test_other_package_types_are_left_alone(prune, session):
    add_package(session, "1", "series", type_="dataset_series", extras={"custodian": "x"})
    add_package(session, "2", "ds", extras={"custodian": "x"})

    assert [o.name for o in prune.find_orphaned_extras(session, RETIRED)] == ["ds"]


def test_deleted_and_private_datasets_are_found_and_flagged(prune, session):
    add_package(session, "1", "gone", state="deleted", extras={"custodian": "x"})
    add_package(session, "2", "hidden", private=True, extras={"custodian": "x"})

    found = {o.name: o for o in prune.find_orphaned_extras(session, RETIRED)}
    assert found["gone"].state == "deleted"
    assert found["hidden"].private is True


def test_no_retired_fields_means_nothing_is_queried_or_found(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x"})

    assert prune.find_orphaned_extras(session, set()) == []


def test_datasets_come_back_ordered_by_name(prune, session):
    add_package(session, "1", "zeta", extras={"custodian": "x"})
    add_package(session, "2", "alpha", extras={"custodian": "x"})

    assert [o.name for o in prune.find_orphaned_extras(session, RETIRED)] == ["alpha", "zeta"]


# --- deleting ------------------------------------------------------------------------


def test_deleting_removes_exactly_the_listed_extras(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x", "variables": "[]", "guid": "g", "related_resource": "r"})
    add_package(session, "2", "b", extras={"custodian": "keep me, b was not listed", "guid": "g"})
    orphans = [o for o in prune.find_orphaned_extras(session, RETIRED) if o.package_id == "1"]

    assert prune.delete_orphaned_extras(session, orphans) == 2
    session.commit()

    assert extras_of(session, "1") == ["guid", "related_resource"]
    assert extras_of(session, "2") == ["custodian", "guid"]


def test_deleting_nothing_changes_nothing(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x"})

    assert prune.delete_orphaned_extras(session, []) == 0
    assert extras_of(session, "1") == ["custodian"]


def test_a_rolled_back_delete_leaves_the_extras(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x"})
    prune.delete_orphaned_extras(session, prune.find_orphaned_extras(session, RETIRED))
    session.rollback()

    assert extras_of(session, "1") == ["custodian"]


def test_a_second_run_finds_nothing(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x"})
    prune.delete_orphaned_extras(session, prune.find_orphaned_extras(session, RETIRED))
    session.commit()

    assert prune.find_orphaned_extras(session, RETIRED) == []


# --- harvest sources -----------------------------------------------------------------


@pytest.fixture
def sources(session):
    session.execute(
        text("CREATE TABLE harvest_source (id TEXT PRIMARY KEY, title TEXT, active BOOLEAN, config TEXT)")
    )

    def add(source_id, title, config, active=True):
        session.execute(
            text("INSERT INTO harvest_source VALUES (:id, :title, :active, :config)"),
            {"id": source_id, "title": title, "active": active, "config": config},
        )
        session.commit()

    return add


def test_a_source_naming_a_profile_that_is_not_enabled_is_listed(prune, session, sources):
    sources("s1", "Old FDP", json.dumps({"metadata_profile": "healthdcat_r8"}), active=False)
    sources("s2", "Current FDP", json.dumps({"metadata_profile": "gdi_current"}))

    assert prune.find_sources_with_retired_profile(session, ["gdi_current"]) == [
        prune.RetiredSource("s1", "Old FDP", False, "healthdcat_r8")
    ]


@pytest.mark.parametrize(
    "config",
    [None, "", "{}", "not json", "[]", '"text"', json.dumps({"profile": "fairdatapoint_dcat_ap"}), json.dumps({"metadata_profile": None}),
     json.dumps({"metadata_profile": "  "}), json.dumps({"metadata_profile": 7})],
)
def test_a_source_that_names_no_profile_is_not_listed(prune, session, sources, config):
    sources("s1", "Plain", config)

    assert prune.find_sources_with_retired_profile(session, ["gdi_current"]) == []


def test_a_deployment_without_harvest_has_no_sources(prune, session):
    assert prune.find_sources_with_retired_profile(session, ["gdi_current"]) == []


# --- the report ----------------------------------------------------------------------


def report(prune, session, deleting=False, retired=None, sources=()):
    retired = retired if retired is not None else {"dataset_fields": {"custodian": ["healthdcat_r8"]}, "resource_fields": {}}
    orphans = prune.find_orphaned_extras(session, set(retired["dataset_fields"]))
    return "\n".join(prune.format_report(["gdi_current"], retired, orphans, list(sources), deleting))


def test_the_dry_run_report_names_datasets_and_keys_and_says_nothing_changed(prune, session):
    add_package(session, "1", "a", private=True, extras={"custodian": "SECRET-VALUE"})

    text_ = report(prune, session)

    assert "Enabled metadata profiles: gdi_current" in text_
    assert "custodian (healthdcat_r8)" in text_
    assert "Orphaned extras: 1 on 1 dataset(s)" in text_
    assert "a (1) [active, private]: custodian" in text_
    assert "Dry run: nothing was changed. Rerun with --delete" in text_
    assert "SECRET-VALUE" not in text_


def test_the_report_of_a_delete_run_is_not_labelled_a_dry_run(prune, session):
    add_package(session, "1", "a", extras={"custodian": "x"})

    assert "Dry run" not in report(prune, session, deleting=True)


def test_nothing_to_prune_does_not_suggest_deleting(prune, session):
    text_ = report(prune, session)

    assert "Orphaned extras: 0 on 0 dataset(s)" in text_
    assert "--delete" not in text_


def test_no_retired_dataset_fields_is_said_plainly(prune, session):
    text_ = report(prune, session, retired={"dataset_fields": {}, "resource_fields": {}})

    assert "nothing can be orphaned" in text_


def test_retired_resource_fields_are_reported_as_not_pruned(prune, session):
    text_ = report(prune, session, retired={"dataset_fields": {}, "resource_fields": {"res_b": ["b"]}})

    assert "Resource fields of retired profiles are not pruned by this command: res_b" in text_


def test_harvest_sources_are_listed_and_left_alone(prune, session, sources):
    sources("s1", "Old FDP", json.dumps({"metadata_profile": "healthdcat_r8"}))
    found = prune.find_sources_with_retired_profile(session, ["gdi_current"])

    text_ = report(prune, session, sources=found)

    assert "Old FDP (s1) [active]: healthdcat_r8" in text_
    assert "this command does not change them" in text_
