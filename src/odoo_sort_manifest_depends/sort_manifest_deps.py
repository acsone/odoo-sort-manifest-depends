# SPDX-FileCopyrightText: 2024-present AnizR
#
# SPDX-License-Identifier: MIT

import os
import re
from ast import literal_eval

import click

MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py", "__terp__.py")


class NoManifestFoundError(Exception):
    pass


def _get_manifest_path(addon_dir):
    for manifest_name in MANIFEST_NAMES:
        manifest_path = os.path.join(addon_dir, manifest_name)
        if os.path.isfile(manifest_path):
            return manifest_path


def _read_manifest(addon_dir):
    manifest_path = _get_manifest_path(addon_dir)
    if not manifest_path:
        msg = f"No Odoo manifest found in {addon_dir}"
        raise NoManifestFoundError(msg)
    with open(manifest_path) as mf:
        return literal_eval(mf.read())


def _get_oca_addon_in_requirements(requirement_file):
    """
    Return the addon names in the requirements file.
    """
    oca_addons = []
    with open(requirement_file) as f:
        for line in f:
            if regex_match := re.search(r"^odoo-addon-(.*?)(?:==| @)", line):
                module_name = regex_match.group(1)
                module_name = module_name.replace("-", "_")
                oca_addons.append(module_name)
    return oca_addons


def _generate_depends_sections(dict_depends_by_cateogry):
    new_content = '"depends": ['
    for category, deps in dict_depends_by_cateogry.items():
        if deps:
            new_content += f"\n        # {category}\n        " + ",\n        ".join(f'"{dep}"' for dep in deps) + ","
    new_content += "\n    ]"

    return new_content


def do_sorting(addons_dir, requirements_file):
    """
    Update manifest files to sort dependencies by typa and then by name.

    This script will sort the dependencies of all manifest files in the given
    directory. We'll get 3 groups of dependencies: Custom, OCA and Others.

    The script will also exclude not installable addons from the dependencies.
    """
    oca_addons = _get_oca_addon_in_requirements(requirements_file)
    addons = os.listdir(addons_dir or ".")
    for addon in addons:
        addon_dir = os.path.join(addons_dir, addon)
        try:
            manifest = _read_manifest(addon_dir)
        except NoManifestFoundError:
            continue

        if not manifest.get("installable", True):
            continue
        dependencies = manifest.get("depends", [])

        custom, oca, other = [], [], []
        for dep in dependencies:
            if dep in addons:
                custom.append(dep)
            elif dep in oca_addons:
                oca.append(dep)
            else:
                other.append(dep)

        if not (custom or oca or other):
            continue

        custom, oca, other = sorted(custom), sorted(oca), sorted(other)

        manifest_path = _get_manifest_path(addon_dir)
        with open(manifest_path) as f:
            content = f.read()

        categories = {
            "Custom": custom,
            "OCA": oca,
            "Others": other,
        }

        new_content = _generate_depends_sections(categories)

        pattern = r'"depends":\s*\[([^]]*)\]'
        content = re.sub(pattern, new_content, content, flags=re.DOTALL)
        with open(manifest_path, "w") as f:
            f.write(content)


@click.command(help="Sort modules dependencies section in odoo addon's manifest")
@click.option(
    "--requirements-file",
    type=click.Path(dir_okay=False),
    required=True,
    help="Requirements file to use to identify addons",
)
@click.option(
    "--addons-dir",
    type=click.Path(file_okay=False),
    required=True,
    help="Repository containing manifests to sort",
)
def sort_manifest_deps(requirements_file, addons_dir):
    do_sorting(addons_dir, requirements_file)
