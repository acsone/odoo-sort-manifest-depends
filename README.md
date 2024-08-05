# odoo-sort-manifest-depends

## Table of Contents

- [Help](#help)
- [Pre-commit hook](#pre-commit)
- [License](#license)

## Help

```
Usage: odoo-sort-manifest-deps [OPTIONS]

  Sort modules dependencies section in odoo addons manifests

Options:
  --local-addons-dir DIRECTORY  Directory containing manifests to sort
                                [required]
  --odoo-version TEXT           Project's Odoo version (e.g. 16.0)  [required]
  --project-name TEXT           Name of the project, will be the name of
                                category of local addons (default: Local)
  --help                        Show this message and exit.
```


## Pre-commit

```yaml
  - repo: https://github.com/acsone/odoo-sort-manifest-depends
    rev: v1.1
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

`odoo-sort-manifest-depends` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
