# SPDX-FileCopyrightText: 2024-present Acsone
#
# SPDX-License-Identifier: MIT

import re
from pathlib import Path

import click
import requests
from click import command, option
from diskcache import Cache
from manifestoo_core.addon import Addon, is_addon_dir
from manifestoo_core.core_addons import is_core_ce_addon, is_core_ee_addon
from manifestoo_core.metadata import addon_name_to_distribution_name
from manifestoo_core.odoo_series import OdooSeries
from mousebender import simple
from packaging.metadata import parse_email
from packaging.specifiers import SpecifierSet
from packaging.utils import parse_wheel_filename
from platformdirs import user_cache_dir

NAME_DEFAULT_CATEGORY = "Default"
OCA_ADDONS_INDEX_URL = "https://wheelhouse.odoo-community.org/oca-simple/"
REQUEST_TIMEOUT = 2  # s

PYPI_SIMPLE_INDEX_URL = "https://pypi.org/simple/"
PAGE_NOT_FOUND = 404
DEFAULT_OCA_CATEGORY = "OCA"

other_addons_category_cache = Cache(user_cache_dir("odoo-sort-manifest-depends", "Acsone", "1.0"))


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


def _identify_oca_addons(addon_names: list[str], odoo_series: OdooSeries) -> tuple[dict[str, list[str]], list[str]]:
    oca_addons_by_category, other_addons = {}, []

    with other_addons_category_cache as cache:
        for addon_name in addon_names:
            category = cache.get(addon_name)

            if not category:
                distribution_name = addon_name_to_distribution_name(addon_name, odoo_series).replace("_", "-")
                res = requests.head(f"{OCA_ADDONS_INDEX_URL}{distribution_name}", timeout=REQUEST_TIMEOUT)
                if res:
                    category = get_oca_repository_name(addon_name, odoo_series) or DEFAULT_OCA_CATEGORY
                    cache[addon_name] = category
                else:
                    category = "other"

            if category == "other":
                other_addons.append(addon_name)
            else:
                oca_addons_by_category.setdefault(category, []).append(addon_name)

    return oca_addons_by_category, other_addons


def get_oca_repository_name(addon_name: str, odoo_series: OdooSeries) -> str | None:
    specifier = SpecifierSet(f"=={odoo_series.value}.*")
    distribution_name = addon_name_to_distribution_name(addon_name, odoo_series)
    # get avaialble releases
    project_url = simple.create_project_url(PYPI_SIMPLE_INDEX_URL, distribution_name)
    response = requests.get(project_url, headers={"Accept": simple.ACCEPT_JSON_V1}, timeout=REQUEST_TIMEOUT)
    if response.status_code == PAGE_NOT_FOUND:
        # project not found
        return None
    response.raise_for_status()
    content_type = response.headers["Content-Type"]
    project_details = simple.parse_project_details(response.text, content_type, distribution_name)
    # find the first version that matches the requested Odoo version;
    # we assume all releases come from the same repo for a given Odoo series
    for file in project_details["files"]:
        if file.get("yanked"):
            continue
        filename = file["filename"]
        if not filename.endswith(".whl"):
            continue
        _, version, _, _ = parse_wheel_filename(filename)
        if specifier.contains(version, prereleases=True):
            # found a release that matches the requested Odoo version
            break
    else:
        # no release found that matches the requested Odoo version
        return None

    if not file.get("data-dist-info-metadata"):
        return None
    metadata_url = file["url"] + ".metadata"
    response = requests.get(metadata_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    home_page = re.search("OCA/.*", parse_email(response.text)[0].get("home_page"))

    return home_page.group() if home_page else None


def _add_oca_categories(
    categories: dict[str, list[str]], other: list[str], odoo_series: OdooSeries, oca_category: str
) -> tuple[dict[str, list[str]], list[str]]:
    oca_addons_by_category, other = _identify_oca_addons(other, odoo_series)
    if oca_category == "repository":
        for category, oca_addons in {
            key: sorted(value) for key, value in sorted(oca_addons_by_category.items())
        }.items():
            categories[category] = oca_addons
    else:
        # oca category == 'basic'
        categories[DEFAULT_OCA_CATEGORY] = sorted(
            [oca_addon for oca_addons in oca_addons_by_category.values() for oca_addon in oca_addons]
        )
    return categories, other


def do_sorting(addons_dir: Path, odoo_version: str, project_name: str, *, oca_category: str) -> None:
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

        if oca_category:
            categories, other = _add_oca_categories(categories, other, odoo_series, oca_category)

        categories["Third-party"] = other

        # Local
        local_categories = dict(sorted(local_categories.items()))
        categories.update(local_categories)

        new_depends = _generate_depends_sections(categories)

        pattern = r'"depends":\s*\[([^]]*)\]'
        content = re.sub(pattern, new_depends, content, flags=re.DOTALL)
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
    type=click.Choice(["basic", "repository"], case_sensitive=False),
    help="Add category for third party addons coming from OCA. "
    "If 'basic': category is set to 'OCA'. "
    "If 'repository': category is set as 'OCA/<repository_name>', "
    "if the repository can not be identified, it falls into the default 'OCA' category.",
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
    oca_category: str,
    *,
    reset_cache: bool = False,
) -> None:
    if reset_cache:
        other_addons_category_cache.clear()
    elif other_addons_category_cache:
        # Remove addons from cache that have 'oca_category_repo_not_found' as category
        with other_addons_category_cache as cache:
            # 'oca' is for retrocompatibility with cache created in versions < v1.4
            cache.evict(DEFAULT_OCA_CATEGORY)
            cache.evict("oca")

    do_sorting(Path(local_addons_dir), odoo_version, project_name, oca_category=oca_category)
