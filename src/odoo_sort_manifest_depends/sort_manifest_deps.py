# SPDX-FileCopyrightText: 2024-present AnizR
#
# SPDX-License-Identifier: MIT

from os import listdir
from os.path import join
from pathlib import Path
from re import DOTALL, sub

from click import Path as click_Path
from click import command, option
from manifestoo_core.addon import Addon, is_addon_dir
from manifestoo_core.core_addons import is_core_ce_addon, is_core_ee_addon
from manifestoo_core.odoo_series import OdooSeries

MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py", "__terp__.py")

NAME_DEFAULT_CATEGORY = "Default"


def _generate_depends_sections(dict_depends_by_cateogry):
    new_content = '"depends": ['
    for category, deps in dict_depends_by_cateogry.items():
        if deps:
            new_content += f"\n        # {category}\n        " + ",\n        ".join(f'"{dep}"' for dep in deps) + ","
    new_content += "\n    ]"

    return new_content


def _generate_dict_addons_obj(addons_dir):
    addons = listdir(addons_dir)
    local_addons = {}
    for addon_name in addons:
        addon_dir = Path(join(addons_dir, addon_name))
        if not is_addon_dir(addon_dir, allow_not_installable=False):
            continue
        addon_obj = Addon.from_addon_dir(addon_dir, allow_not_installable=False)
        local_addons[addon_name] = addon_obj
    return local_addons


def do_sorting(addons_dir, odoo_version, project_name):
    """
    Update manifest files to sort dependencies by typa and then by name.

    This script will sort the dependencies of all manifest files in the given
    directory. We'll get 4 groups of dependencies:
        Custom, Odoo community, Odoo enterprise and Others.

    The script will also exclude not installable addons from the dependencies.
    """
    odoo_version = OdooSeries(odoo_version)

    local_addons = _generate_dict_addons_obj(addons_dir)

    for addon_obj in local_addons.values():
        dependencies = addon_obj.manifest.depends

        odoo_ce, odoo_ee, other = [], [], []
        custom_by_category = {}
        for dep in dependencies:
            if local_addons.get(dep):
                addons_in_category = custom_by_category.setdefault(
                    local_addons.get(dep).manifest.manifest_dict.get("category", NAME_DEFAULT_CATEGORY), []
                )
                addons_in_category.append(dep)
            elif is_core_ce_addon(dep, odoo_version):
                odoo_ce.append(dep)
            elif is_core_ee_addon(dep, odoo_version):
                odoo_ee.append(dep)
            else:
                other.append(dep)

        if not (custom_by_category or odoo_ce or odoo_ee or other):
            continue

        odoo_ce, odoo_ee, other = sorted(odoo_ce), sorted(odoo_ee), sorted(other)

        manifest_path = addon_obj.manifest_path
        with open(manifest_path) as f:
            content = f.read()

        local_categories = {}
        for cat, addon_names in custom_by_category.items():
            if cat == NAME_DEFAULT_CATEGORY:
                local_categories[project_name] = sorted(addon_names)
            else:
                local_categories[f"{project_name}/{cat}"] = sorted(addon_names)

        categories = {
            "Odoo Community": odoo_ce,
            "Odoo Enterprise": odoo_ee,
            "Third-party": other,
        }

        categories.update(local_categories)

        new_content = _generate_depends_sections(categories)

        pattern = r'"depends":\s*\[([^]]*)\]'
        content = sub(pattern, new_content, content, flags=DOTALL)
        with open(manifest_path, "w") as f:
            f.write(content)


@command(help="Sort modules dependencies section in odoo addon's manifest")
@option(
    "--local-addons-dir",
    type=click_Path(file_okay=False),
    required=True,
    help="Repository containing manifests to sort",
)
@option(
    "--odoo-version",
    type=str,
    required=True,
    help="Project's Odoo version (e.g. 16.0)",
)
@option(
    "--project-name",
    type=str,
    help="Name of the project, will be the name of category of local addons",
    default="Local",
)
def sort_manifest_deps(local_addons_dir, odoo_version, project_name):
    do_sorting(local_addons_dir, odoo_version, project_name)
