# odoo-sort-manifest-depends

## Table of Contents

- [Help](#help)
- [Pre-commit hook](#pre-commit)
- [License](#license)

## Help

```
Usage: odoo-sort-manifest-depends [OPTIONS]

  Sort modules dependencies section in odoo addons manifests and group them by
  type (Third-party, Odoo Community, Odoo Enterprise, Local) and module
  category.

Options:
  --local-addons-dir DIRECTORY  Directory containing manifests to sort
                                [required]
  --odoo-version TEXT           Project's Odoo version (e.g. 16.0)  [required]
  --project-name TEXT           Name of the project, will be the name of
                                category of local addons (default: Local)
  --distinct-oca                Add disctinction for third party addons coming
                                from OCA
  --help                        Show this message and exit.
```

## Using from the command line

This project is distributed on PyPI. The recommended way to run it is with
[pipx](https://github.com/pypa/pipx), with a command like this:

`pipx run odoo-sort-manifest-depends --local-addons-dir=odoo/addons --odoo-version=16.0`

## Using with pre-commit

This project may be used as a [pre-commit](https://pre-commit.com) hook, with an
entry like this in `.pre-commit-config.yml`.

```yaml
  - repo: https://github.com/acsone/odoo-sort-manifest-depends
    rev: v1.x  # see the release page https://github.com/acsone/odoo-sort-manifest-depends/releases
    hooks:
      - id: odoo-sort-manifest-depends
        args:
          [
            --local-addons-dir=./odoo/addons/,
            --odoo-version=16.0,
            --project-name=MyProject,
          ]
```

## Credits

 * [Laurent Mignon](https://github.com/lmignon)
 * [Thomas Binsfeld](https://github.com/ThomasBinsfeld)
 * [Zina Rasoamanana](https://github.com/AnizR)

## License

`odoo-sort-manifest-depends` is distributed under the terms of the
[MIT](https://spdx.org/licenses/MIT.html) license.
