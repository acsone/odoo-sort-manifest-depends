# SPDX-FileCopyrightText: 2024-present Acsone
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from re import DOTALL, sub

import click
from click import command, option
from diskcache import Cache
from manifestoo_core.addon import Addon, is_addon_dir
from manifestoo_core.core_addons import is_core_ce_addon, is_core_ee_addon
from manifestoo_core.metadata import addon_name_to_distribution_name
from manifestoo_core.odoo_series import OdooSeries
from platformdirs import user_cache_dir
from requests import head

NAME_DEFAULT_CATEGORY = "Default"
OCA_ADDONS_INDEX_URL = "https://wheelhouse.odoo-community.org/oca-simple/"
REQUEST_TIMEOUT = 2  # s

other_addons_category_cache = Cache(user_cache_dir("odoo-sort-manifest-depends", "Acsone"))


def _generate_depends_sections(dict_depends_by_cateogry: dict[str, list[str]]) -> str:
    new_content = '"depends": ['
    for category, deps in dict_depends_by_cateogry.items():
        if deps:
            new_content += f"\n        # {category}\n        " + ",\n        ".join(f'"{dep}"' for dep in deps) + ","
    new_content += "\n    ]"

    return new_content


def _get_addons_by_name(addons_dir: Path) -> dict[str, Addon]:
    local_addons = {}
    for addon_dir in addons_dir.iterdir():
        if not is_addon_dir(addon_dir, allow_not_installable=False):
            continue
        addon_obj = Addon.from_addon_dir(addon_dir, allow_not_installable=False)
        local_addons[addon_dir.name] = addon_obj
    return local_addons


def _identify_oca_addons(addon_names: list[str], odoo_series: OdooSeries) -> tuple[list[str], list[str]]:
    oca_addons, other_addons = [], []

    with other_addons_category_cache as cache:
        for addon_name in addon_names:
            category = cache.get(addon_name)

            if not category:
                distribution_name = addon_name_to_distribution_name(addon_name, odoo_series).replace("_", "-")
                res = head(f"{OCA_ADDONS_INDEX_URL}{distribution_name}", timeout=REQUEST_TIMEOUT)
                if res:
                    category = "oca"
                else:
                    category = "other"
                cache[addon_name] = category

            if category == "oca":
                oca_addons.append(addon_name)
            else:
                other_addons.append(addon_name)

    return oca_addons, other_addons


def do_sorting(addons_dir: Path, odoo_version: str, project_name: str, *, oca_category: bool) -> None:
    """
    Update manifest files to sort dependencies by type, category and then by name.

    This script will sort the dependencies of all manifest files in the given
    directory. We'll get the following groups of dependencies:
        Third-party, Odoo Community, Odoo Enterprise, Local/{module_category}

    The script will also exclude not installable addons from the dependencies.
    """
    odoo_series = OdooSeries(odoo_version)

    local_addons = _get_addons_by_name(addons_dir)

    for addon_obj in local_addons.values():
        dependencies = addon_obj.manifest.depends

        if not dependencies:
            continue

        odoo_ce, odoo_ee, other = [], [], []
        custom_by_category: dict[str, list[str]] = {}
        for dep in dependencies:
            if dep_addon_obj := local_addons.get(dep):
                addons_in_category = custom_by_category.setdefault(
                    dep_addon_obj.manifest.category or NAME_DEFAULT_CATEGORY, []
                )
                addons_in_category.append(dep)
            elif is_core_ce_addon(dep, odoo_series):
                odoo_ce.append(dep)
            elif is_core_ee_addon(dep, odoo_series):
                odoo_ee.append(dep)
            else:
                other.append(dep)

        assert custom_by_category or odoo_ce or odoo_ee or other

        odoo_ce, odoo_ee, other = sorted(odoo_ce), sorted(odoo_ee), sorted(other)

        manifest_path = addon_obj.manifest_path
        content = manifest_path.read_text()

        local_categories = {}
        for cat, addon_names in custom_by_category.items():
            if cat == NAME_DEFAULT_CATEGORY:
                local_categories[project_name] = sorted(addon_names)
            else:
                local_categories[f"{project_name}/{cat}"] = sorted(addon_names)

        # Odoo
        categories = {
            "Odoo Community": odoo_ce,
            "Odoo Enterprise": odoo_ee,
        }

        # Third party
        if oca_category:
            oca, other = _identify_oca_addons(other, odoo_series)
            categories["OCA"] = oca

        categories["Third-party"] = other

        # Local
        local_categories = dict(sorted(local_categories.items()))
        categories.update(local_categories)

        new_depends = _generate_depends_sections(categories)

        pattern = r'"depends":\s*\[([^]]*)\]'
        content = sub(pattern, new_depends, content, flags=DOTALL)
        manifest_path.write_text(content)


@command(
    help="Sort modules dependencies section in odoo addons manifests and group them by"
    " type (Third-party, Odoo Community, Odoo Enterprise, Local) and module category."
)
@option(
    "--local-addons-dir",
    type=click.Path(file_okay=False),
    required=True,
    help="Directory containing manifests to sort",
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
    help="Name of the project, will be the name of category of local addons (default: Local)",
    default="Local",
)
@option(
    "--oca-category",
    is_flag=True,
    help="Add category for third party addons coming from OCA",
)
@option(
    "--reset-cache",
    is_flag=True,
    help="Purge cache used to identify OCA addons",
)
def sort_manifest_deps(
    local_addons_dir: str,
    odoo_version: str,
    project_name: str,
    *,
    oca_category: bool = False,
    reset_cache: bool = False,
) -> None:
    if reset_cache:
        other_addons_category_cache.clear()

    do_sorting(Path(local_addons_dir), odoo_version, project_name, oca_category=oca_category)
