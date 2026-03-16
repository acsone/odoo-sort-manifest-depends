# SPDX-FileCopyrightText: 2024-present Acsone
#
# SPDX-License-Identifier: MIT

import tempfile
from unittest.mock import MagicMock, patch

import pytest
from diskcache import Cache

from odoo_sort_manifest_depends.sort_manifest_deps import (
    DEFAULT_OCA_CATEGORY,
    OdooSeries,
    _identify_oca_addons,
)


@pytest.fixture
def test_cache():
    """Create a temporary cache for testing"""
    cache_dir = tempfile.mkdtemp()
    cache = Cache(cache_dir)
    yield cache
    cache.close()


def test_cache_oca_addon_with_repository(test_cache):
    """Test that OCA addons with identifiable repository are cached correctly"""
    addon_names = ["test_addon_repo"]
    odoo_series = OdooSeries("16.0")

    with (
        patch("odoo_sort_manifest_depends.sort_manifest_deps.requests.head") as mock_head,
        patch("odoo_sort_manifest_depends.sort_manifest_deps.get_oca_repository_name") as mock_get_repo,
    ):
        # Mock: addon found in OCA wheelhouse
        mock_head.return_value = MagicMock(status_code=200)
        # Mock: repository identified
        mock_get_repo.return_value = "OCA/server-tools"

        oca_addons, other_addons = _identify_oca_addons(addon_names, odoo_series, cache=test_cache)

        # Should be categorized as OCA/server-tools
        assert "OCA/server-tools" in oca_addons
        assert "test_addon_repo" in oca_addons["OCA/server-tools"]
        assert "test_addon_repo" not in other_addons

        # Should be cached
        with test_cache as cache:
            assert cache.get("test_addon_repo") == "OCA/server-tools"


def test_cache_oca_addon_without_repository(test_cache):
    """Test that OCA addons without identifiable repository fall back to default OCA category"""
    addon_names = ["test_addon_no_repo"]
    odoo_series = OdooSeries("16.0")

    with (
        patch("odoo_sort_manifest_depends.sort_manifest_deps.requests.head") as mock_head,
        patch("odoo_sort_manifest_depends.sort_manifest_deps.get_oca_repository_name") as mock_get_repo,
    ):
        # Mock: addon found in OCA wheelhouse
        mock_head.return_value = MagicMock(status_code=200)
        # Mock: repository NOT identified (returns None)
        mock_get_repo.return_value = None

        oca_addons, other_addons = _identify_oca_addons(addon_names, odoo_series, cache=test_cache)

        # Should fall back to default OCA category
        assert DEFAULT_OCA_CATEGORY in oca_addons
        assert "test_addon_no_repo" in oca_addons[DEFAULT_OCA_CATEGORY]
        assert "test_addon_no_repo" not in other_addons

        # Should be cached with default OCA category
        with test_cache as cache:
            assert cache.get("test_addon_no_repo") == DEFAULT_OCA_CATEGORY


def test_cache_non_oca_addon(test_cache):
    """Test that non-OCA addons are not cached and go to other_addons"""
    addon_names = ["test_non_oca"]
    odoo_series = OdooSeries("16.0")

    with patch("odoo_sort_manifest_depends.sort_manifest_deps.requests.head") as mock_head:
        # Mock: addon NOT found in OCA wheelhouse
        mock_head.return_value = None

        oca_addons, other_addons = _identify_oca_addons(addon_names, odoo_series, cache=test_cache)

        # Should be in other_addons
        assert "test_non_oca" in other_addons
        assert "test_non_oca" not in [addon for addons in oca_addons.values() for addon in addons]

        # Should NOT be cached
        with test_cache as cache:
            assert cache.get("test_non_oca") is None


def test_cache_reuse(test_cache):
    """Test that cached values are reused on subsequent calls"""
    addon_names = ["test_addon_reuse"]
    odoo_series = OdooSeries("16.0")

    with (
        patch("odoo_sort_manifest_depends.sort_manifest_deps.requests.head") as mock_head,
        patch("odoo_sort_manifest_depends.sort_manifest_deps.get_oca_repository_name") as mock_get_repo,
    ):
        # First call: addon found in OCA wheelhouse with repository
        mock_head.return_value = MagicMock(status_code=200)
        mock_get_repo.return_value = "OCA/server-tools"

        oca_addons1, _ = _identify_oca_addons(addon_names, odoo_series, cache=test_cache)
        assert "OCA/server-tools" in oca_addons1

        # Second call: mock should not be called again (cached)
        mock_head.reset_mock()
        mock_get_repo.reset_mock()

        oca_addons2, _ = _identify_oca_addons(addon_names, odoo_series, cache=test_cache)

        # Should use cached value
        assert "OCA/server-tools" in oca_addons2
        mock_head.assert_not_called()
        mock_get_repo.assert_not_called()


def test_cache_eviction(test_cache):
    """Test that cache entries can be evicted"""
    addon_names = ["test_addon_evict"]
    odoo_series = OdooSeries("16.0")

    with (
        patch("odoo_sort_manifest_depends.sort_manifest_deps.requests.head") as mock_head,
        patch("odoo_sort_manifest_depends.sort_manifest_deps.get_oca_repository_name") as mock_get_repo,
    ):
        # Addon found in OCA wheelhouse but no repository identified
        mock_head.return_value = MagicMock(status_code=200)
        mock_get_repo.return_value = None

        # First identification
        _identify_oca_addons(addon_names, odoo_series, cache=test_cache)

        # Should be cached with default OCA
        with test_cache as cache:
            cached_value = cache.get("test_addon_evict")
            assert cached_value == DEFAULT_OCA_CATEGORY

        # Clear the cache to test eviction behavior
        test_cache.clear()

        # Cache should be empty now
        with test_cache as cache:
            assert cache.get("test_addon_evict") is None
