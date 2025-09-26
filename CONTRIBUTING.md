# Contributing Guide

## Writing release notes

This repo uses the [towncrier](https://github.com/twisted/towncrier) tool for managing release notes.

When submitting a PR, please include a news fragment file in the [unreleased_notes](./unreleased_notes/) folder with the
issue number and an appropriate suffix chosen from the list of `directory` values under each `tool.towncrier.type`
heading in `pyproject.toml`. For example, the file `unreleased_notes/37.feature` would indicate a note for a feature
related to issue number #37.

The valid filename extensions are currently:

* .breaking
* .deprecation
* .feature
* .bugfix
* .refactor
* .doc
* .build

See the [towncrier docs](https://towncrier.readthedocs.io/en/stable/index.html) for more details.

## TODO: Rewrite the below info

Setting Up for Local Development
********************************

1. Fork marshmallow_jsonschema on Github.

::

    $ git clone https://github.com/stretch4x4/marshmallow-jsonschema.git
    $ cd marshmallow_jsonschema

2. Create a virtual environment and install all dependencies

::

    $ make venv

3. Install the pre-commit hooks, which will format and lint your git staged files.

::

    # The pre-commit CLI was installed above
    $ pre-commit install --allow-missing-config


Running tests
*************

To run all tests: ::

    $ pytest

To run syntax checks: ::

    $ tox -e lint

(Optional) To run tests in all supported Python versions in their own virtual environments (must have each interpreter installed): ::

    $ tox
