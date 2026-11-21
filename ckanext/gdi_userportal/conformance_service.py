# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Conformance of datasets, dataset series and distributions to the enabled metadata profiles, as the API action,
the dataset, series, distribution and search pages, the report action and the CLI use it.

Everything is computed from the record on every call and stored nowhere, and nothing here touches the Solr schema
or the index. Conformance is reported, never enforced: the rules are the mandatory properties of each pack's
conformance file, and a pack without rules has no mandatory properties and is satisfied by every record.

A record is checked against the profile it comes from: the ``metadata_profile`` of the harvest source that created
it, the main profile when that source names none, and every enabled profile when no source says (a dataset made by
hand or through the API). A sample and an analytics distribution are distributions: they are resources of the
dataset, checked like the others and labelled by ``resource_kind``.
"""

from __future__ import annotations

import functools
import json
import logging
from collections.abc import Mapping

from ckanext.gdi_userportal.profile_packs import conformance as profile_conformance
from ckanext.gdi_userportal.profile_packs import generator as profile_generator

log = logging.getLogger(__name__)

# Records read from the search per request of the report: below ckan.search.rows_max (1000).
REPORT_PAGE_SIZE = 500

DATASET = "dataset"
SERIES = "dataset_series"
SOURCE_ID_FIELD = "harvest_source_id"

# Why a record is checked against the profiles it is.
BASIS_SOURCE = "source"  # the metadata_profile of its harvest source
BASIS_MAIN = "main"  # its harvest source names none: the main profile
BASIS_ENABLED = "enabled"  # no harvest source says: every enabled profile

# The kinds of distribution, by the dataset property that points at them.
KIND_DISTRIBUTION = "distribution"
KIND_SAMPLE = "sample"
KIND_ANALYTICS = "analytics"


@functools.lru_cache(maxsize=None)
def rules_for(profile: str):
    """The conformance document of a pack, or None when it declares no mandatory properties."""
    registry = profile_generator.Registry()
    return registry.conformance(registry.pack(profile))


def _rules(names) -> dict:
    return {name: rules_for(name) for name in names}


def enabled_profiles(config) -> list:
    """The profiles the deployment enables; ``gdi_current`` alone when the option is unset."""
    return profile_generator.parse_profiles(config.get(profile_generator.OPTION_PROFILES))


def main_profile(config, enabled) -> str:
    return (config.get(profile_generator.OPTION_MAIN_PROFILE) or "").strip() or enabled[0]


# --- which profiles a record is checked against ------------------------------------------


def source_id_of(record):
    """The harvest source that created the record, from its extras, or None."""
    value = record.get(SOURCE_ID_FIELD)
    if not value:
        extras = record.get("extras")
        if isinstance(extras, Mapping):
            value = extras.get(SOURCE_ID_FIELD)
        elif isinstance(extras, (list, tuple)):
            value = next(
                (e.get("value") for e in extras if isinstance(e, Mapping) and e.get("key") == SOURCE_ID_FIELD), None
            )
    return value.strip() if isinstance(value, str) and value.strip() else None


def applicable_profiles(record, enabled, main, source_profiles):
    """``(profiles to check the record against, basis, the profile its source names or None)``.

    ``source_profiles`` is ``{source id: metadata_profile or None}`` for the harvest sources that exist. A source
    whose profile is not enabled leaves nothing to check: its datasets are hidden, and a sysadmin who opens one
    sees no indicator.
    """
    source_id = source_id_of(record)
    if source_id is None or source_id not in source_profiles:
        return list(enabled), BASIS_ENABLED, None
    named = source_profiles[source_id]
    profile = named or main
    return ([profile] if profile in enabled else []), (BASIS_SOURCE if named else BASIS_MAIN), named


def applicable_for(record, config, lookup):
    enabled = enabled_profiles(config)
    source_id = source_id_of(record)
    sources = lookup([source_id]) if lookup is not None and source_id else {}
    return applicable_profiles(record, enabled, main_profile(config, enabled), sources)


# --- the empty properties a page lists ----------------------------------------------------


@functools.lru_cache(maxsize=None)
def profile_fields(profile: str) -> dict:
    """``{section: frozenset of field names}`` the pack ``profile`` defines, for the dataset and resource fields."""
    sections = {section: set() for section in profile_generator.FIELD_SECTIONS}
    for key in profile_generator.build_schema([profile]).fields:
        section, _, name = key.partition(".")
        if section in sections:
            sections[section].add(name)
    return {section: frozenset(names) for section, names in sections.items()}


def empty_property_scope(record, section, config, lookup=None):
    """The field names of ``section`` a page may list without a value for ``record``, or None for all of them.

    The generated schema holds the fields of every enabled profile, so a page that lists the empty properties
    would also list those of a profile the dataset does not come from. For a dataset whose harvest source names
    a profile (or none, which is the main profile) only the fields of that pack are in scope. A dataset no
    source says anything about, and anything that is not a dataset (a series has a schema of its own, not
    built from the packs), has no restriction. ``section`` is ``dataset_fields`` or ``resource_fields``;
    ``lookup`` is as for ``page_indicator``. Never raises: on a failure every field is in scope, as it was
    before.
    """
    try:
        if not isinstance(record, Mapping) or record.get("type", DATASET) != DATASET:
            return None
        names, basis, _ = applicable_for(record, config, lookup)
        if basis == BASIS_ENABLED:
            return None
        return frozenset().union(*(profile_fields(name)[section] for name in names))
    except Exception:  # noqa: BLE001 - listing too many empty properties beats a page that fails to render
        log.warning("Could not tell which empty properties to list for a record", exc_info=True)
        return None


# --- distributions: plain, sample and analytics ------------------------------------------


def _uris(value) -> list:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                return _uris(json.loads(text))
            except ValueError:
                pass
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def resource_kind(dataset, resource) -> str:
    """``sample`` or ``analytics`` when the dataset points at the resource by that property, else ``distribution``.

    adms:sample and healthdcatap:analytics link a dcat:Distribution, so all three are distributions.
    """
    uri = resource.get("uri") if isinstance(resource, Mapping) else None
    if isinstance(uri, str) and uri.strip():
        uri = uri.strip()
        if uri in _uris(dataset.get(KIND_SAMPLE)):
            return KIND_SAMPLE
        if uri in _uris(dataset.get(KIND_ANALYTICS)):
            return KIND_ANALYTICS
    return KIND_DISTRIBUTION


def _display_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        texts = [value.get("en"), *value.values()]
        return next((text.strip() for text in texts if isinstance(text, str) and text.strip()), "")
    return ""


def resource_name(resource) -> str:
    """A name for the distribution: its title, else its name, URL or id."""
    for key in ("name_translated", "name", "url", "id"):
        text = _display_text(resource.get(key))
        if text:
            return text
    return ""


# --- evaluation ---------------------------------------------------------------------------


def evaluate_dataset(dataset, config, profiles=None) -> dict:
    """``profile_conformance.evaluate`` of ``dataset`` for ``profiles`` (default: every enabled one)."""
    names = list(profiles) if profiles is not None else enabled_profiles(config)
    return profile_conformance.evaluate(dataset, names, _rules(names))


def evaluate_series(series, config, profiles=None) -> dict:
    """The conformance of a dataset series: ``evaluate_dataset``'s shape, with no access layer."""
    names = list(profiles) if profiles is not None else enabled_profiles(config)
    return {"access_layer": None, **profile_conformance.evaluate_class(series, names, _rules(names), "series")}


def evaluate_distributions(dataset, config, profiles=None) -> list:
    """The conformance of each resource of ``dataset``, samples and analytics distributions included::

    ``[{"id", "name", "kind", "profiles": {name: {...}}, "conformant_profiles": [...]}, ...]``
    """
    names = list(profiles) if profiles is not None else enabled_profiles(config)
    rules = _rules(names)
    resources = dataset.get("resources")
    return [
        {
            "id": resource.get("id"),
            "name": resource_name(resource),
            "kind": resource_kind(dataset, resource),
            **profile_conformance.evaluate_class(resource, names, rules, "distribution"),
        }
        for resource in (resources if isinstance(resources, (list, tuple)) else [])
        if isinstance(resource, Mapping)
    ]


# --- what the pages show -------------------------------------------------------------------


def _entries(outcomes) -> list:
    return [
        {
            "name": name,
            "conformant": outcome["conformant"],
            "missing": [item["property"] for item in outcome["missing"]],
            "reason": outcome.get("reason"),
        }
        for name, outcome in outcomes.items()
    ]


def _failing(entries) -> list:
    return [entry for entry in entries if not entry["conformant"]]


def page_indicator(record, config, source_profiles=None):
    """What the dataset, series and search pages show: the conformance of the record to its profiles.

    ``{"kind": "dataset" | "dataset_series", "basis": ..., "access_layer": layer or None,
       "profiles": [{"name", "conformant", "missing": [property labels], "reason"}, ...],
       "failing": [the entries of "profiles" that are not conformant],
       "distributions": [{"id", "name", "kind", "profiles": [...], "failing": [...]}, ...]}``

    ``source_profiles`` maps a list of harvest source ids to ``{source id: metadata_profile or None}``; without
    it every enabled profile is used. ``distributions`` lists the resources of a dataset, samples and analytics
    distributions included, and is empty for a series. None when no indicator applies (the record is neither a
    dataset nor a series, or no profile applies to it) or anything goes wrong: a page must render whatever the
    data holds, so this never raises.
    """
    try:
        kind = record.get("type", DATASET) if isinstance(record, Mapping) else None
        if kind not in (DATASET, SERIES):
            return None
        names, basis, _ = applicable_for(record, config, source_profiles)
        if not names:
            return None
        if kind == SERIES:
            result, distributions = evaluate_series(record, config, names), []
        else:
            result = evaluate_dataset(record, config, names)
            distributions = [
                {"id": item["id"], "name": item["name"], "kind": item["kind"], **_checked_entries(item["profiles"])}
                for item in evaluate_distributions(record, config, names)
            ]
    except Exception:  # noqa: BLE001 - a missing indicator beats a page that fails to render
        log.warning("Could not compute the metadata profile conformance of a record", exc_info=True)
        return None
    return {
        "kind": kind,
        "basis": basis,
        "access_layer": result["access_layer"],
        **_checked_entries(result["profiles"]),
        "distributions": distributions,
    }


def _checked_entries(outcomes) -> dict:
    entries = _entries(outcomes)
    return {"profiles": entries, "failing": _failing(entries)}


def resource_indicator(dataset, resource, config, source_profiles=None):
    """The same for one distribution of ``dataset``, for its entry in the list and its own page::

    ``{"kind": "distribution" | "sample" | "analytics", "basis": ..., "profiles": [...], "failing": [...]}``

    The profiles are those of the dataset the distribution belongs to. None when there is nothing to show or
    anything goes wrong; never raises.
    """
    try:
        if not isinstance(dataset, Mapping) or dataset.get("type", DATASET) != DATASET:
            return None
        if not isinstance(resource, Mapping):
            return None
        names, basis, _ = applicable_for(dataset, config, source_profiles)
        if not names:
            return None
        outcomes = profile_conformance.evaluate_class(resource, names, _rules(names), "distribution")["profiles"]
    except Exception:  # noqa: BLE001 - a missing indicator beats a page that fails to render
        log.warning("Could not compute the metadata profile conformance of a distribution", exc_info=True)
        return None
    return {"kind": resource_kind(dataset, resource), "basis": basis, **_checked_entries(outcomes)}


# --- the report -----------------------------------------------------------------------------


def _pages(package_search, record_type):
    """The records of one type the search shows, a page at a time."""
    start = 0
    while True:
        page = package_search(
            {
                "q": "*:*",
                "fq": f"+dataset_type:{record_type}",
                "sort": "name asc",
                "rows": REPORT_PAGE_SIZE,
                "start": start,
                "include_private": True,
            }
        )
        results = page.get("results") or []
        if results:
            yield results
        start += len(results)
        if not results or start >= page.get("count", 0):
            return


def _section() -> dict:
    return {"checked": 0, "non_conformant": 0, "items": []}


def _tally(section, outcome, make_entry) -> None:
    """Count one check; ``make_entry(outcome)`` builds the item to list when it failed."""
    section["checked"] += 1
    if not outcome["conformant"]:
        section["non_conformant"] += 1
        section["items"].append(make_entry(outcome))


def _missing(outcome) -> list:
    return [item["property"] for item in outcome["missing"]]


def _record_entry(record, layer, outcome) -> dict:
    entry = {
        "id": record.get("id"),
        "name": record.get("name"),
        "title": record.get("title") or record.get("name"),
        "access_layer": layer,
        "missing": _missing(outcome),
    }
    if outcome.get("reason"):
        entry["reason"] = outcome["reason"]
    return entry


def _distribution_entry(dataset, resource, kind, outcome) -> dict:
    """The report item of a distribution that failed."""
    return {
        "id": resource.get("id"),
        "name": resource_name(resource),
        "kind": kind,
        "dataset": dataset.get("name"),
        "dataset_id": dataset.get("id"),
        "missing": _missing(outcome),
    }


def _check_dataset(dataset, names, rules, sections) -> int:
    """Check a dataset and its distributions against ``names``; returns how many distributions it has."""
    result = profile_conformance.evaluate(dataset, names, rules)
    make_dataset_entry = functools.partial(_record_entry, dataset, result["access_layer"])
    for name, outcome in result["profiles"].items():
        _tally(sections[name]["datasets"], outcome, make_dataset_entry)
    resources = [r for r in (dataset.get("resources") or []) if isinstance(r, Mapping)]
    for resource in resources:
        make_entry = functools.partial(_distribution_entry, dataset, resource, resource_kind(dataset, resource))
        for name, outcome in profile_conformance.evaluate_class(resource, names, rules, "distribution")["profiles"].items():
            _tally(sections[name]["distributions"], outcome, make_entry)
    return len(resources)


def _check_series(series, names, rules, sections) -> None:
    make_entry = functools.partial(_record_entry, series, None)
    for name, outcome in profile_conformance.evaluate_class(series, names, rules, "series")["profiles"].items():
        _tally(sections[name]["series"], outcome, make_entry)


def _check_record(record, record_type, names, rules, sections, seen) -> None:
    """Check one dataset or series against ``names`` and count what was looked at in ``seen``."""
    if record_type == SERIES:
        seen["series"] += 1
        _check_series(record, names, rules, sections)
    else:
        seen["datasets"] += 1
        seen["distributions"] += _check_dataset(record, names, rules, sections)


def conformance_report(package_search, config, profiles=None, source_profiles=None) -> dict:
    """The datasets, dataset series and distributions that do not conform, per profile.

    ``package_search`` is called with a data dict and must answer like the ``package_search`` action: the search
    decides which records are visible, so datasets of a hidden profile are left out. Each record is checked
    against the profile it comes from only (see ``applicable_profiles``); ``source_profiles`` maps a list of
    harvest source ids to ``{source id: metadata_profile or None}``, and without it every enabled profile
    applies. ``profiles`` limits the report to those profiles. Only what does not conform is listed::

        {"enabled_profiles": [...], "checked": datasets, "checked_series": n, "checked_distributions": n,
         "profiles": {name: {"datasets": {"checked": n, "non_conformant": n, "items": [...]},
                             "series": {...}, "distributions": {...}}}}

    A dataset item has ``id``, ``name``, ``title``, ``access_layer`` and ``missing`` (property labels, or a
    ``reason`` when there is no access layer); a series item the same; a distribution item ``id``, ``name``,
    ``kind``, ``dataset``, ``dataset_id`` and ``missing``.
    """
    enabled = enabled_profiles(config)
    main = main_profile(config, enabled)
    selected = list(profiles) if profiles else enabled
    rules = _rules(selected)
    sections = {name: {"datasets": _section(), "series": _section(), "distributions": _section()} for name in selected}
    seen = {"datasets": 0, "series": 0, "distributions": 0}
    for record_type in (DATASET, SERIES):
        for page in _pages(package_search, record_type):
            source_ids = {source_id_of(record) for record in page} - {None}
            sources = source_profiles(source_ids) if source_profiles and source_ids else {}
            for record in page:
                names = [n for n in applicable_profiles(record, enabled, main, sources)[0] if n in selected]
                _check_record(record, record_type, names, rules, sections, seen)
    return {
        "enabled_profiles": enabled,
        "checked": seen["datasets"],
        "checked_series": seen["series"],
        "checked_distributions": seen["distributions"],
        "profiles": sections,
    }


_SECTION_LABELS = (("datasets", "dataset(s)"), ("series", "series"), ("distributions", "distribution(s)"))


def format_report(report) -> list:
    """The lines the ``profiles conformance`` command prints for a ``conformance_report``."""
    lines = [
        f"Checked {report['checked']} dataset(s), {report['checked_series']} series "
        f"and {report['checked_distributions']} distribution(s)"
    ]
    for name, sections in report["profiles"].items():
        failing = [(key, label) for key, label in _SECTION_LABELS if sections[key]["non_conformant"]]
        if not failing:
            counts = ", ".join(f"{sections[key]['checked']} {label}" for key, label in _SECTION_LABELS)
            lines.append(f"{name}: all conform ({counts})")
            continue
        lines.append(
            f"{name}: "
            + "; ".join(
                f"{sections[key]['non_conformant']} of {sections[key]['checked']} {label} do not conform"
                for key, label in failing
            )
        )
        for key, _ in failing:
            lines += [f"  {_describe(key, item)}" for item in sections[key]["items"]]
    return lines


def _describe(key, item) -> str:
    shortfall = f"missing {', '.join(item['missing'])}" if item["missing"] else item.get("reason", "")
    if key == "distributions":
        return f"{item['dataset']} / {item['name']} ({item['kind']}): {shortfall}"
    layer = f" [{item['access_layer']}]" if item.get("access_layer") else ""
    prefix = "series " if key == "series" else ""
    return f"{prefix}{item['name']}{layer}: {shortfall}"
