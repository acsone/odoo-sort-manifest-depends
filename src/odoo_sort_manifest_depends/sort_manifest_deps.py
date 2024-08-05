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


def _generate_depends_sections(dict_depends_by_cateogry):
    new_content = '"depends": ['
    for category, deps in dict_depends_by_cateogry.items():
        if deps:
            new_content += f"\n        # {category}\n        " + ",\n        ".join(f'"{dep}"' for dep in deps) + ","
    new_content += "\n    ]"

    return new_content


def do_sorting(addons_dir, odoo_version):
    """
    Update manifest files to sort dependencies by typa and then by name.

    This script will sort the dependencies of all manifest files in the given
    directory. We'll get 4 groups of dependencies:
        Custom, Odoo community, Odoo enterprise and Others.

    The script will also exclude not installable addons from the dependencies.
    """
    odoo_version = OdooSeries(odoo_version)
    addons = listdir(addons_dir)
    for addon_name in addons:
        addon_dir = Path(join(addons_dir, addon_name))

        if not is_addon_dir(addon_dir, allow_not_installable=False):
            continue

        addon_obj = Addon.from_addon_dir(addon_dir, allow_not_installable=False)
        dependencies = addon_obj.manifest.depends

        odoo_ce, odoo_ee, other, custom = [], [], [], []
        for dep in dependencies:
            if dep in addons:
                custom.append(dep)
            elif is_core_ce_addon(dep, odoo_version):
                odoo_ce.append(dep)
            elif is_core_ee_addon(dep, odoo_version):
                odoo_ee.append(dep)
            else:
                other.append(dep)

        if not (custom or odoo_ce or odoo_ee or other):
            continue

        custom, odoo_ce, odoo_ee, other = sorted(custom), sorted(odoo_ce), sorted(odoo_ee), sorted(other)

        manifest_path = addon_obj.manifest_path
        with open(manifest_path) as f:
            content = f.read()

        categories = {
            "Odoo Community": odoo_ce,
            "Odoo Enterprise": odoo_ee,
            "Others (OCA,Shopinvader,...)": other,
            "Local": custom,
        }

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
def sort_manifest_deps(local_addons_dir, odoo_version):
    do_sorting(local_addons_dir, odoo_version)
