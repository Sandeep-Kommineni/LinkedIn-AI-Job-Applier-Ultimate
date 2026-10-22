"""
This module is used to customize the search parameters for the LinkedIn jobs search.
"""

import argparse
import re
from inspect import isawaitable
from typing import Any, Union
from urllib.parse import urlencode

from playwright.sync_api import Page

from config.app_config import EASY_APPLY_ONLY_MODE
from config.constants import SEARCH_CONFIG_FILE

try:
    from config.app_config import LINKEDIN_RECOMMENDED_JOBS_MODE
except ImportError:
    LINKEDIN_RECOMMENDED_JOBS_MODE = False
try:
    from config.app_config import LINKEDIN_TOP_APPLICANT_JOBS_MODE
except ImportError:
    LINKEDIN_TOP_APPLICANT_JOBS_MODE = False
from config.logger_config import logger

# Import Playwright utilities for enhanced functionality
from src.job_manager.search_customizer import BaseSearchCustomizer
from src.utils.browser_utils import find_elements_safely, get_clean_text
from src.utils.utils import async_pause, load_yaml_file


class SearchCustomizer(BaseSearchCustomizer):
    RECOMMENDED_JOBS_URL = "https://www.linkedin.com/jobs/collections/recommended/"
    TOP_APPLICANT_JOBS_URL = "https://www.linkedin.com/jobs/collections/top-applicant/"

    def __init__(self, page: Union[Page, Any]):
        super().__init__(page)
        logger.info("SearchCustomizer initialized")

    async def _open_recommended_jobs(self) -> None:
        """Navigate to LinkedIn recommended jobs and skip configured position keywords."""
        logger.info("LinkedIn recommended jobs mode enabled; ignoring configured positions")
        await self.page.goto(self.RECOMMENDED_JOBS_URL, wait_until="domcontentloaded")
        await async_pause(2, 3)

    async def _open_top_applicant_jobs(self) -> None:
        """Navigate to LinkedIn Top applicant picks and skip configured position keywords."""
        logger.info("LinkedIn top applicant jobs mode enabled; ignoring configured positions")
        await self.page.goto(self.TOP_APPLICANT_JOBS_URL, wait_until="domcontentloaded")
        await async_pause(2, 3)

    def format_linkedin_keyword_query(self) -> str:
        """Format positions as a LinkedIn boolean keyword query."""
        cleaned_positions = [
            position.strip() for position in self.positions if position and position.strip()
        ]
        return " OR ".join(f'"{position}"' for position in cleaned_positions)

    def build_search_url(self) -> str:
        """Build a LinkedIn job search URL with keywords, location and filters as query params.

        Typing the location into the search box only works when a typeahead suggestion is
        selected, otherwise LinkedIn silently keeps the account's default location.
        """
        params = {"keywords": self.format_linkedin_keyword_query()}
        if self.locations:
            if len(self.locations) > 1:
                logger.warning(
                    f"LinkedIn accepts one location per search, using {self.locations[0]!r}"
                )
            params["location"] = self.locations[0]

        work_types = [
            code
            for enabled, code in ((self.onsite, "1"), (self.remote, "2"), (self.hybrid, "3"))
            if enabled
        ]
        if work_types:
            params["f_WT"] = ",".join(work_types)

        experience_codes = {
            "internship": "1",
            "entry": "2",
            "associate": "3",
            "mid_senior_level": "4",
            "director": "5",
            "executive": "6",
        }
        experience = [
            code for key, code in experience_codes.items() if self.experience_level.get(key)
        ]
        if experience:
            params["f_E"] = ",".join(experience)

        job_type_codes = {
            "full_time": "F",
            "part_time": "P",
            "contract": "C",
            "temporary": "T",
            "volunteer": "V",
            "internship": "I",
            "other": "O",
        }
        job_types = [code for key, code in job_type_codes.items() if self.job_types.get(key)]
        if job_types:
            params["f_JT"] = ",".join(job_types)

        date_codes = {
            "24_hours": "r86400",
            "day_24_hours": "r86400",
            "week": "r604800",
            "month": "r2592000",
        }
        for key, code in date_codes.items():
            if self.date_posted.get(key):
                params["f_TPR"] = code
                break

        if EASY_APPLY_ONLY_MODE:
            params["f_AL"] = "true"

        return "https://www.linkedin.com/jobs/search/?" + urlencode(params)

    async def set_search_params(self):
        """Set search parameters on LinkedIn (async)"""
        logger.info("Starting LinkedIn search parameters setup")

        try:
            if LINKEDIN_RECOMMENDED_JOBS_MODE:
                await self._open_recommended_jobs()
                logger.info("LinkedIn recommended jobs page opened successfully")
                return
            if LINKEDIN_TOP_APPLICANT_JOBS_MODE:
                await self._open_top_applicant_jobs()
                logger.info("LinkedIn Top applicant picks page opened successfully")
                return

            # Open the search with keywords, location and filters encoded in the URL
            search_url = self.build_search_url()
            logger.info(f"Opening LinkedIn search: {search_url}")
            await self.page.goto(search_url, wait_until="domcontentloaded")
            await async_pause(2, 3)

            logger.info("Search parameters successfully set")

        except Exception as e:
            logger.error(f"Error setting search parameters: {e}")
            raise


if __name__ == "__main__":
    """Simple test for SearchCustomizer functionality"""
    import asyncio

    from src.utils.browser_utils import create_playwright_browser, save_browser_session

    # Test configuration
    test_config = {
        "remote": True,
        "hybrid": True,
        "onsite": False,
        "experience_level": {
            "entry": True,
            "associate": True,
            "mid_senior_level": True,
            "director": False,
            "executive": False,
            "internship": False,
        },
        "job_types": {
            "full_time": True,
            "contract": False,
            "part_time": True,
            "temporary": True,
            "volunteer": False,
            "internship": False,
        },
        "date": {"all_time": False, "month": False, "week": False, "24_hours": True},
        "positions": ["Software Engineer", "Python Developer"],
        "locations": ["Germany"],
        "apply_once_at_company": True,
        "company_blacklist": ["wayfair", "Crossover"],
        "title_blacklist": ["word1", "word2"],
        "location_blacklist": ["Brazil"],
    }

    def parse_args():
        parser = argparse.ArgumentParser(description="Debug LinkedIn job search filters safely")
        parser.add_argument(
            "--config",
            action="store_true",
            help="Load config/search_config.yaml instead of the built-in smoke-test config",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximum visible result cards to print",
        )
        parser.add_argument(
            "--pause-seconds",
            type=int,
            default=300,
            help="Seconds to keep the browser open for manual inspection after parsing",
        )
        return parser.parse_args()

    def _canonical_job_url_from_href(href: str | None) -> str:
        if not href:
            return ""

        current_job_match = re.search(r"[?&]currentJobId=(\d+)", href)
        if current_job_match:
            return f"https://www.linkedin.com/jobs/view/{current_job_match.group(1)}"

        view_match = re.search(r"/jobs/view/(\d+)", href)
        if view_match:
            return f"https://www.linkedin.com/jobs/view/{view_match.group(1)}"

        return href

    async def _first_text(element: Any, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                locator = element.locator(selector).first
                if await locator.count() > 0:
                    text = (
                        await locator.inner_text() or await locator.text_content() or ""
                    ).strip()
                    if text:
                        return " ".join(text.split())
            except Exception:
                continue
        return ""

    async def _first_href(element: Any, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                locator = element.locator(selector).first
                if await locator.count() > 0:
                    href = await locator.get_attribute("href")
                    if href:
                        return _canonical_job_url_from_href(href)
            except Exception:
                continue
        return ""

    def _fallback_job_card_fields(text: str) -> tuple[str, str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        filtered = [
            line
            for line in lines
            if line.lower() not in {"promoted", "easy apply", "view job", "actively hiring"}
        ]
        title = filtered[0] if len(filtered) > 0 else ""
        company = filtered[1] if len(filtered) > 1 else ""
        location = filtered[2] if len(filtered) > 2 else ""
        return title, company, location

    def is_applied_job_card_text(text: str) -> bool:
        return any(line.strip().lower() == "applied" for line in text.splitlines())

    async def is_applied_search_result_card(card: Any, full_text: str = "") -> bool:
        """Return True when a visible search result card is marked Applied."""
        selectors = [
            ".job-card-container__footer-job-state",
            ".job-card-container__footer-wrapper",
            "li",
        ]
        for selector in selectors:
            try:
                locator = card.locator(selector)
                if isawaitable(locator):
                    continue
                count = await locator.count()
                for index in range(count):
                    item = locator.nth(index)
                    text = (
                        (await item.inner_text() or await item.text_content() or "").strip().lower()
                    )
                    if text == "applied":
                        return True
            except Exception:
                continue

        return is_applied_job_card_text(full_text)

    async def parse_visible_search_results(page: Any, limit: int = 25) -> list[dict[str, str]]:
        """Parse visible LinkedIn search result cards without opening/applying to jobs."""
        card_selectors = [
            ".scaffold-layout__list [data-view-name='job-card'][data-job-id]",
            ".scaffold-layout__list .job-card-job-posting-card-wrapper[data-job-id]",
            ".scaffold-layout__list div[data-job-id]",
            ".jobs-search-results__list-item",
            ".job-card-container",
            "div[data-job-id]",
        ]
        title_selectors = [
            "a[href*='/jobs/view/']",
            "a[href*='currentJobId=']",
            ".job-card-list__title",
            ".job-card-container__link",
        ]
        company_selectors = [
            ".artdeco-entity-lockup__subtitle",
            ".job-card-container__primary-description",
            "a[href*='/company/']",
        ]
        location_selectors = [
            ".artdeco-entity-lockup__caption",
            ".job-card-container__metadata-item",
            "li-icon[type='map-marker-icon'] ~ span",
        ]
        link_selectors = ["a[href*='/jobs/view/']", "a[href*='currentJobId=']"]

        seen_urls = set()
        results = []
        for selector in card_selectors:
            by = "xpath" if selector.startswith("//") else "css selector"
            cards = await find_elements_safely(page, selector, by)
            if not cards:
                continue

            for card in cards:
                if len(results) >= limit:
                    break
                try:
                    full_text = await get_clean_text(card)
                    is_applied = await is_applied_search_result_card(card, full_text)
                    fallback_title, fallback_company, fallback_location = _fallback_job_card_fields(
                        full_text
                    )
                    url = await _first_href(card, link_selectors)
                    if not url:
                        job_id = await card.get_attribute(
                            "data-job-id"
                        ) or await card.get_attribute("data-occludable-job-id")
                        if job_id:
                            url = f"https://www.linkedin.com/jobs/view/{job_id}"
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)

                    results.append(
                        {
                            "title": await _first_text(card, title_selectors) or fallback_title,
                            "company": await _first_text(card, company_selectors)
                            or fallback_company,
                            "location": await _first_text(card, location_selectors)
                            or fallback_location,
                            "url": url,
                            "skip_reason": "Already applied" if is_applied else "",
                        }
                    )
                except Exception as e:
                    logger.debug(f"Failed parsing visible job card: {e}")

            if results:
                break

        return results

    def load_debug_search_config(use_real_config: bool) -> dict[str, Any]:
        if use_real_config:
            logger.info(f"Loading real search config: {SEARCH_CONFIG_FILE}")
            config = load_yaml_file(SEARCH_CONFIG_FILE)
            if not isinstance(config, dict):
                raise ValueError(f"Search config {SEARCH_CONFIG_FILE} must be a mapping")
            return config
        logger.info("Using built-in smoke-test search config")
        return test_config

    def log_search_results(results: list[dict[str, str]]) -> None:
        logger.info(f"Visible LinkedIn search results parsed: {len(results)}")
        if not results:
            logger.warning("No visible job result cards were parsed")
            return
        for index, job in enumerate(results, start=1):
            skip_prefix = f"[SKIP: {job['skip_reason']}] " if job.get("skip_reason") else ""
            logger.info(
                f"[{index}] {skip_prefix}{job.get('title') or '-'} | "
                f"{job.get('company') or '-'} | "
                f"{job.get('location') or '-'} | "
                f"{job.get('url') or '-'}"
            )

    async def test_search_customizer():
        """Async test function for SearchCustomizer"""
        args = parse_args()
        browser = None
        context = None

        try:
            # Initialize Playwright browser (async)
            browser, context, page = await create_playwright_browser()
            page = page
            logger.info("Playwright browser initialized successfully (async)")

            # Create SearchCustomizer instance
            search_customizer = SearchCustomizer(page)

            # Test parameter setting
            search_customizer.set_advanced_search_params(load_debug_search_config(args.config))
            logger.info("✓ Parameters set successfully")

            # Test blacklist functionality
            if not args.config:
                test_cases = [
                    ("Software Engineer", "Wayfair", "Germany", True),  # Company blacklisted
                    ("Python Developer", "Google", "Brazil", True),  # Location blacklisted
                    ("word1 Developer", "Microsoft", "Germany", True),  # Title blacklisted
                    ("Data Scientist", "Amazon", "Germany", False),  # Not blacklisted
                ]

                for title, company, location, expected in test_cases:
                    result = search_customizer.is_job_blacklisted(title, company, location)
                    status = "✓" if result == expected else "✗"
                    logger.info(
                        f"{status} Blacklist test: {title} at {company} in {location} -> {result}"
                    )

            logger.info("✓ All tests completed successfully")

            # Test async set_search_params
            await search_customizer.set_search_params()
            await async_pause(3, 5)
            results = await parse_visible_search_results(page, limit=args.limit)
            log_search_results(results)

            if args.pause_seconds > 0:
                logger.info(
                    f"Search debug complete. Browser will remain open for {args.pause_seconds} seconds."
                )
                await async_pause(args.pause_seconds, args.pause_seconds)

        except Exception as e:
            logger.error(f"Test failed: {e}")
        finally:
            # Cleanup Playwright resources
            logger.info("Cleaning up Playwright browser resources...")
            try:
                if context:
                    # Save session state before closing (async)
                    await save_browser_session(context)

                if browser:
                    await browser.close()
                    logger.info("Playwright browser closed successfully")
            except Exception as cleanup_error:
                logger.warning(f"Error during Playwright cleanup: {cleanup_error}")

    # Run the async test
    asyncio.run(test_search_customizer())
