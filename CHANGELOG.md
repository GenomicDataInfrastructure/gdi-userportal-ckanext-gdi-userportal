<!--
SPDX-FileCopyrightText: 2024 PNED G.I.E.

SPDX-License-Identifier: CC-BY-4.0
-->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [v1.3.4] - 2025-04-04

### Changed
- Update translation_utils.py by @Hans-Christian in 43e482f
- chore(deps): update aquasecurity/trivy-action action to v0.28.0 by @Renovate Bot in 0d28b0c
- chore: update CHANGELOG.md by @Bruno Pacheco in dc0ca52


### Fixed
- fix(translations): populate translations with a fallback language by @Mark Janse in 3c36a98




## [v1.3.3] - 2024-10-14

### Changed
* chore(deps): update aquasecurity/trivy-action action to v0.27.0 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/103
* fix: fix bug themes not normalized when searching datasets duplicates and clutter in display by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/105
* chore: index publisher and creator name in solr by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/106

## [v1.3.2] - 2024-10-09

### Changed
* chore(deps): update aquasecurity/trivy-action action to v0.25.0 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/100
* chore(deps): update aquasecurity/trivy-action action to v0.26.0 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/101
* chore(deps): use solr slim image by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/102

## [v1.3.1] - 2024-09-29

### Changed
* feat: Upgrade to DCAT AP 3 by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/99

## [v1.3.0] - 2024-09-14

### Changed
* feat: Flexible datetime scheming by @Markus92 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/90
* feat(scheming): added Dutch translation to all fields for the Scheming by @Markus92 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/91
* feat: make enhanced package search as post by @admy7 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/92
* chore: add error handling and logging to enhanced_package_search by @admy7 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/94

### Removed
* feat(auth): remove Keycloak integration from CKAN and user portal by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/93

## [v1.2.4] - 2024-08-14

### Added
* feat: Enhance creator parsing in DCAT profile and ckan by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/54
* feat: renovate integration by @sehaartuc in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/56
* feat: add Vulnscan by @sehaartuc in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/55
* feat: Enhance creator parsing in DCAT profile and ckan by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/84

### Changed
* chore: change schema to accept multiValues contact points with repeating subfields by @a-nayden in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/51
* chore(deps): update fsfe/reuse-action action to v4 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/61
* chore(deps): update docker/build-push-action action to v6 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/60
* chore(deps): update docker/metadata-action digest to a64d048 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/58
* chore(deps): update docker/login-action digest to 0d4c9c5 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/57
* chore(deps): update oss-review-toolkit/ort-ci-github-action digest to 81698a9 by @LNDS-Sysadmins in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/59
* feat(solr-schema): Add multi-valued creator field with subfields for … by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/89


## [v1.2.3] - 2024-05-23

## Changed
* chore: change schema to accept multiValues contact points with repeating subfields by @a-nayden in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/51

## [v1.2.2] - 2024-04-17

### Fixed
* fix: replace spatial_uri str value by ValueLabel by @brunopacheco1
* ci: fix registry push permissions for releases by @brunopacheco1

## [v1.2.1] - 2024-04-16

### Fixed
* fix: fix empty values handling by @a-nayden in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/47

## [v1.2.0] - 2024-04-16

### Added
* chore: `enhanced_package_show` and `enhanced_package_show`  endpoints by @a-nayden in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/45 as per https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/issues/43

## [v1.1.2] - 2024-04-04

### Removed
* chore!: drop `*_list` endpoints by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/42

### Fixed
* fix: rename deprecated; fix typos by @a-nayden in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/41

## [v1.1.1] - 2024-04-02

### Fixed
* fix: fix dcat ap fields indexation by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/40

## [V1.1.0] - 2024-03-25

### Added
* feat: new endpoint to map urls to labels by @a-nayden in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/37

### Fixed
* fix: replace deprecated typos by @a-nayden in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/37

## [v1.0.1] - 2024-03-01

### Added
* chore: #10 add licenses and copyrights by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/32

### Fixed
* fix(theme-fetcher): handle empty iterable in theme reduction process by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/36

## [v1.0.0] - 2024-01-30

### Added

* Setup CKAN extension for GDI - User Portal by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/1
* Update LICENSE by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/2
* Feature/ckan UI by @admy7 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/3
* Feature/ckan UI by @admy7 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/4
* Create ort.yml by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/8
* Enable OIDC PKCE by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/12
* 14 dynamically load data in frond end by @hcvdwerf in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/15
* Add fields to scheming_package_show by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/16
* Add link to harvest view for sys admins by @inderps in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/20
* Endpoints listing unique values by @admy7 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/22
* check key existence before trying to get the value from a dataset for… by @admy7 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/24
* chore: add CI/CD and changelog by @brunopacheco1 in https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/pull/31
