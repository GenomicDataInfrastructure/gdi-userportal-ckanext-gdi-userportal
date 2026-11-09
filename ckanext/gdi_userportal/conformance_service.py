# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

"""
Conformance of datasets to the enabled metadata profiles, as the API action, the dataset and search
pages, the report action and the CLI use it.

Everything is computed from the dataset on every call and stored nowhere, and nothing here touches the
Solr schema or the index (ADR 0001, section 6). The rules come from the pack manifests; a pack without
rules has no mandatory properties and is satisfied by every dataset.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Mapping

from ckanext.gdi_userportal.profile_packs import conformance as profile_conformance
from ckanext.gdi_userportal.profile_packs import generator as profile_generator

log = logging.getLogger(__name__)

# Datasets read from the search per request of the report: below ckan.search.rows_max (1000).
REPORT_PAGE_SIZE = 500


@functools.lru_cache(maxsize=None)
def rules_for(profile: str):
    """The conformance document of a pack, or None when it declares no mandatory properties."""
    registry = profile_generator.Registry()
    return registry.conformance(registry.pack(profile))


def enabled_profiles(config) -> list:
    """The profiles the deployment enables; ``gdi_current`` alone when the option is unset."""
    return profile_generator.parse_profiles(config.get(profile_generator.OPTION_PROFILES))


def main_profile(config, enabled) -> str:
    return (config.get(profile_generator.OPTION_MAIN_PROFILE) or "").strip() or enabled[0]


def evaluate_dataset(dataset, config, profiles=None) -> dict:
    """``profile_conformance.evaluate`` of ``dataset`` for ``profiles`` (default: every enabled one)."""
    names = list(profiles) if profiles is not None else enabled_profiles(config)
    return profile_conformance.evaluate(dataset, names, {name: rules_for(name) for name in names})


def page_indicator(dataset, config):
    """What the dataset and search pages show: the conformance to every enabled profile.

    ``{"access_layer": layer or None,
       "profiles": [{"name", "conformant", "missing": [property labels], "reason"}, ...],
       "failing": [the entries of "profiles" that are not conformant]}``

    None when no indicator applies: the record is not a dataset (a series has no rules), or anything
    goes wrong. A page must render whatever the data holds, so this never raises.
    """
    try:
        if not isinstance(dataset, Mapping) or dataset.get("type", "dataset") != "dataset":
            return None
        result = evaluate_dataset(dataset, config)
    except Exception:  # noqa: BLE001 - a missing indicator beats a page that fails to render
        log.warning("Could not compute the metadata profile conformance of a dataset", exc_info=True)
        return None
    entries = [
        {
            "name": name,
            "conformant": outcome["conformant"],
            "missing": [item["property"] for item in outcome["missing"]],
            "reason": outcome.get("reason"),
        }
        for name, outcome in result["profiles"].items()
    ]
    return {
        "access_layer": result["access_layer"],
        "profiles": entries,
        "failing": [entry for entry in entries if not entry["conformant"]],
    }


def _all_datasets(package_search):
    """Every dataset the search shows, a page at a time."""
    start = 0
    while True:
        page = package_search(
            {
                "q": "*:*",
                "fq": "+dataset_type:dataset",
                "sort": "name asc",
                "rows": REPORT_PAGE_SIZE,
                "start": start,
                "include_private": True,
            }
        )
        results = page.get("results") or []
        yield from results
        start += len(results)
        if not results or start >= page.get("count", 0):
            return


def _report_entry(dataset, layer, outcome) -> dict:
    entry = {
        "id": dataset.get("id"),
        "name": dataset.get("name"),
        "title": dataset.get("title") or dataset.get("name"),
        "access_layer": layer,
        "missing": [item["property"] for item in outcome["missing"]],
    }
    if outcome.get("reason"):
        entry["reason"] = outcome["reason"]
    return entry


def conformance_report(package_search, config, profiles=None) -> dict:
    """The datasets that do not conform, per profile.

    ``package_search`` is called with a data dict and must answer like the ``package_search`` action: the
    search decides which datasets are visible, so datasets of a hidden profile are left out. Only the
    non-conforming datasets are listed, each with what it misses::

        {"enabled_profiles": [...], "checked": 32,
         "profiles": {name: {"non_conformant": 2,
                             "datasets": [{"id", "name", "title", "access_layer",
                                           "missing": [labels], "reason": text, only without a layer}]}}}
    """
    enabled = enabled_profiles(config)
    selected = list(profiles) if profiles else enabled
    rules = {name: rules_for(name) for name in selected}
    listing = {name: [] for name in selected}
    checked = 0
    for dataset in _all_datasets(package_search):
        checked += 1
        result = profile_conformance.evaluate(dataset, selected, rules)
        for name, outcome in result["profiles"].items():
            if not outcome["conformant"]:
                listing[name].append(_report_entry(dataset, result["access_layer"], outcome))
    return {
        "enabled_profiles": enabled,
        "checked": checked,
        "profiles": {name: {"non_conformant": len(items), "datasets": items} for name, items in listing.items()},
    }


def format_report(report) -> list:
    """The lines the ``profiles conformance`` command prints for a ``conformance_report``."""
    lines = [f"Checked {report['checked']} dataset(s) against: {', '.join(report['profiles'])}"]
    for name, outcome in report["profiles"].items():
        if not outcome["non_conformant"]:
            lines.append(f"{name}: all conform")
            continue
        lines.append(f"{name}: {outcome['non_conformant']} of {report['checked']} do not conform")
        for dataset in outcome["datasets"]:
            layer = f" [{dataset['access_layer']}]" if dataset["access_layer"] else ""
            shortfall = f"missing {', '.join(dataset['missing'])}" if dataset["missing"] else dataset.get("reason", "")
            lines.append(f"  {dataset['name']}{layer}: {shortfall}")
    return lines
