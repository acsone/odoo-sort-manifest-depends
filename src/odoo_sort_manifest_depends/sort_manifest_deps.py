# SPDX-FileCopyrightText: 2024-present Acsone
#
# SPDX-License-Identifier: MIT

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _generate_depends_sections(dict_depends_by_category: dict[str, list[str]]) -> str:
    new_content = '"depends": ['
    # Define the preferred category order
    category_order = ["Odoo Community", "Odoo Enterprise"]

    # Separate OCA categories (start with "OCA" - includes both "OCA/" and "OCA") and local categories
    oca_categories = []
    local_categories = []
    other_categories = []

    for category in dict_depends_by_category.keys():
        if category.startswith("OCA"):  # Includes both "OCA/" and "OCA"
            oca_categories.append(category)
        elif category not in category_order and category != "Third-party":
            local_categories.append(category)
        else:
            other_categories.append(category)

    # Sort OCA categories alphabetically
    oca_categories.sort()

    # Build the final category order
    final_order = []
    final_order.extend(category_order)
    final_order.extend(oca_categories)
    final_order.append("Third-party")
    final_order.extend(sorted(local_categories))

    # Generate content in the correct order
    for category in final_order:
        if category in dict_depends_by_category:
            deps = dict_depends_by_category[category]
            if deps:
                new_content += (
                    f"\n        # {category}\n        " + ",\n        ".join(f'"{dep}"' for dep in deps) + ","
                )
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


def _fetch_addon_category(addon_name: str, odoo_series: OdooSeries, cache_context) -> tuple[str, str]:
    """Fetch category information for a single addon.

    Args:
        addon_name: Name of the addon to fetch category for
        odoo_series: Odoo series version
        cache_context: Cache context for storing/retrieving cached categories

    Returns:
        tuple: (addon_name, category) where category is either a specific category name,
               DEFAULT_OCA_CATEGORY, or "other" if not found
    """
    category = cache_context.get(addon_name)

    if not category:
        distribution_name = addon_name_to_distribution_name(addon_name, odoo_series).replace("_", "-")
        res = requests.head(f"{OCA_ADDONS_INDEX_URL}{distribution_name}", timeout=REQUEST_TIMEOUT)
        if res:
            category = get_oca_repository_name(addon_name, odoo_series)
            if category:
                cache_context[addon_name] = category
            else:
                # If module is found but not categories
                # keep it out of cache, it is probably a pending PR
                category = DEFAULT_OCA_CATEGORY
        else:
            category = "other"

    return addon_name, category


def _separate_cached_and_uncached_addons(addon_names: list[str], cache_context) -> tuple[dict[str, str], list[str]]:
    """Separate addons into cached and uncached groups.

    Args:
        addon_names: List of addon names to process
        cache_context: Cache context for checking cached categories

    Returns:
        tuple: (cached_addons, uncached_addons) where:
            - cached_addons: Dictionary mapping cached addon names to their categories
            - uncached_addons: List of addon names that need category fetching
    """
    cached_addons = {}
    addons_to_process = []

    for addon_name in addon_names:
        category = cache_context.get(addon_name)
        if category:
            cached_addons[addon_name] = category
        else:
            addons_to_process.append(addon_name)

    return cached_addons, addons_to_process


def _fetch_addons_categories_paralell(
    addon_names: list[str], odoo_series: OdooSeries, cache_context, max_workers: int = 10
) -> dict[str, str]:
    """Fetch categories for uncached addons in parallel.

    Args:
        addon_names: List of uncached addon names to fetch categories for
        odoo_series: Odoo series version
        cache_context: Cache context for storing fetched categories
        max_workers: Maximum number of parallel workers (default: 10)

    Returns:
        dict: Dictionary mapping addon names to their fetched categories
    """
    cached_addons = {}

    if addon_names:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_addon = {
                executor.submit(_fetch_addon_category, addon_name, odoo_series, cache_context): addon_name
                for addon_name in addon_names
            }

            for future in as_completed(future_to_addon):
                addon_name, category = future.result()
                cached_addons[addon_name] = category

    return cached_addons


def _get_addons_categories(
    addon_names: list[str], odoo_series: OdooSeries, cache_context, max_workers: int = 10
) -> dict[str, str]:
    """Get categories for all addons using parallel processing for uncached ones.

    Args:
        addon_names: List of addon names to get categories for
        odoo_series: Odoo series version
        cache_context: Cache context for storing/retrieving categories
        max_workers: Maximum number of parallel workers for uncached addons (default: 10)

    Returns:
        dict: Dictionary mapping all addon names to their categories (cached or fetched)
    """
    cached_addons, addons_to_process = _separate_cached_and_uncached_addons(addon_names, cache_context)
    uncached_results = _fetch_addons_categories_paralell(addons_to_process, odoo_series, cache_context, max_workers)

    cached_addons.update(uncached_results)
    return cached_addons


def _identify_oca_addons(
    addon_names: list[str], odoo_series: OdooSeries, cache: Cache = other_addons_category_cache
) -> tuple[dict[str, list[str]], list[str]]:
    """Identify OCA addons and separate them from other third-party addons.

    Args:
        addon_names: List of addon names to identify
        odoo_series: Odoo series version
        cache: Cache for storing/retrieving addon category information

    Returns:
        tuple: (oca_addons_by_category, other_addons) where:
            - oca_addons_by_category: Dictionary mapping OCA repository names to lists of addon names
            - other_addons: List of non-OCA third-party addon names
    """
    oca_addons_by_category, other_addons = {}, []

    with cache as cache_context:
        cached_addons = _get_addons_categories(addon_names, odoo_series, cache_context)

        # Organize results
        for addon_name, category in cached_addons.items():
            if category == "other":
                other_addons.append(addon_name)
            else:
                oca_addons_by_category.setdefault(category, []).append(addon_name)

    return oca_addons_by_category, other_addons


def get_oca_repository_name(addon_name: str, odoo_series: OdooSeries) -> str | None:
    """Get the OCA repository name for an addon by querying PyPI.

    Args:
        addon_name: Name of the addon to look up
        odoo_series: Odoo series version to match

    Returns:
        str | None: OCA repository name (e.g., 'OCA/repository-name') if found,
                   None if addon is not found or doesn't match the Odoo series

    Note:
        This function makes external HTTP requests to PyPI to fetch
        package metadata and determine the repository name.
    """
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
    """Add OCA addons to categories and separate them from other third-party addons.

    Args:
        categories: Existing dictionary of dependency categories
        other: List of third-party addon names to process
        odoo_series: Odoo series version
        oca_category: Type of OCA categorization ('basic' or 'repository')

    Returns:
        tuple: (updated_categories, remaining_other_addons) where:
            - updated_categories: Categories dictionary with OCA addons added
            - remaining_other_addons: List of non-OCA third-party addons
    """
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
    # Ensure remaining third-party addons are sorted
    other = sorted(other)
    return categories, other


def _collect_dependencies_from_addon(
    addon_obj, local_addons: dict[str, Addon], odoo_series: OdooSeries
) -> tuple[dict, set]:
    """Collect and categorize dependencies from a single addon.

    Args:
        addon_obj: Addon object to process
        local_addons: Dictionary of all local addons
        odoo_series: Odoo series version

    Returns:
        tuple: (dependency_info, third_party_deps) where:
            - dependency_info: Dict with categorized dependencies
            - third_party_deps: Set of third-party dependency names
    """
    dependencies = addon_obj.manifest.depends
    if not dependencies:
        return {}, set()

    odoo_ce, odoo_ee, other = [], [], []
    custom_by_category: dict[str, list[str]] = {}
    third_party_deps = set()

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
            third_party_deps.add(dep)

    dependency_info = {
        "odoo_ce": sorted(odoo_ce),
        "odoo_ee": sorted(odoo_ee),
        "other": sorted(other),
        "custom_by_category": {k: sorted(v) for k, v in custom_by_category.items()},
    }

    return dependency_info, third_party_deps


def _apply_oca_categorization(
    categories: dict[str, list[str]], deps_info: dict, oca_categories: dict[str, str], oca_category: str
) -> dict[str, list[str]]:
    """Apply OCA categorization to dependency categories.

    Args:
        categories: Existing categories dictionary
        deps_info: Dependency info for current addon
        oca_categories: Mapping of addon names to OCA categories
        oca_category: Type of OCA categorization

    Returns:
        Updated categories dictionary with OCA addons categorized
    """
    if not oca_category:
        categories["Third-party"] = deps_info["other"]
        return categories

    oca_addons = []
    other_addons = []

    for dep in deps_info["other"]:
        category = oca_categories.get(dep, "other")
        if category != "other":
            oca_addons.append(dep)
            # Group by OCA category
            if oca_category == "repository":
                categories.setdefault(category, []).append(dep)
            else:
                categories.setdefault(DEFAULT_OCA_CATEGORY, []).append(dep)
        else:
            other_addons.append(dep)

    # Sort OCA categories
    if oca_category == "repository":
        odoo_categories = {"Odoo Community", "Odoo Enterprise"}
        for cat, deps in categories.items():
            if cat not in odoo_categories:
                categories[cat] = sorted(deps)
    elif DEFAULT_OCA_CATEGORY in categories:
        categories[DEFAULT_OCA_CATEGORY] = sorted(categories[DEFAULT_OCA_CATEGORY])

    categories["Third-party"] = sorted(other_addons)
    return categories


def _generate_local_categories(custom_by_category: dict[str, list[str]], project_name: str) -> dict[str, list[str]]:
    """Generate local category dictionary from custom dependencies.

    Args:
        custom_by_category: Custom categorized dependencies
        project_name: Project name for category prefix

    Returns:
        Dictionary of local categories
    """
    local_categories = {}
    for cat, addon_names in custom_by_category.items():
        if cat == NAME_DEFAULT_CATEGORY:
            local_categories[project_name] = sorted(addon_names)
        else:
            local_categories[f"{project_name}/{cat}"] = sorted(addon_names)

    return dict(sorted(local_categories.items()))


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

    # First pass: Collect all third-party dependencies that need OCA identification
    all_third_party_deps = set()
    addon_dependency_info = {}

    for addon_obj in local_addons.values():
        dependency_info, third_party_deps = _collect_dependencies_from_addon(addon_obj, local_addons, odoo_series)
        if dependency_info:
            addon_dependency_info[addon_obj] = dependency_info
            all_third_party_deps.update(third_party_deps)

    # Bulk process all third-party dependencies for OCA identification
    oca_categories = {}
    if oca_category and all_third_party_deps:
        oca_addons_by_category, remaining_other = _identify_oca_addons(list(all_third_party_deps), odoo_series)
        # Create a mapping from addon name to its category
        for category, addons in oca_addons_by_category.items():
            for addon in addons:
                oca_categories[addon] = category
        # Remaining addons stay as "other"
        for addon in remaining_other:
            oca_categories[addon] = "other"

    # Second pass: Update manifests with sorted dependencies
    for addon_obj, deps_info in addon_dependency_info.items():
        manifest_path = addon_obj.manifest_path
        content = manifest_path.read_text()

        # Odoo
        categories = {
            "Odoo Community": deps_info["odoo_ce"],
            "Odoo Enterprise": deps_info["odoo_ee"],
        }

        # Apply OCA categorization
        categories = _apply_oca_categorization(categories, deps_info, oca_categories, oca_category)

        # Local
        local_categories = _generate_local_categories(deps_info["custom_by_category"], project_name)
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
