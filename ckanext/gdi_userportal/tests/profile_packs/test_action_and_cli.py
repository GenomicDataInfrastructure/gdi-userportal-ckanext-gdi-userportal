# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The conformance API action and the ``profiles prune`` command, with CKAN's globals patched.

These need CKAN and this extension importable, but no database and no running CKAN:

    uv run --no-project --python 3.10 --with ckan==2.11.5 --with-requirements <ckan freeze> \
        --with sqlalchemy --with pytest --with-editable . python -I -m pytest -p no:ckan <this file>

Without CKAN the module is skipped. The prune command runs against SQLite.
"""

from types import SimpleNamespace
from unittest import mock

import pytest

pytest.importorskip("ckan")
pytest.importorskip("sqlalchemy")

from click.testing import CliRunner  # noqa: E402
from ckan.logic import ValidationError  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ckanext.gdi_userportal import cli  # noqa: E402
from ckanext.gdi_userportal.logic.action import get as get_module  # noqa: E402

from test_conformance import NON_PUBLIC, non_public_dataset  # noqa: E402


# --- the API action ----------------------------------------------------------------------


def run_action(package, config, data_dict=None, context=None):
    get_action = mock.MagicMock(return_value=mock.MagicMock(return_value=package))
    toolkit = SimpleNamespace(get_action=get_action, config=config, ValidationError=ValidationError)
    with mock.patch.object(get_module, "toolkit", toolkit):
        result = get_module.gdi_metadata_profile_conformance(context if context is not None else {"user": "u"}, data_dict)
    return result, get_action


def dataset(**extra):
    return {"id": "d1", "name": "one", "type": "dataset", **extra}


BOTH = {"ckanext.dcat.metadata_profiles": "healthdcat_r8 gdi_current", "ckanext.dcat.metadata_profiles.main": "gdi_current"}


@pytest.mark.parametrize("data_dict", [None, {}, {"id": ""}])
def test_the_action_needs_an_id(data_dict):
    with pytest.raises(ValidationError):
        run_action(dataset(), BOTH, data_dict)


def test_the_action_reads_the_dataset_through_package_show_with_a_copy_of_the_context():
    context = {"user": "u", "keep": "me"}
    _, get_action = run_action(dataset(), BOTH, {"id": "one"}, context)

    get_action.assert_called_once_with("package_show")
    (passed, data), _ = get_action.return_value.call_args
    assert data == {"id": "one"}
    assert passed == context
    assert passed is not context  # package_show writes into the context it is given


def test_a_dataset_series_is_rejected():
    with pytest.raises(ValidationError, match="only computed for datasets"):
        run_action(dataset(type="dataset_series"), BOTH, {"id": "one"})


def test_the_action_answers_for_every_enabled_profile_and_names_the_main_one():
    result, _ = run_action({**dataset(), **non_public_dataset()}, BOTH, {"id": "one"})

    assert result["main_profile"] == "gdi_current"
    assert result["access_layer"] == "NON_PUBLIC"
    assert set(result["profiles"]) == {"healthdcat_r8", "gdi_current"}
    assert result["conformant_profiles"] == ["healthdcat_r8", "gdi_current"]
    assert (result["id"], result["name"]) == ("d1", "one")


def test_an_old_dataset_is_not_conformant_and_does_not_raise():
    result, _ = run_action(dataset(title="Old", notes=None, extras=[{"key": "guid", "value": "x"}]), BOTH, {"id": "one"})

    assert result["conformant_profiles"] == ["gdi_current"]
    assert "access rights is missing" in result["profiles"]["healthdcat_r8"]["reason"]


def test_the_main_profile_defaults_to_the_first_enabled_one():
    result, _ = run_action(dataset(), {"ckanext.dcat.metadata_profiles": "healthdcat_r8 gdi_current"}, {"id": "one"})

    assert result["main_profile"] == "healthdcat_r8"


@pytest.mark.parametrize("config", [{}, {"ckanext.dcat.metadata_profiles": ""}])
def test_a_deployment_without_generated_config_is_gdi_current_only(config):
    result, _ = run_action(dataset(access_rights=NON_PUBLIC), config, {"id": "one"})

    assert list(result["profiles"]) == ["gdi_current"]
    assert result["main_profile"] == "gdi_current"


def test_the_rules_of_a_profile_are_loaded_once():
    get_module._conformance_rules.cache_clear()

    assert get_module._conformance_rules("healthdcat_r8") is get_module._conformance_rules("healthdcat_r8")
    assert get_module._conformance_rules.cache_info().misses == 1


# --- the prune command -------------------------------------------------------------------


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE package (id TEXT PRIMARY KEY, name TEXT, type TEXT, state TEXT, private BOOLEAN)"))
        connection.execute(
            text("CREATE TABLE package_extra (id TEXT PRIMARY KEY, key TEXT, value TEXT, state TEXT, package_id TEXT)")
        )
        connection.execute(text("INSERT INTO package VALUES ('p1', 'ds-one', 'dataset', 'active', 0)"))
        for index, key in enumerate(["custodian", "has_structured_data", "related_resource", "guid"]):
            connection.execute(
                text("INSERT INTO package_extra VALUES (:id, :key, 'v', 'active', 'p1')"), {"id": f"e{index}", "key": key}
            )
    with Session(engine) as session:
        yield session


def keys(session):
    return [k for (k,) in session.execute(text("SELECT key FROM package_extra ORDER BY key"))]


def prune(db, args=(), input_=None, profiles="gdi_current", rebuild=None):
    rebuild = rebuild or mock.MagicMock()
    config = {"ckanext.dcat.metadata_profiles": profiles} if profiles is not None else {}
    with mock.patch("ckan.model.Session", db), \
            mock.patch("ckan.lib.search.rebuild", rebuild), \
            mock.patch("ckan.plugins.toolkit.config", config, create=True):
        result = CliRunner().invoke(cli.gdi_userportal, ["profiles", "prune", *args], input=input_)
    return result, rebuild


def test_prune_is_a_dry_run_by_default(db):
    result, rebuild = prune(db)

    assert result.exit_code == 0
    assert "custodian, has_structured_data" in result.output
    assert "Dry run: nothing was changed. Rerun with --delete" in result.output
    assert keys(db) == ["custodian", "guid", "has_structured_data", "related_resource"]
    rebuild.assert_not_called()


def test_prune_never_lists_the_extras_every_profile_keeps(db):
    result, _ = prune(db)

    listed = result.output.split("Orphaned extras")[1]
    assert "related_resource" not in listed
    assert "guid" not in listed


def test_declining_the_confirmation_deletes_nothing(db):
    result, rebuild = prune(db, ["--delete"], input_="n\n")

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert len(keys(db)) == 4
    rebuild.assert_not_called()


def test_confirming_deletes_the_orphans_and_reindexes_the_dataset(db):
    result, rebuild = prune(db, ["--delete"], input_="y\n")

    assert result.exit_code == 0
    assert "Deleted 2 extra(s) from 1 dataset(s)." in result.output
    assert keys(db) == ["guid", "related_resource"]
    rebuild.assert_called_once_with(package_id="p1")


def test_yes_skips_the_confirmation(db):
    result, _ = prune(db, ["--delete", "--yes"])

    assert result.exit_code == 0
    assert keys(db) == ["guid", "related_resource"]


def test_delete_with_nothing_to_prune_does_not_ask_or_touch_anything(db):
    result, rebuild = prune(db, ["--delete"], profiles="healthdcat_r8 gdi_current")

    assert result.exit_code == 0
    assert "Orphaned extras: 0 on 0 dataset(s)" in result.output
    assert len(keys(db)) == 4
    rebuild.assert_not_called()


def test_a_failed_reindex_is_reported_but_the_delete_stands(db):
    result, _ = prune(db, ["--delete", "--yes"], rebuild=mock.MagicMock(side_effect=RuntimeError("solr down")))

    assert result.exit_code == 0
    assert keys(db) == ["guid", "related_resource"]
    assert "could not reindex ds-one: solr down" in result.output
    assert "ckan search-index rebuild" in result.output


def test_a_failed_delete_rolls_back_and_fails(db):
    with mock.patch.object(db, "rollback", wraps=db.rollback) as rollback, \
            mock.patch("ckanext.gdi_userportal.profile_packs.prune.delete_orphaned_extras", side_effect=RuntimeError("db gone")):
        result, rebuild = prune(db, ["--delete", "--yes"])

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    rollback.assert_called_once_with()
    rebuild.assert_not_called()
    assert len(keys(db)) == 4


@pytest.mark.parametrize("profiles", [None, "", "   "])
def test_prune_refuses_to_guess_the_enabled_profiles(db, profiles):
    result, rebuild = prune(db, ["--delete", "--yes"], profiles=profiles)

    assert result.exit_code == 1
    assert "is not set, so the enabled profiles are unknown" in result.output
    assert len(keys(db)) == 4
    rebuild.assert_not_called()


def test_prune_refuses_an_unknown_enabled_profile(db):
    result, _ = prune(db, ["--delete", "--yes"], profiles="nope")

    assert result.exit_code == 1
    assert "unknown metadata profile 'nope'" in result.output
    assert len(keys(db)) == 4
