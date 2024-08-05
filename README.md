# odoo-sort-manifest-depends

[![PyPI - Version](https://img.shields.io/pypi/v/odoo-sort-manifest-depends.svg)](https://pypi.org/project/odoo-sort-manifest-depends)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/odoo-sort-manifest-depends.svg)](https://pypi.org/project/odoo-sort-manifest-depends)

-----

## Table of Contents

- [Installation](#installation)
- [License](#license)

## Installation

```console
pip install odoo-sort-manifest-depends
```

## Pre-commit hook

```yaml
  - repo: https://github.com/acsone/odoo-sort-manifest-depends
    rev: master
    hooks:
      - id: odoo-sort-manifest-depends
        args:
          [
            --local-addons-dir=./odoo/addons/,
            --odoo-version=16.0,
            --project-name=MyProject,
          ]
```

## License

`odoo-sort-manifest-depends` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
