<!--
SPDX-FileCopyrightText: 2024 PNED G.I.E.

SPDX-License-Identifier: CC-BY-4.0
-->

[![REUSE status](https://api.reuse.software/badge/github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal)](https://api.reuse.software/info/github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal)
![example workflow](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/actions/workflows/main.yml/badge.svg)
![example workflow](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/actions/workflows/release.yml/badge.svg)
![example workflow](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/actions/workflows/test.yml/badge.svg)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=GenomicDataInfrastructure_gdi-userportal-ckanext-gdi-userportal&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=GenomicDataInfrastructure_gdi-userportal-ckanext-gdi-userportal)
[![GitHub contributors](https://img.shields.io/github/contributors/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal)](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/graphs/contributors)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](code_of_conduct.md)

# ckanext-gdi-userportal

**TODO:** Put a description of your extension here:  What does it do? What features does it have? Consider including some screenshots or embedding a video!


## Requirements

**TODO:** For example, you might want to mention here which versions of CKAN this
extension works with.

If your extension works across different versions you can add the following table:

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.9             | not tested    |
| 2.10            | yes           |

Suggested values:

* "yes"
* "not tested" - I can't think of a reason why it wouldn't work
* "not yet" - there is an intention to get it working
* "no"


## Installation

**TODO:** Add any additional install steps to the list below.
   For example installing any non-Python dependencies or adding any required
   config settings.

To install ckanext-gdi-userportal:

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

    git clone https://github.com/GenomicDataInfrastructure/ckanext-gdi-userportal.git
    cd ckanext-gdi_userportal
    pip install -e .
	pip install -r requirements.txt

3. Add `gdi_userportal` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

     sudo service apache2 reload


## Config settings

None at present

**TODO:** Document any optional config settings here. For example:

	# The minimum number of hours to wait before re-checking a resource
	# (optional, default: 24).
	ckanext.gdi_userportal.some_setting = some_default_value


## Developer installation

To install ckanext-gdi-userportal for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/GenomicDataInfrastructure/ckanext-gdi-userportal.git
    cd ckanext-gdi-userportal
    python setup.py develop
    pip install -r dev-requirements.txt


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini


## Releasing a new version of ckanext-gdi-userportal

If ckanext-gdi-userportal should be available on PyPI you can follow these steps to publish a new version:

1. Update the version number in the `setup.py` file. See [PEP 440](http://legacy.python.org/dev/peps/pep-0440/#public-version-identifiers) for how to choose version numbers.

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

This work is licensed under multiple licences. Because keeping this section up-to-date is challenging, here is a brief summary as of January 2024:

- All original source code is licensed under [Apache-2.0](./LICENSES/Apache-2.0.txt).
- All documentation is licensed under [CC-BY-4.0](./LICENSES/CC-BY-4.0.txt).
- Some configuration and data files are licensed under [CC-BY-4.0](./LICENSES/CC-BY-4.0.txt).
- For more accurate information, check the individual files.
