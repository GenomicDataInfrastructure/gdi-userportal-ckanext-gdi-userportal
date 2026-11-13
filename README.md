<!--
SPDX-FileCopyrightText: 2024 PNED G.I.E.

SPDX-License-Identifier: CC-BY-4.0
-->

[![REUSE status](https://api.reuse.software/badge/github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal)](https://api.reuse.software/info/github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal)
![main workflow](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/actions/workflows/main.yml/badge.svg)
![release workflow](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/actions/workflows/release.yml/badge.svg)
![test workflow](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/actions/workflows/test.yml/badge.svg)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=GenomicDataInfrastructure_gdi-userportal-ckanext-gdi-userportal&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=GenomicDataInfrastructure_gdi-userportal-ckanext-gdi-userportal)
[![GitHub contributors](https://img.shields.io/github/contributors/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal)](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/graphs/contributors)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

# ckanext-gdi-userportal

CKAN extension of the GDI User Portal. It holds the metadata profiles of the catalogue (the portal's own model
and HealthDCAT-AP Release 8), the dataset schema generated from them, the Solr indexing of datasets, the
translation of controlled vocabulary codes into labels for the API, and the profile conformance report.

The profiles, the schema and the Solr fields are described in
[ckanext/gdi_userportal/profile_packs/README.md](ckanext/gdi_userportal/profile_packs/README.md).

## Requirements

Developed and tested against CKAN 2.11 with the extensions listed in
`requirements.txt`: ckanext-scheming, ckanext-fluent, ckanext-harvest, ckanext-dataset-series and ckanext-dcat.

## Installation

To install ckanext-gdi-userportal:

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it into the virtualenv:

       git clone https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal.git
       cd gdi-userportal-ckanext-gdi-userportal
       pip install -e .
       pip install -r requirements.txt

3. Add `gdi_userportal` to the `ckan.plugins` setting in your CKAN config file (by default
   `/etc/ckan/default/ckan.ini`).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

       sudo service apache2 reload

In the GDI User Portal stack the plugin is installed and configured by
[gdi-userportal-ckan-docker](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckan-docker); the
metadata profiles are selected there with `GDI_METADATA_PROFILES`.

## Config settings

| Option | Default | Meaning |
|---|---|---|
| `ckanext.gdi_userportal.intro_text` | none | Introduction text shown on the portal. Readable without signing in. |
| `ckanext.gdi_userportal.show_empty_properties` | `false` | Dataset and distribution pages also list the properties that have no value, with a dash. Environment variable: `CKANEXT__GDI_USERPORTAL__SHOW_EMPTY_PROPERTIES`. See the profile packs README, "Empty properties". |

## Developer installation

To install ckanext-gdi-userportal for development, activate your CKAN virtualenv and do:

    git clone https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal.git
    cd gdi-userportal-ckanext-gdi-userportal
    pip install -e .
    pip install -r requirements.txt
    pip install -r dev-requirements.txt

Needed services, for a local CKAN:

Postgres:

    docker run -d \
      --name ckan-postgres \
      -e POSTGRES_USER=ckan_default \
      -e POSTGRES_PASSWORD=password \
      -e POSTGRES_DB=ckan_default \
      -v /path/to/your/data:/var/lib/postgresql/data \
      -p 5432:5432 \
      postgres

Solr: build the image from `solr/Dockerfile` in this repository. The core's schema is `solr/schema.xml`; the
dataset fields are added to it from the profiles when CKAN starts (see the profile packs README, "Solr schema").

Redis:

    docker run --name ckan-redis -p 6379:6379 -d redis:7

Add a new ckan.ini in your local repository and add the below values:

     sqlalchemy.url = postgresql://ckan_default:password@localhost:5432/ckan_default
     ckanext.dcat.rdf.profiles = euro_dcat_ap
     ckan.harvest.s3_rdf.aws_access_key = changeme
     ckan.harvest.s3_rdf.aws_secret_key = changeme

Full stack with Docker Compose: see the README of
[gdi-userportal-ckan-docker](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckan-docker).

## Configure User login

     ckan sysadmin add <username>    # Replace <username> with the actual username you want to create

## DB Set UP

To initialize local db:

     ckan db init

To initialize db with harvester tables:

     ckan db upgrade -p harvest

To clean the db:

     ckan db clean

## Term Translation Migrations

Versioned migrations load the translations of controlled vocabulary terms into CKAN's `term_translation` table.
They run on container startup, after the CKAN database upgrade.

For details, see [docs/term_translation_migrations.md](docs/term_translation_migrations.md).

Quick commands:

```bash
# Check migration status
docker exec <ckan-container> ckan gdi-userportal translations status

# Run all pending migrations manually
docker exec <ckan-container> ckan gdi-userportal translations migrate
```

## Search indexing

The Solr fields of a dataset and the free-text field are derived from the dataset schema and the `solr` keys of its
fields. Which fields are searched as free text, how translated labels get into the index and what to run after a
change are described in the profile packs README, sections "What the indexing writes" and "Searching".

After a change to the indexing or to the translations, rebuild the search index:

```bash
docker exec <ckan-container> ckan -c /srv/app/ckan.ini search-index rebuild
```

## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini

The profile pack tests in `ckanext/gdi_userportal/tests/profile_packs` need only PyYAML, SQLAlchemy and pytest; see
the profile packs README, "Running it".

## Releasing a new version of ckanext-gdi-userportal

If ckanext-gdi-userportal should be available on PyPI you can follow these steps to publish a new version:

1. Update the version number in the `setup.py` file. See the
   [version specifiers of the Python packaging guide](https://packaging.python.org/en/latest/specifications/version-specifiers/)
   for how to choose version numbers.

2. Make sure you have the latest version of necessary packages:

       pip install --upgrade setuptools wheel twine

3. Create a source and binary distributions of the new version:

       python setup.py sdist bdist_wheel && twine check dist/*

   Fix any errors you get.

4. Upload the source distribution to PyPI:

       twine upload dist/*

5. Commit any outstanding changes:

       git commit -a
       git push

6. Tag the new release of the project on GitHub with the version number from
   the `setup.py` file. For example if the version number in `setup.py` is
   1.0.0 then do:

       git tag 1.0.0
       git push --tags

## License

This work is licensed under multiple licenses. Because keeping this section up-to-date is challenging, here is a brief summary as of January 2024:

- All original source code is licensed under [Apache-2.0](./LICENSES/Apache-2.0.txt).
- All documentation is licensed under [CC-BY-4.0](./LICENSES/CC-BY-4.0.txt).
- Some configuration and data files are licensed under [CC-BY-4.0](./LICENSES/CC-BY-4.0.txt).
- For more accurate information, check the individual files.
