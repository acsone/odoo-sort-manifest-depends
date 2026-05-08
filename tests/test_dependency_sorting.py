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
        def mock_identify_oca_addons(addon_names, odoo_series, cache=None):  # noqa: ARG001
            return {"OCA/zzz-last": ["zebra_dep"], "OCA/aaa-first": ["alpha_dep"]}, []

        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._identify_oca_addons",
            side_effect=mock_identify_oca_addons,
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
        def mock_identify_oca_addons(addon_names, odoo_series, cache=None):  # noqa: ARG001
            return {"OCA/server-auth": ["server-auth"], "OCA/queue": ["queue"]}, []

        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._identify_oca_addons",
            side_effect=mock_identify_oca_addons,
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
        def mock_identify_oca_addons(addon_names, odoo_series, cache=None):  # noqa: ARG001
            return {}, addon_names  # All are third-party

        with patch(
            "src.odoo_sort_manifest_depends.sort_manifest_deps._identify_oca_addons",
            side_effect=mock_identify_oca_addons,
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
