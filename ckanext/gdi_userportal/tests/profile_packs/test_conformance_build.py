# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
The conformance file is generated from R8's cardinality rules, never hand-copied.

The builder is tested on synthetic rules. Whether the committed file is what R8's real rules
produce needs the rules file, which lives outside this repository: point
``HEALTHDCAT_RULES_JSON`` at it to run that check.
"""

import json
import os
from pathlib import Path

import pytest
import yaml

from conftest import PACKS_DIR


def rule(card, requirement):
    return {"card": card, "requirement": requirement, "definition": "d", "usage_note": "u", "reuse": "E"}


def rules_text(public=None, restricted=None, non_public=None):
    base = {"title": rule("1..*", "Mandatory"), "theme": rule("1..*", "Mandatory"), "note": rule("0..*", "Optional")}
    return json.dumps(
        {
            "PUBLIC": public or base,
            "RESTRICTED": restricted or base,
            "NON-PUBLIC": non_public or {**base, "keyword": rule("1..*", "Mandatory")},
        }
    )


def fields_text(**properties):
    properties = properties or {"title": ["title_translated"], "theme": ["theme"], "keyword": ["tags"]}
    return yaml.safe_dump({"properties": properties})


def build(conformance_build, rules=None, fields=None):
    return json.loads(conformance_build.build(rules or rules_text(), fields or fields_text()))


def test_only_the_mandatory_properties_of_each_layer_are_kept(conformance_build):
    document = build(conformance_build)
    assert [r["property"] for r in document["layers"]["PUBLIC"]["mandatory"]] == ["title", "theme"]
    assert [r["property"] for r in document["layers"]["NON_PUBLIC"]["mandatory"]] == ["title", "theme", "keyword"]


def test_the_layer_names_are_normalised_and_every_layer_is_present(conformance_build):
    assert list(build(conformance_build)["layers"]) == ["PUBLIC", "RESTRICTED", "NON_PUBLIC"]


def test_a_property_carries_its_cardinality_and_its_fields(conformance_build):
    assert build(conformance_build)["layers"]["PUBLIC"]["mandatory"][0] == {
        "property": "title",
        "cardinality": "1..*",
        "fields": ["title_translated"],
    }


def test_the_source_is_recorded_by_name_and_hash(conformance_build):
    text = rules_text()
    document = json.loads(conformance_build.build(text, fields_text(), source_name="rules.json"))
    assert document["source"]["file"] == "rules.json"
    assert len(document["source"]["sha256"]) == 64
    changed = json.loads(conformance_build.build(text.replace("note", "remark"), fields_text(), source_name="rules.json"))
    assert changed["source"]["sha256"] != document["source"]["sha256"]


def test_building_is_deterministic(conformance_build):
    assert conformance_build.build(rules_text(), fields_text()) == conformance_build.build(rules_text(), fields_text())


def test_a_mandatory_property_without_fields_fails_and_names_it(conformance_build):
    with pytest.raises(conformance_build.ConformanceBuildError, match="'keyword' has no CKAN fields"):
        conformance_build.build(rules_text(), fields_text(title=["t"], theme=["theme"]))


@pytest.mark.parametrize("fields", [[], "tags", [""], [1]])
def test_a_property_needs_a_list_of_field_names(conformance_build, fields):
    with pytest.raises(conformance_build.ConformanceBuildError, match="no CKAN fields"):
        conformance_build.build(rules_text(), fields_text(title=["t"], theme=["theme"], keyword=fields))


def test_a_mapped_property_that_is_not_mandatory_anywhere_fails(conformance_build):
    with pytest.raises(conformance_build.ConformanceBuildError, match="not mandatory in any layer: note"):
        conformance_build.build(
            rules_text(), fields_text(title=["t"], theme=["theme"], keyword=["tags"], note=["notes"])
        )


def test_a_rule_that_contradicts_itself_fails(conformance_build):
    bad = {"title": rule("0..*", "Mandatory")}
    with pytest.raises(conformance_build.ConformanceBuildError, match="disagree with themselves"):
        conformance_build.build(rules_text(public=bad), fields_text(title=["t"]))


def test_a_missing_or_unknown_layer_fails(conformance_build):
    text = json.loads(rules_text())
    del text["RESTRICTED"]
    with pytest.raises(conformance_build.ConformanceBuildError, match="no layer RESTRICTED"):
        conformance_build.build(json.dumps(text), fields_text())
    text = json.loads(rules_text())
    text["SECRET"] = {}
    with pytest.raises(conformance_build.ConformanceBuildError, match="unknown layers.*SECRET"):
        conformance_build.build(json.dumps(text), fields_text())


@pytest.mark.parametrize("rules", ["not json", "[]", '{"PUBLIC": []}'])
def test_unusable_rules_fail_cleanly(conformance_build, rules):
    with pytest.raises(conformance_build.ConformanceBuildError):
        conformance_build.build(rules, fields_text())


def test_the_command_line_writes_and_checks_the_file(conformance_build, tmp_path, capsys):
    (tmp_path / "rules.json").write_text(rules_text())
    (tmp_path / "fields.yaml").write_text(fields_text())
    out = tmp_path / "out.json"
    args = ["--rules", str(tmp_path / "rules.json"), "--fields", str(tmp_path / "fields.yaml"), "--output", str(out)]

    assert conformance_build.main([*args, "--check"]) == 1  # nothing written yet
    assert not out.exists()
    assert conformance_build.main(args) == 0
    assert conformance_build.main([*args, "--check"]) == 0
    out.write_text(out.read_text().replace("title", "titel"))
    assert conformance_build.main([*args, "--check"]) == 1
    assert "out of date" in capsys.readouterr().err


def test_the_command_line_reports_a_build_error_and_exits_one(conformance_build, tmp_path, capsys):
    (tmp_path / "rules.json").write_text("nope")
    (tmp_path / "fields.yaml").write_text(fields_text())
    code = conformance_build.main(
        ["--rules", str(tmp_path / "rules.json"), "--fields", str(tmp_path / "fields.yaml"), "--output", str(tmp_path / "o")]
    )
    assert code == 1
    assert "ERROR" in capsys.readouterr().err


def test_the_mapping_that_ships_has_an_entry_for_every_property_the_file_lists(r8_rules):
    mapping = yaml.safe_load((PACKS_DIR / "conformance" / "healthdcat_r8_fields.yaml").read_text())["properties"]
    listed = {rule["property"] for layer in r8_rules["layers"].values() for rule in layer["mandatory"]}
    assert set(mapping) == listed


@pytest.mark.skipif(
    not os.environ.get("HEALTHDCAT_RULES_JSON"), reason="set HEALTHDCAT_RULES_JSON to the R8 cardinality rules file"
)
def test_the_committed_file_is_what_the_real_rules_produce(conformance_build):
    rules = Path(os.environ["HEALTHDCAT_RULES_JSON"])
    assert conformance_build.main(["--rules", str(rules), "--check"]) == 0
