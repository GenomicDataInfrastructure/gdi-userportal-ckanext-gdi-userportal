# SPDX-FileCopyrightText: 2026 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

# Read-only capture for the characterization tests: for every dataset, what the gdi_userportal plugin
# receives and returns in before_dataset_index, plus what its two side lookups answered, and what
# package_show gives with the term translations the translation layer would use.
# Nothing is written: the Solr connection is replaced by a fake, no commit, no DB write.
#
# Run it in the CKAN container (it reads the database, it is not a test):
#
#     docker exec -i <ckan container> python3 - < capture_corpus.py > corpus.json
#
# index_and_api_corpus.json is a selection of that output without the data_dict and validated_data_dict
# blobs, with the e-mail addresses replaced by example.org ones.
import copy
import json
import sys

from ckan import model
from ckan.cli import load_config
from ckan.config.middleware import make_app
from ckan.plugins import toolkit

app = make_app(load_config("/srv/app/ckan.ini"))

flask_app = getattr(app, "_wsgi_app", app)
while not hasattr(flask_app, "test_request_context"):
    flask_app = flask_app.app

with flask_app.test_request_context():
    import ckan.lib.search.index as search_index
    from ckanext.gdi_userportal import plugin as gdi_plugin
    from ckanext.gdi_userportal.logic.action import translation_utils as tu

    sent = []

    class FakeConnection:
        def add(self, docs=None, commit=False):
            sent.append(copy.deepcopy(docs))

        def commit(self, *args, **kwargs):
            pass

    search_index.make_connection = lambda *a, **k: FakeConnection()

    series_lookups = {}
    real_get_action = toolkit.get_action

    class RecordingToolkit:
        """The toolkit as the plugin sees it, recording what its package_show lookups (series) answer."""

        def __getattr__(self, attr):
            return getattr(toolkit, attr)

        def get_action(self, name):
            action = real_get_action(name)
            if name != "package_show":
                return action

            def wrapper(context, data_dict):
                result = action(context, data_dict)
                series_lookups[data_dict["id"]] = {"name": result.get("name"), "title": result.get("title")}
                return result

            return wrapper

    gdi_plugin.toolkit = RecordingToolkit()

    translations = {}
    real_all = gdi_plugin.get_all_translations

    def recording_all(terms):
        result = real_all(terms)
        translations.update(result)
        return result

    gdi_plugin.get_all_translations = recording_all

    captured = []
    real_hook = gdi_plugin.GdiUserPortalPlugin.before_dataset_index

    def hook(self, data_dict):
        entry = {"input": copy.deepcopy(data_dict)}
        out = real_hook(self, data_dict)
        entry["output"] = copy.deepcopy(out)
        captured.append(entry)
        return out

    gdi_plugin.GdiUserPortalPlugin.before_dataset_index = hook

    rows = (
        model.Session.query(model.Package.id, model.Package.name, model.Package.type)
        .filter(model.Package.state == "active")
        .filter(model.Package.type.in_(["dataset", "dataset_series"]))
        .order_by(model.Package.name)
        .all()
    )
    corpus = []
    index = search_index.PackageSearchIndex()
    for pkg_id, name, pkg_type in rows:
        captured.clear()
        sent.clear()
        context = {"model": model, "session": model.Session, "ignore_auth": True, "validate": False, "use_cache": False}
        pkg_dict = real_get_action("package_show")(context, {"id": pkg_id})
        index.index_package(copy.deepcopy(pkg_dict), defer_commit=True)
        if not captured:
            continue
        api = real_get_action("package_show")({"ignore_auth": True}, {"id": pkg_id})
        terms = tu.collect_values_to_translate(copy.deepcopy(api))
        term_table = {lang: tu.get_translations(terms, lang=lang) for lang in ("en", "nl")}
        shown = {lang: tu.replace_package(copy.deepcopy(api), term_table[lang], lang=lang) for lang in ("en", "nl")}
        corpus.append(
            {
                "name": name,
                "type": pkg_type,
                "index_input": captured[-1]["input"],
                "index_output": captured[-1]["output"],
                "solr_doc": sent[-1][0] if sent else None,
                "api_package": api,
                "terms": sorted(map(str, terms)),
                "term_translations": term_table,
                "api_output": shown,
            }
        )

    json.dump(
        {"series": series_lookups, "term_translations_for_index": translations, "datasets": corpus},
        sys.stdout,
        indent=1,
        sort_keys=True,
        default=str,
    )
