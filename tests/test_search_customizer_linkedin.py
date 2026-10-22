"""Tests for src/job_manager/linkedin/search_customizer_linkedin.py"""

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from src.job_manager.linkedin.search_customizer_linkedin import SearchCustomizer

MODULE = "src.job_manager.linkedin.search_customizer_linkedin"


@pytest.fixture
def mock_page():
    page = AsyncMock()
    return page


@pytest.fixture
def customizer(mock_page):
    sc = SearchCustomizer(mock_page)
    sc.set_advanced_search_params(
        {
            "positions": ["Software Engineer", "Python Developer"],
            "locations": ["Germany"],
            "remote": True,
            "hybrid": True,
            "onsite": False,
            "experience_level": {"entry": True, "mid_senior_level": True, "director": False},
            "job_types": {"full_time": True, "contract": False, "internship": True},
            "date": {"24_hours": True, "week": False},
            "apply_once_at_company": True,
            "company_blacklist": ["Wayfair", "Crossover"],
            "title_blacklist": ["word1", "word2"],
            "location_blacklist": ["Brazil"],
        }
    )
    return sc


# ---------------------------------------------------------------------------
# set_advanced_search_params / is_job_blacklisted (base class, exercised here)
# ---------------------------------------------------------------------------


class TestSetAdvancedSearchParams:
    def test_sets_positions_and_locations(self, customizer):
        assert customizer.positions == ["Software Engineer", "Python Developer"]
        assert customizer.locations == ["Germany"]

    def test_sets_work_location_flags(self, customizer):
        assert customizer.remote is True
        assert customizer.hybrid is True
        assert customizer.onsite is False

    def test_sets_experience_level(self, customizer):
        assert customizer.experience_level["entry"] is True
        assert customizer.experience_level["director"] is False

    def test_sets_job_types(self, customizer):
        assert customizer.job_types["full_time"] is True
        assert customizer.job_types["contract"] is False

    def test_sets_date_posted(self, customizer):
        assert customizer.date_posted["24_hours"] is True
        assert customizer.date_posted["week"] is False

    def test_sets_blacklists(self, customizer):
        assert "Wayfair" in customizer.company_blacklist
        assert "word1" in customizer.title_blacklist
        assert "Brazil" in customizer.location_blacklist


class TestSearchDebugHelpers:
    def test_format_linkedin_keyword_query_quotes_and_ors_positions(self, mock_page):
        sc = SearchCustomizer(mock_page)
        sc.positions = ["CTO", "Chief Technology Officer", " Technical Manager ", ""]
        assert (
            sc.format_linkedin_keyword_query()
            == '"CTO" OR "Chief Technology Officer" OR "Technical Manager"'
        )


class TestIsJobBlacklisted:
    def test_blacklisted_company(self, customizer):
        assert customizer.is_job_blacklisted("Engineer", "Wayfair", "Germany") is True

    def test_blacklisted_company_case_insensitive(self, customizer):
        assert customizer.is_job_blacklisted("Engineer", "wayfair", "Germany") is True

    def test_blacklisted_title(self, customizer):
        assert customizer.is_job_blacklisted("word1 Developer", "Google", "Germany") is True

    def test_blacklisted_location(self, customizer):
        assert customizer.is_job_blacklisted("Engineer", "Google", "Brazil") is True

    def test_not_blacklisted(self, customizer):
        assert customizer.is_job_blacklisted("Data Scientist", "Amazon", "Germany") is False

    def test_partial_title_match(self, customizer):
        assert customizer.is_job_blacklisted("Senior word2 Engineer", "Amazon", "Germany") is True


# ---------------------------------------------------------------------------
# set_search_params (orchestration)
# ---------------------------------------------------------------------------


class TestSetSearchParams:
    @pytest.mark.asyncio
    async def test_navigates_to_search_url(self, customizer, mock_page):
        with (
            patch(f"{MODULE}.LINKEDIN_RECOMMENDED_JOBS_MODE", False),
            patch(f"{MODULE}.LINKEDIN_TOP_APPLICANT_JOBS_MODE", False),
            patch(f"{MODULE}.async_pause"),
        ):
            await customizer.set_search_params()

        mock_page.goto.assert_called_once_with(
            customizer.build_search_url(), wait_until="domcontentloaded"
        )

    @pytest.mark.asyncio
    async def test_recommended_jobs_mode_ignores_position_search(self, customizer, mock_page):
        with (
            patch(f"{MODULE}.LINKEDIN_RECOMMENDED_JOBS_MODE", True),
            patch(f"{MODULE}.LINKEDIN_TOP_APPLICANT_JOBS_MODE", False),
            patch(f"{MODULE}.async_pause", new_callable=AsyncMock),
        ):
            await customizer.set_search_params()

        mock_page.goto.assert_called_once_with(
            "https://www.linkedin.com/jobs/collections/recommended/",
            wait_until="domcontentloaded",
        )

    @pytest.mark.asyncio
    async def test_top_applicant_jobs_mode_ignores_position_search(self, customizer, mock_page):
        with (
            patch(f"{MODULE}.LINKEDIN_RECOMMENDED_JOBS_MODE", False),
            patch(f"{MODULE}.LINKEDIN_TOP_APPLICANT_JOBS_MODE", True),
            patch(f"{MODULE}.async_pause", new_callable=AsyncMock),
        ):
            await customizer.set_search_params()

        mock_page.goto.assert_called_once_with(
            "https://www.linkedin.com/jobs/collections/top-applicant/",
            wait_until="domcontentloaded",
        )

    def test_build_search_url_encodes_keywords_location_and_filters(self, customizer):
        with patch(f"{MODULE}.EASY_APPLY_ONLY_MODE", True):
            url = customizer.build_search_url()

        query = parse_qs(urlparse(url).query)
        assert url.startswith("https://www.linkedin.com/jobs/search/?")
        assert query["keywords"] == ['"Software Engineer" OR "Python Developer"']
        assert query["location"] == ["Germany"]
        assert query["f_WT"] == ["2,3"]
        assert query["f_E"] == ["2,4"]
        assert query["f_JT"] == ["F,I"]
        assert query["f_TPR"] == ["r86400"]
        assert query["f_AL"] == ["true"]

    def test_build_search_url_uses_first_location_and_omits_easy_apply(self, customizer):
        customizer.locations = ["Europe", "United States"]
        customizer.date_posted = {"all_time": True}
        with patch(f"{MODULE}.EASY_APPLY_ONLY_MODE", False):
            query = parse_qs(urlparse(customizer.build_search_url()).query)

        assert query["location"] == ["Europe"]
        assert "f_AL" not in query
        assert "f_TPR" not in query

    @pytest.mark.asyncio
    async def test_raises_on_page_navigation_error(self, customizer, mock_page):
        mock_page.goto.side_effect = Exception("network error")
        with (
            patch(f"{MODULE}.LINKEDIN_RECOMMENDED_JOBS_MODE", False),
            patch(f"{MODULE}.LINKEDIN_TOP_APPLICANT_JOBS_MODE", False),
            patch(f"{MODULE}.async_pause"),
        ):
            with pytest.raises(Exception, match="network error"):
                await customizer.set_search_params()
