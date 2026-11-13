<!--
SPDX-FileCopyrightText: 2024 PNED G.I.E.

SPDX-License-Identifier: CC-BY-4.0
-->

<!-- omit in toc -->
# Contributing to CKAN Extension GDI User Portal

Thanks for taking the time to contribute. All types of contributions are welcome. Read the section that matches
your contribution before you start; it makes the review faster for everyone.

> If you like the project but do not have time to contribute, you can still help: star the project, refer to it in
> your project's readme, or mention it to colleagues.

<!-- omit in toc -->
## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [I Have a Question](#i-have-a-question)
- [I Want To Contribute](#i-want-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
  - [Improving The Documentation](#improving-the-documentation)
- [Styleguides](#styleguides)
  - [Commit Messages](#commit-messages)

## Code of Conduct

This project and everyone participating in it is governed by the
[CKAN Extension GDI User Portal Code of Conduct](CODE_OF_CONDUCT.md).
By participating, you are expected to uphold this code. Report unacceptable behaviour privately to the maintainers
of the GDI User Portal, through the GenomicDataInfrastructure organisation on GitHub.

## I Have a Question

Read the [documentation of the GDI User Portal](https://genomicdatainfrastructure.github.io/gdi-userportal-docs/)
first, then search the existing [issues](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/issues).
If neither answers the question, open a [new issue](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/issues/new)
with as much context as you can: what you ran, the CKAN and Python versions, and the output you got.

## I Want To Contribute

> ### Legal Notice
> When contributing to this project, you must agree that you have authored 100% of the content, that you have the
> necessary rights to the content and that the content you contribute may be provided under the project license.

### Reporting Bugs

#### Before Submitting a Bug Report

- Use the latest version.
- Check that the behaviour is a bug and not a configuration or environment problem. The
  [documentation](https://genomicdatainfrastructure.github.io/gdi-userportal-docs/) and the
  [question section](#i-have-a-question) may help.
- Search the [bug label](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/labels/bug)
  for an existing report.
- Collect the traceback, the operating system, the CKAN and Python versions, and your input and output. Note whether
  you can reproduce the problem reliably.

#### How Do I Submit a Good Bug Report?

Do not report security issues in the public issue tracker. Report them privately through a GitHub security advisory
on the repository.

For any other bug, open an [issue](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/issues/new)
that states the expected and the actual behaviour and gives the steps to reproduce it, ideally as a small test case.
Do not label the issue yourself; the maintainers label it. An issue without reproduction steps is marked `needs-repro`
and is not addressed until it is reproduced. A reproduced bug is marked `needs-fix`.

### Suggesting Enhancements

Enhancement suggestions cover new features and smaller improvements. Before you open one:

- Check the [documentation](https://genomicdatainfrastructure.github.io/gdi-userportal-docs/) to see whether a
  configuration option already does it.
- Search the [issues](https://github.com/GenomicDataInfrastructure/gdi-userportal-ckanext-gdi-userportal/issues) and
  comment on an existing suggestion instead of opening a duplicate.
- Make the case for users beyond one deployment. A feature for a small group of users is better kept in a separate plugin.

Open the issue with a clear title, the current behaviour, the behaviour you expect and why it is useful. Screenshots
help when the change is visual.

### Your First Code Contribution

1. Set up a development environment as described in the [README](README.md#developer-installation).
2. Create a branch named `type/short-description`, for example `fix/empty-language-fallback`.
3. Add or change a test for the behaviour you change, then run the tests:

       pytest --ckan-ini=test.ini

   The profile pack tests run without a CKAN database; see the profile packs README, "Running it".
4. Keep the change focused. Several small pull requests are easier to review than one large one.
5. Open a pull request. Describe what changed and why, and how you verified it.

### Improving The Documentation

The documentation lives next to the code: this README, [`CONTRIBUTING.md`](CONTRIBUTING.md), the
[profile packs README](ckanext/gdi_userportal/profile_packs/README.md) and [`docs/`](docs/). Update the document
that describes the behaviour you change, in the same pull request. Keep one place for each fact and link to it from
the others.

## Styleguides

### Commit Messages

Use the semantic commit format, with an imperative summary of at most 72 characters:

    type: short imperative summary

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`. Add a body only when the reason for the change is not
obvious from the summary; the body explains why, not what.
