#!/usr/bin/env python3
"""Tests for dependency sorting and categorization."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from src.odoo_sort_manifest_depends.sort_manifest_deps import do_sorting


def test_category_ordering():
    """Test that categories appear in the correct order."""
    with tempfile.TemporaryDirectory() as temp_dir:
        addons_dir = Path(temp_dir)

        # Create test addon
        test_manifest = addons_dir / "test_addon"
        test_manifest.mkdir()
        (test_manifest / "__init__.py").write_text("")

        manifest_file = test_manifest / "__manifest__.py"
        # Create a second local addon to test local dependencies
        local_addon = addons_dir / "local_addon"
        local_addon.mkdir()
        (local_addon / "__init__.py").write_text("")
        (local_addon / "__manifest__.py").write_text('{"name": "Local Addon", "version": "1.0", "installable": True}')

        manifest_content = """
{
    "name": "Test Addon",
    "version": "1.0",
    "depends": [
        "web", "mail", "zebra_dep", "alpha_dep", "local_addon"
    ],
    "installable": True,
}
"""
        manifest_file.write_text(manifest_content)

        # Mock OCA identification
        def mock_identify_addons(addon_names, odoo_series, cache=None, config_categories=None):  # noqa: ARG001
            return {"OCA/zzz-last": ["zebra_dep"], "OCA/aaa-first": ["alpha_dep"]}, [], {}

        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._identify_addons",
            side_effect=mock_identify_addons,
        ):
            do_sorting(addons_dir, "16.0", "TestProject", oca_category="repository")

            result_content = manifest_file.read_text()

            # Extract category order
            depends_section = result_content.split('"depends":')[1].split("]")[0]
            categories = []
            for line in depends_section.split("\n"):
                if line.strip().startswith("#"):
                    category = line.strip()[2:].strip()
                    categories.append(category)

            # Verify correct ordering (Odoo Enterprise may not be present)
            assert "Odoo Community" in categories
            assert "OCA/aaa-first" in categories
            assert "OCA/zzz-last" in categories
            assert "TestProject" in categories  # Local category

            # Verify Odoo categories come before OCA
            odoo_community_idx = categories.index("Odoo Community")
            first_oca_idx = next(i for i, cat in enumerate(categories) if cat.startswith("OCA/"))
            assert odoo_community_idx < first_oca_idx, "Odoo Community should come before OCA categories"

            # Verify OCA categories come before Local categories
            local_idx = categories.index("TestProject")
            assert first_oca_idx < local_idx, "OCA categories should come before Local categories"

            # Verify OCA categories are sorted alphabetically
            oca_cats = [cat for cat in categories if cat.startswith("OCA/")]
            assert oca_cats == sorted(oca_cats), f"OCA categories not sorted: {oca_cats}"


def test_oca_categories_alphabetical_sorting():
    """Test that OCA categories are sorted alphabetically."""
    with tempfile.TemporaryDirectory() as temp_dir:
        addons_dir = Path(temp_dir)

        # Create test addon
        test_manifest = addons_dir / "test_addon"
        test_manifest.mkdir()
        (test_manifest / "__init__.py").write_text("")

        manifest_file = test_manifest / "__manifest__.py"
        manifest_content = """
{
    "name": "Test Addon",
    "version": "1.0",
    "depends": ["server-auth", "queue", "web"],
    "installable": True,
}
"""
        manifest_file.write_text(manifest_content)

        # Mock OCA identification with intentionally unsorted categories
        def mock_identify_addons(addon_names, odoo_series, cache=None, config_categories=None):  # noqa: ARG001
            return {"OCA/server-auth": ["server-auth"], "OCA/queue": ["queue"]}, [], {}

        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._identify_addons",
            side_effect=mock_identify_addons,
        ):
            do_sorting(addons_dir, "16.0", "TestProject", oca_category="repository")

            result_content = manifest_file.read_text()

            # Extract OCA categories in order
            depends_section = result_content.split('"depends":')[1].split("]")[0]
            oca_categories = []
            for line in depends_section.split("\n"):
                if line.strip().startswith("# OCA/"):
                    category = line.strip()[2:].strip()
                    oca_categories.append(category)

            # Verify alphabetical ordering (queue before server-auth)
            assert oca_categories == [
                "OCA/queue",
                "OCA/server-auth",
            ], f"Expected ['OCA/queue', 'OCA/server-auth'], got {oca_categories}"


def test_dependencies_sorted_within_categories():
    """Test that dependencies are sorted alphabetically within each category."""
    with tempfile.TemporaryDirectory() as temp_dir:
        addons_dir = Path(temp_dir)

        # Create test addon with unsorted dependencies
        test_manifest = addons_dir / "test_addon"
        test_manifest.mkdir()
        (test_manifest / "__init__.py").write_text("")

        manifest_file = test_manifest / "__manifest__.py"
        manifest_content = """
{
    "name": "Test Addon",
    "version": "1.0",
    "depends": ["zebra", "web", "alpha", "mail"],
    "installable": True,
}
"""
        manifest_file.write_text(manifest_content)

        # Mock OCA identification
        def mock_identify_addons(addon_names, odoo_series, cache=None, config_categories=None):  # noqa: ARG001
            return {}, addon_names, {}  # All are third-party

        with patch(
            "odoo_sort_manifest_depends.sort_manifest_deps._identify_addons",
            side_effect=mock_identify_addons,
        ):
            do_sorting(addons_dir, "16.0", "TestProject", oca_category=None)

            result_content = manifest_file.read_text()

            # Verify dependencies are sorted within categories
            depends_section = result_content.split('"depends":')[1].split("]")[0]

            # Extract Odoo Community dependencies
            odoo_community_deps = []
            in_odoo_community = False
            for line in depends_section.split("\n"):
                if "# Odoo Community" in line:
                    in_odoo_community = True
                    continue
                if in_odoo_community and line.strip().startswith("#"):
                    break
                if in_odoo_community and line.strip() and line.strip()[0] == '"':
                    dep = line.strip()[1:-2]  # Remove quotes and comma
                    odoo_community_deps.append(dep)

            # Verify Odoo Community dependencies are sorted
            assert odoo_community_deps == sorted(odoo_community_deps), (
                f"Odoo Community deps not sorted: {odoo_community_deps}"
            )

            # Extract Third-party dependencies
            third_party_deps = []
            in_third_party = False
            for line in depends_section.split("\n"):
                if "# Third-party" in line:
                    in_third_party = True
                    continue
                if in_third_party and line.strip().startswith("#"):
                    break
                if in_third_party and line.strip() and line.strip()[0] == '"':
                    dep = line.strip()[1:-2]  # Remove quotes and comma
                    third_party_deps.append(dep)

            # Verify Third-party dependencies are sorted
            assert third_party_deps == sorted(third_party_deps), f"Third-party deps not sorted: {third_party_deps}"


def test_custom_categories_from_config():
    """Test that custom categories from config file are properly applied."""
    with tempfile.TemporaryDirectory() as temp_dir:
        addons_dir = Path(temp_dir)

        # Mock config categories
        config_categories = {
            "shopinvader_api": "Shopinvader",
            "shopinvader_product": "Shopinvader",
            "custom_module_a": "CustomCategory",
            "custom_module_b": "CustomCategory",
        }

        # Create test addon
        test_manifest = addons_dir / "test_addon"
        test_manifest.mkdir()
        (test_manifest / "__init__.py").write_text("")

        manifest_file = test_manifest / "__manifest__.py"
        manifest_content = """
{
    "name": "Test Addon",
    "version": "1.0",
    "depends": ["shopinvader_api", "shopinvader_product", "custom_module_a", "custom_module_b", "web"],
    "installable": True,
}
"""
        manifest_file.write_text(manifest_content)

        # Mock _load_config_file to return our config
        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._load_config_file",
            return_value=config_categories,
        ):
            # Run sorting
            do_sorting(addons_dir, "16.0", "TestProject", oca_category="repository")

        result_content = manifest_file.read_text()

        # Verify custom categories appear in output
        assert "# Shopinvader" in result_content, "Shopinvader category not found"
        assert "# CustomCategory" in result_content, "CustomCategory not found"

        # Verify Shopinvader addons are in Shopinvader category
        shopinvader_section = result_content.split("# Shopinvader")[1].split("#")[0]
        assert '"shopinvader_api"' in shopinvader_section
        assert '"shopinvader_product"' in shopinvader_section

        # Verify CustomCategory addons are in CustomCategory category
        custom_section = result_content.split("# CustomCategory")[1].split("#")[0]
        assert '"custom_module_a"' in custom_section
        assert '"custom_module_b"' in custom_section


def test_custom_categories_alphabetical_sorting():
    """Test that addons within custom categories are sorted alphabetically."""
    with tempfile.TemporaryDirectory() as temp_dir:
        addons_dir = Path(temp_dir)

        # Mock config categories
        config_categories = {
            "zebra_module": "CustomCat",
            "alpha_module": "CustomCat",
            "middle_module": "CustomCat",
        }

        # Create test addon
        test_manifest = addons_dir / "test_addon"
        test_manifest.mkdir()
        (test_manifest / "__init__.py").write_text("")

        manifest_file = test_manifest / "__manifest__.py"
        manifest_content = """
{
    "name": "Test Addon",
    "version": "1.0",
    "depends": ["zebra_module", "alpha_module", "middle_module"],
    "installable": True,
}
"""
        manifest_file.write_text(manifest_content)

        # Mock _load_config_file to return our config
        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._load_config_file",
            return_value=config_categories,
        ):
            # Run sorting
            do_sorting(addons_dir, "16.0", "TestProject", oca_category="repository")

        result_content = manifest_file.read_text()

        # Extract CustomCat section
        custom_section = result_content.split("# CustomCat")[1].split("#")[0]

        # Extract dependencies in order
        deps = []
        for line in custom_section.split("\n"):
            stripped = line.strip()
            # Match lines that are just a quoted string followed by a comma (dependencies)
            # Not other manifest keys like "installable": True
            if stripped.startswith('"') and stripped.endswith(","):
                # Extract content between quotes (remove both quotes and comma)
                dep = stripped[1:-2]
                # Make sure it's a simple module name (no colon or other characters)
                if ":" not in dep:
                    deps.append(dep)

        # Verify alphabetical ordering
        assert deps == sorted(deps), f"Custom category deps not sorted: {deps}"
        assert deps == ["alpha_module", "middle_module", "zebra_module"]


def test_custom_categories_order():
    """Test that custom categories appear in correct order (after Third-party, before Local)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        addons_dir = Path(temp_dir)

        # Mock config categories
        config_categories = {
            "shopinvader": "Shopinvader",
            "custom_mod": "CustomCat",
        }

        # Create test addon with local addon dependency
        local_addon = addons_dir / "local_addon"
        local_addon.mkdir()
        (local_addon / "__init__.py").write_text("")
        (local_addon / "__manifest__.py").write_text(
            '{"name": "Local", "version": "1.0", "installable": True, "category": "Extra"}'
        )

        test_manifest = addons_dir / "test_addon"
        test_manifest.mkdir()
        (test_manifest / "__init__.py").write_text("")

        manifest_file = test_manifest / "__manifest__.py"
        manifest_content = """
{
    "name": "Test Addon",
    "version": "1.0",
    "depends": ["web", "shopinvader", "custom_mod", "unknown_dep", "local_addon"],
    "installable": True,
}
"""
        manifest_file.write_text(manifest_content)

        # Mock _load_config_file to return our config
        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._load_config_file",
            return_value=config_categories,
        ):
            # Run sorting
            do_sorting(addons_dir, "16.0", "TestProject", oca_category="repository")

        result_content = manifest_file.read_text()

        # Extract category order
        depends_section = result_content.split('"depends":')[1].split("]")[0]
        categories = []
        for line in depends_section.split("\n"):
            if line.strip().startswith("#"):
                category = line.strip()[2:].strip()
                categories.append(category)

        # Verify order: Odoo Community, Third-party, CustomCat, Shopinvader, Local/Extra
        assert "Odoo Community" in categories
        assert "Third-party" in categories
        assert "CustomCat" in categories
        assert "Shopinvader" in categories
        assert "TestProject/Extra" in categories

        # Verify custom categories come after Third-party and before Local
        third_party_idx = categories.index("Third-party")
        custom_cat_idx = categories.index("CustomCat")
        shopinvader_idx = categories.index("Shopinvader")
        local_idx = categories.index("TestProject/Extra")

        assert third_party_idx < custom_cat_idx, "CustomCat should come after Third-party"
        assert third_party_idx < shopinvader_idx, "Shopinvader should come after Third-party"
        assert custom_cat_idx < local_idx, "CustomCat should come before Local"
        assert shopinvader_idx < local_idx, "Shopinvader should come before Local"
