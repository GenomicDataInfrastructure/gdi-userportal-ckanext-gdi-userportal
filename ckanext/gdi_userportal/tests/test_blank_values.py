# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""A dataset is saved without the fields that hold nothing, and what was saved before can be cleaned up."""

import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ckanext.gdi_userportal import blank_values, blank_values_cleanup
from ckanext.gdi_userportal.logic.action import blank_values as action


class TestPrune:
    @pytest.mark.parametrize(
        "value",
        [None, "", "  ", [], {}, "[]", "{}", " [] ", '{"en": "", "nl": ""}', {"en": "", "nl": None}, [None, ""], [[]]],
    )
    def test_nothing_is_left(self, value):
        assert blank_values.prune(value) is None

    @pytest.mark.parametrize("value", [0, False, "0", "false", "null", "x", ["a"], {"en": "x"}, 1.5])
    def test_a_value_stays(self, value):
        assert blank_values.prune(value) == value

    def test_empty_languages_and_items_are_left_out(self):
        assert blank_values.prune({"en": "Title", "nl": ""}) == {"en": "Title"}
        assert blank_values.prune({"en": ["a", ""], "nl": []}) == {"en": ["a"]}
        assert blank_values.prune(["a", "", None, "b"]) == ["a", "b"]

    def test_the_rows_of_a_repeating_field_are_never_changed_from_the_inside(self):
        # the validation of the nested subfields fails for a row that lacks a key it had ("role": "" removed
        # from a row of qualified_attribution made the dataset impossible to index)
        rows = [{"role": "", "agent": [{"email": "a@b.c", "country": []}]}, {"name": ""}]
        assert blank_values.prune(rows) == rows

    def test_rows_that_are_all_empty_are_a_value_that_holds_nothing(self):
        assert blank_values.prune([{"name": "", "email": ""}, {"agent": [{"x": []}]}]) is None
        assert blank_values.prune('[{"start": null, "end": null}]') is None

    def test_a_json_text_is_given_back_as_it_came_when_nothing_is_left_out(self):
        text_ = '{"en": "Title", "nl": "Titel"}'
        assert blank_values.prune(text_) is text_

    def test_a_json_text_with_empty_parts_is_written_again_without_them(self):
        assert json.loads(blank_values.prune('{"en": "Title", "nl": ""}')) == {"en": "Title"}

    def test_text_that_only_looks_like_json_is_kept(self):
        assert blank_values.prune("[not json") == "[not json"


def _schema():
    return {
        "dataset_fields": [{"field_name": name} for name in ("title", "provenance", "theme", "identifier", "publisher", "keep")],
        "resource_fields": [{"field_name": name} for name in ("url", "status", "conforms_to")],
    }


class TestPruneDataset:
    def prune(self, data):
        schema = _schema()
        return blank_values.prune_dataset(
            data,
            schema["dataset_fields"],
            schema["resource_fields"],
            {"title", "url"},
            {"url"},
        )

    def test_empty_schema_fields_are_dropped_and_core_fields_stay(self):
        cleaned = self.prune({"title": "", "provenance": {"en": "", "nl": ""}, "theme": [], "identifier": "", "keep": "x"})
        assert cleaned == {"title": "", "keep": "x"}

    def test_keys_the_schema_does_not_name_are_not_touched(self):
        assert self.prune({"free": "", "extras": []}) == {"free": "", "extras": []}

    def test_a_repeating_field_is_dropped_when_every_row_is_empty_and_kept_as_it_is_otherwise(self):
        assert self.prune({"publisher": [{"name": "", "email": ""}]}) == {}
        rows = [{"name": "x", "email": ""}, {"name": "", "email": ""}]
        assert self.prune({"publisher": rows}) == {"publisher": rows}

    def test_resources_are_cleaned_by_their_own_fields(self):
        cleaned = self.prune({"resources": [{"url": "", "status": "", "conforms_to": [], "id": "r1"}]})
        assert cleaned == {"resources": [{"url": "", "id": "r1"}]}

    def test_the_dataset_that_came_in_is_not_changed(self):
        data = {"provenance": {"en": "", "nl": ""}, "resources": [{"status": ""}]}
        self.prune(data)
        assert data == {"provenance": {"en": "", "nl": ""}, "resources": [{"status": ""}]}

    def test_a_dataset_without_resources_has_none_added(self):
        assert "resources" not in self.prune({"keep": "x"})


class TestTheAction:
    def test_it_follows_the_schema_of_the_dataset_type(self):
        cleaned = action.without_blank_values(
            {"type": "dataset", "title": "T", "notes_translated": {"en": "", "nl": ""}, "theme": [], "tags": [], "resources": []}
        )
        assert "notes_translated" not in cleaned
        assert "theme" not in cleaned
        assert cleaned["tags"] == [] and cleaned["resources"] == []  # not saved as extras: left alone

    def test_the_field_that_a_patch_clears_is_dropped(self):
        # package_patch merges {"provenance": ""} into the stored dataset and calls package_update with the result
        stored = {"type": "dataset", "title": "T", "provenance": {"en": "old", "nl": "oud"}}
        patched = {**stored, "provenance": ""}
        assert "provenance" not in action.without_blank_values(patched)

    def test_a_failure_does_not_stop_the_save(self, monkeypatch):
        def broken(*args, **kwargs):
            raise RuntimeError("no schema")

        monkeypatch.setattr(action.schema_access, "dataset_schema", broken)
        data = {"type": "dataset", "provenance": ""}
        assert action.without_blank_values(data) is data

    @pytest.mark.parametrize("chained", ["package_create", "package_update"])
    def test_the_chained_actions_pass_the_cleaned_dataset_on(self, chained):
        seen = {}

        def original(context, data_dict):
            seen.update(data_dict)
            return data_dict

        getattr(action, chained)(original, {}, {"type": "dataset", "title": "T", "provenance": ""})
        assert seen == {"type": "dataset", "title": "T"}


def _session():
    engine = create_engine("sqlite://")
    session = sessionmaker(bind=engine)()
    for statement in (
        "CREATE TABLE package (id TEXT PRIMARY KEY, name TEXT, type TEXT)",
        "CREATE TABLE package_extra (id TEXT PRIMARY KEY, package_id TEXT, key TEXT, value TEXT, state TEXT)",
        "CREATE TABLE resource (id TEXT PRIMARY KEY, package_id TEXT, extras TEXT, state TEXT, position INTEGER)",
    ):
        session.execute(text(statement))
    session.execute(text("INSERT INTO package VALUES ('p1', 'one', 'dataset')"))
    extras = [
        ("e1", "provenance", '{"en": "", "nl": ""}'),
        ("e2", "theme", "[]"),
        ("e3", "identifier", ""),
        ("e4", "version_notes", '{"en": "Note", "nl": ""}'),
        ("e5", "language", '["http://x/NLD"]'),
        ("e6", "not_in_the_schema", ""),
    ]
    for row_id, key, value in extras:
        session.execute(
            text("INSERT INTO package_extra VALUES (:id, 'p1', :key, :value, 'active')"),
            {"id": row_id, "key": key, "value": value},
        )
    session.execute(
        text("INSERT INTO resource VALUES ('r1', 'p1', :extras, 'active', 0)"),
        {
            "extras": json.dumps(
                {
                    "status": "",
                    "conforms_to": "[]",
                    "access_url": "https://x",
                    "language": ["http://x/NLD", ""],  # a list in the object, not a text
                }
            )
        },
    )
    return session


FIELDS = (
    {"provenance", "theme", "identifier", "version_notes", "language"},
    {"status", "conforms_to", "access_url", "language"},
)


class TestTheCleanup:
    def changes(self, session):
        return blank_values_cleanup.find_changes(session, lambda package_type: FIELDS)

    def test_it_finds_the_empty_values_of_schema_fields_only(self):
        found = {(change.kind, change.key): change.after for change in self.changes(_session())}
        assert found == {
            ("extra", "provenance"): None,
            ("extra", "theme"): None,
            ("extra", "identifier"): None,
            ("extra", "version_notes"): '{"en": "Note"}',
            ("resource", "status"): None,
            ("resource", "conforms_to"): None,
            ("resource", "language"): ["http://x/NLD"],
        }

    def test_nothing_is_changed_until_it_is_applied(self):
        session = _session()
        self.changes(session)
        assert session.execute(text("SELECT count(*) FROM package_extra")).scalar() == 6

    def test_applying_removes_and_rewrites(self):
        session = _session()
        blank_values_cleanup.apply_changes(session, self.changes(session))
        rows = dict(session.execute(text("SELECT key, value FROM package_extra")).fetchall())
        assert rows == {"version_notes": '{"en": "Note"}', "language": '["http://x/NLD"]', "not_in_the_schema": ""}
        # a list that stays a list: the validation of the dataset needs the list, not a JSON text of it
        assert json.loads(session.execute(text("SELECT extras FROM resource")).scalar()) == {
            "access_url": "https://x",
            "language": ["http://x/NLD"],
        }
        assert self.changes(session) == []

    def test_the_report_says_what_would_happen(self):
        lines = blank_values_cleanup.format_report(self.changes(_session()), deleting=False)
        assert lines[0].startswith("Would remove 5 empty value(s) and 2 value(s) with empty parts, in 1 dataset(s)")
        assert lines[-1].startswith("A dry run")
        assert blank_values_cleanup.format_report([], deleting=False) == ["No empty values are stored."]
