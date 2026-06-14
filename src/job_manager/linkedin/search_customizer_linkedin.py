"""
This module is used to customize the search parameters for the LinkedIn jobs search.
"""

import argparse
import re
from inspect import isawaitable
from typing import Any, Union

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
try:
    from config.app_config import LINKEDIN_AI_SEARCH_MODE
except ImportError:
    LINKEDIN_AI_SEARCH_MODE = False
from config.logger_config import logger

# Import Playwright utilities for enhanced functionality
from src.job_manager.search_customizer import BaseSearchCustomizer
from src.utils.browser_utils import (
    find_element_safely,
    find_elements_safely,
    get_clean_text,
    safe_click,
    safe_fill,
)
from src.utils.utils import async_pause, load_yaml_file


class SearchCustomizer(BaseSearchCustomizer):
    RECOMMENDED_JOBS_URL = "https://www.linkedin.com/jobs/collections/recommended/"
    TOP_APPLICANT_JOBS_URL = "https://www.linkedin.com/jobs/collections/top-applicant/"

    def __init__(self, page: Union[Page, Any]):
        super().__init__(page)
        self._ai_search_active = False
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
        if len(cleaned_positions) == 1:
            return cleaned_positions[0]
        return " OR ".join(f'"{position}"' for position in cleaned_positions)

    def format_ai_search_query(self) -> str:
        """Format positions and locations as a natural language query for AI search."""
        positions_text = ", ".join(
            p.strip() for p in self.positions if p and p.strip()
        )
        parts = []
        if positions_text:
            parts.append(f"{positions_text} roles")
        # Add remote/hybrid/onsite preferences
        work_types = []
        if self.remote:
            work_types.append("remote")
        if self.hybrid:
            work_types.append("hybrid")
        if self.onsite:
            work_types.append("on-site")
        if work_types:
            parts.append(f"preferably {', '.join(work_types)}")
        # Add locations
        if self.locations:
            parts.append(f"in {', '.join(self.locations)}")
        return " ".join(parts) if parts else "AI ML Engineer roles"

    async def _set_basic_search_terms(self):
        """Set basic search parameters (keywords and location) - async"""
        try:
            # Set job title/keywords
            if self.positions:
                keyword_query = self.format_linkedin_keyword_query()
                keyword_selectors = [
                    "input[aria-label*='or company']:not([disabled]):not([aria-hidden='true'])",
                    "input[aria-label*='Search by title']:not([disabled]):not([aria-hidden='true'])",
                    "#jobs-search-box-keyword-id-ember:not([disabled])",
                    ".jobs-search-box__input--keyword:not([disabled])",
                    "input[role='combobox'][aria-label*='Search by title']:not([disabled])",
                ]

                keywords_filled = False
                for selector in keyword_selectors:
                    if await safe_fill(self.page, selector, keyword_query, wait_for_timeout=2000):
                        logger.info(f"Keywords set: {keyword_query}")
                        keywords_filled = True
                        # await async_pause(1, 2)
                        break

                if not keywords_filled:
                    logger.warning("Could not find or fill keywords field")

            location_selectors = [
                "input[aria-label*='or zip code']:not([disabled]):not([aria-hidden='true'])",
                "input[aria-label*='City, state']:not([disabled]):not([aria-hidden='true'])",
                "#jobs-search-box-location-id-ember:not([disabled])",
                "input[id^='jobs-search-box-location-id-ember']:not([disabled])",
                ".jobs-search-box__input--location:not([disabled])",
                "input[aria-label*='location']:not([disabled]):not([aria-hidden='true'])",
            ]

            # Set or clear location. LinkedIn often keeps a previous/default location in this field.
            if self.locations:
                location_filled = False
                for selector in location_selectors:
                    if await safe_fill(
                        self.page, selector, ", ".join(self.locations), wait_for_timeout=2000
                    ):
                        logger.info(f"Location set: {', '.join(self.locations)}")
                        # await async_pause()

                        # Try to press Enter to apply location
                        element = await find_element_safely(self.page, selector)
                        if element:
                            await self.page.keyboard.press("Enter")

                        location_filled = True
                        break

                if not location_filled:
                    logger.warning("Could not find or fill location field")

            else:
                location_cleared = False
                for selector in location_selectors:
                    if await safe_fill(self.page, selector, "", wait_for_timeout=2000):
                        logger.info(
                            "Location search field cleared because no locations are configured"
                        )
                        await self._dismiss_location_typeahead()
                        location_cleared = True
                        break

                if not location_cleared:
                    logger.warning("Could not find or clear location field")

                # await async_pause()

        except Exception as e:
            logger.error(f"Error setting basic search parameters: {e}")

    async def _commit_basic_search(self) -> None:
        """Submit keyword/location fields before filters so LinkedIn preserves them."""
        search_selectors = [
            "button.jobs-search-box__submit-button",
            "button[aria-label='Search']",
            "button:has-text('Search')",
        ]
        for selector in search_selectors:
            if await safe_click(self.page, selector):
                logger.info("Basic LinkedIn search submitted before applying filters")
                await async_pause(2, 3)
                return

        logger.warning("Could not click Search button; pressing Enter to submit basic search")
        try:
            await self.page.keyboard.press("Enter")
            await async_pause(2, 3)
        except Exception as e:
            logger.warning(f"Could not submit basic search with Enter: {e}")

    async def _dismiss_location_typeahead(self) -> None:
        """Close LinkedIn's location suggestions so filter buttons are clickable."""
        try:
            await self.page.keyboard.press("Escape")
            await async_pause(1, 1)
        except Exception as e:
            logger.debug(f"Failed pressing Escape to close location typeahead: {e}")

        try:
            await self.page.evaluate("document.activeElement && document.activeElement.blur()")
        except Exception as e:
            logger.debug(f"Failed blurring active location field: {e}")

    async def _activate_ai_search(self) -> bool:
        """Activate LinkedIn's 'Find jobs with AI' natural language search.

        Clicks the AI search toggle/button on the jobs page, types a natural language
        query built from positions + locations + work preferences, and submits it.

        Returns True if AI search was activated and submitted successfully.
        """
        logger.info("Attempting to activate LinkedIn AI-powered search")

        # Step 1: Click the "Try AI job search" button/link
        ai_button_selectors = [
            "//a[contains(., 'Try AI job search')]",
            "//button[contains(., 'Try AI job search')]",
            "//span[contains(., 'Try AI job search')]/..",
            "//a[contains(., 'Find jobs with AI')]",
            "//button[contains(., 'Find jobs with AI')]",
            "//span[contains(., 'Find jobs with AI')]/..",
            "[data-test-ai-search-toggle]",
            "button[aria-label*='AI']",
            "//a[contains(@aria-label, 'AI')]",
            ".jobs-search-box__ai-search-button",
            "//button[contains(., 'Search with AI')]",
            "//button[contains(., 'AI search')]",
        ]

        ai_activated = False
        for selector in ai_button_selectors:
            if await safe_click(self.page, selector, timeout=3000):
                logger.info("AI search button clicked")
                ai_activated = True
                await async_pause(2, 3)
                break

        if not ai_activated:
            logger.warning(
                "Could not find 'Try AI job search' button. "
                "This feature may not be available in your region or LinkedIn plan. "
                "Falling back to classic keyword search."
            )
            return False

        # Step 2: Wait for the AI search page to load
        # After clicking "Try AI job search", LinkedIn navigates to the AI search
        # landing page (/jobs/search-results/?origin=SEMANTIC_SEARCH_MODE_FROM_CLASSIC).
        # This page has a special search bar with placeholder "Describe the job you want".
        await async_pause(3, 4)

        # Step 3: Fill the AI search bar with the natural language query
        nl_query = self.format_ai_search_query()
        logger.info(f"AI search query: {nl_query}")

        # The AI search bar has different selectors than the classic search
        ai_input_selectors = [
            "input[placeholder*='Describe']",
            "input[placeholder*='describe']",
            "input[placeholder*='job you want']",
            "input[placeholder*='Describe the job']",
            # Fall back to the standard keyword search bar selectors
            "input[aria-label*='or company']:not([disabled]):not([aria-hidden='true'])",
            "input[aria-label*='Search by title']:not([disabled]):not([aria-hidden='true'])",
            "#jobs-search-box-keyword-id-ember:not([disabled])",
            ".jobs-search-box__input--keyword:not([disabled])",
            "input[role='combobox'][aria-label*='Search by title']:not([disabled])",
        ]

        query_filled = False
        for selector in ai_input_selectors:
            if await safe_fill(self.page, selector, nl_query, wait_for_timeout=3000):
                logger.info(f"AI search query filled via selector: {selector}")
                query_filled = True
                await async_pause(1, 2)
                break

        if not query_filled:
            logger.warning(
                "Could not fill AI search query input. "
                "The AI search page may have a different layout than expected."
            )
            return False

        # Step 4: Submit the query
        try:
            await self.page.keyboard.press("Enter")
            await async_pause(4, 5)
            logger.info("AI search query submitted")
        except Exception as e:
            logger.warning(f"Failed to submit AI search query via Enter: {e}")
            # Try clicking the search button as fallback
            search_button_selectors = [
                "button.jobs-search-box__submit-button",
                "button[aria-label='Search']",
                "button:has-text('Search')",
                "button.search-search-box__submit",
            ]
            clicked = False
            for selector in search_button_selectors:
                if await safe_click(self.page, selector, timeout=3000):
                    logger.info("AI search submitted via search button click")
                    clicked = True
                    await async_pause(3, 4)
                    break
            if not clicked:
                logger.warning("Could not submit AI search query")
                return False

        # Step 5: Wait for search results to load
        await self._wait_for_search_results()
        return True

    async def _wait_for_search_results(self, timeout_ms: int = 30000) -> bool:
        """Wait for job listing cards to appear in the search results."""
        result_selectors = [
            "[data-job-id]",
            "li[data-occludable-job-id]",
            ".scaffold-layout__list [data-view-name='job-card']",
            ".job-card-container",
            ".job-card-job-posting-card-wrapper",
            ".jobs-search-results__list-item",
            ".jobs-search-two-pane__job-card-container",
            "a[href*='/jobs/view/']",
            "ul.scaffold-layout__list-container li",
        ]
        # Scroll down to trigger lazy loading of job cards
        try:
            await self.page.evaluate("window.scrollBy(0, 300)")
        except Exception:
            pass

        for selector in result_selectors:
            try:
                await self.page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
                logger.info(f"Search results loaded (detected via: {selector})")
                await async_pause(2, 3)
                return True
            except Exception:
                continue

        # Last resort: check if any job-related links exist on the page
        try:
            job_links = await self.page.locator("a[href*='/jobs/view/']").count()
            if job_links > 0:
                logger.info(f"Search results loaded ({job_links} job links found)")
                await async_pause(2, 3)
                return True
        except Exception:
            pass

        logger.warning("Timed out waiting for search results to appear")
        return False

    async def _apply_ai_search_filters(self) -> None:
        """Apply filters using the chip-based filter bar on the AI search results page.

        AI search uses clickable filter chips (Date posted, Easy Apply, Experience level,
        Remote, etc.) instead of the 'All filters' modal.
        """
        logger.info("Applying filters via AI search filter chips")

        # --- Date posted chip ---
        if self.date_posted:
            date_label = None
            for key, enabled in self.date_posted.items():
                if not enabled:
                    continue
                label_map = {
                    "24_hours": "Past 24 hours",
                    "day_24_hours": "Past 24 hours",
                    "week": "Past week",
                    "month": "Past month",
                    "all_time": "Any time",
                }
                date_label = label_map.get(key)
                break

            if date_label:
                await self._click_ai_filter_chip("Date posted", date_label)

        # --- Easy Apply chip ---
        if EASY_APPLY_ONLY_MODE:
            await self._click_ai_filter_chip("Easy Apply")

        # --- Experience level chip ---
        if self.experience_level:
            ai_exp_map = {
                "entry": "Entry-level",
                "mid_senior_level": "Senior",
                "director": "Director",
                "executive": "Executive",
            }
            for key, enabled in self.experience_level.items():
                if enabled and key in ai_exp_map:
                    await self._click_ai_filter_chip("Experience level", ai_exp_map[key])

        # --- Remote chip ---
        if self.remote:
            await self._click_ai_filter_chip("Remote")

    async def _click_ai_filter_chip(
        self, chip_name: str, option_text: str | None = None
    ) -> None:
        """Click an AI search filter chip and optionally select a dropdown option.

        For simple toggle chips (Easy Apply, Remote): just click the chip.
        For chips with dropdowns (Date posted, Experience level): click the chip,
        then select the matching option from the dropdown.
        """
        logger.debug(f"Clicking AI filter chip: {chip_name}")

        chip_selectors = [
            f"//button[contains(@aria-label, '{chip_name}')]",
            f"//button[contains(., '{chip_name}')]",
            f"//button[normalize-space()='{chip_name}']",
            f"//*[contains(@class, 'search-reusables__filter-pill') and contains(., '{chip_name}')]",
            f"//*[contains(@class, 'artdeco-pill') and contains(., '{chip_name}')]",
            f"//*[contains(@class, 'filter-pill') and contains(., '{chip_name}')]",
            f"//*[contains(@class, 'chip') and contains(., '{chip_name}')]",
            f"//*[contains(@role, 'button') and contains(., '{chip_name}')]",
            f"//span[contains(., '{chip_name}')]/..",
            f"//*[normalize-space()='{chip_name}']",
        ]

        chip_clicked = False
        for selector in chip_selectors:
            if await safe_click(self.page, selector, timeout=3000):
                chip_clicked = True
                await async_pause(1, 2)
                break

        if not chip_clicked:
            logger.warning(f"Could not find filter chip: {chip_name}")
            return

        if not option_text:
            logger.info(f"Filter chip toggled: {chip_name}")
            return

        # Select the option from the dropdown that appeared
        option_selectors = [
            f"//label[contains(., '{option_text}')]",
            f"//li[contains(., '{option_text}')]",
            f"//div[contains(@role, 'option') and contains(., '{option_text}')]",
            f"//*[contains(@class, 'search-reusables__filter') and contains(., '{option_text}')]",
        ]

        for selector in option_selectors:
            if await safe_click(self.page, selector, timeout=3000):
                logger.info(f"Filter option selected: {chip_name} -> {option_text}")
                await async_pause(1, 2)

                # Click 'Show results' or 'Done' to apply
                apply_selectors = [
                    "//button[contains(., 'Show results')]",
                    "//button[contains(., 'Done')]",
                    "//button[contains(., 'Apply')]",
                ]
                for apply_sel in apply_selectors:
                    if await safe_click(self.page, apply_sel, timeout=2000):
                        await async_pause(2, 3)
                        return
                return

        logger.warning(f"Could not select option '{option_text}' in chip '{chip_name}'")

    async def _open_all_filters(self):
        """Open 'All filters' modal window (async)"""
        try:
            filters_selectors = [
                "//button[contains(., 'All filters')]",
                "button[aria-label*='All filters']",
                "button[aria-label*='Show all filters']",
                ".jobs-search-results-list__filter-button[aria-label*='filters']",
            ]

            for selector in filters_selectors:
                if await safe_click(self.page, selector):
                    # await async_pause()
                    logger.info("Filters modal window opened")
                    return True

            logger.warning("Could not find or click All filters button")
            return False
        except Exception as e:
            logger.error(f"Failed to open filters: {e}")
        return False

    async def _set_date_posted_filter(self):
        """Set date posted filter (async)"""
        if not self.date_posted:
            return

        try:
            date_mapping = {
                "24_hours": "Past 24 hours",
                "day_24_hours": "Past 24 hours",
                "week": "Past week",
                "month": "Past month",
                "all_time": "Any time",
            }

            for date_key, is_enabled in self.date_posted.items():
                if is_enabled and date_key in date_mapping:
                    date_text = date_mapping[date_key]

                    # Try multiple selector approaches
                    date_selectors = [
                        f"//label[contains(., '{date_text}')]",
                        f"//input[@value='{date_text}']/..",
                        f"label:has-text('{date_text}')",
                        f"[data-test-date-posted-filter-option='{date_key}']",
                    ]

                    date_set = False
                    for selector in date_selectors:
                        if await safe_click(self.page, selector):
                            logger.info(f"Date filter set: {date_text}")
                            date_set = True
                            break

                    if not date_set:
                        logger.warning(f"Could not set date filter: {date_text}")

                    # await async_pause()
                    break

        except Exception as e:
            logger.error(f"Error setting date filter: {e}")

    async def _set_experience_level_filter(self):
        """Set experience level filter (async).

        Note: AI search and classic search have different experience level options.
        Classic: Internship, Entry level, Associate, Mid-Senior level, Director, Executive
        AI:      Entry-level, Senior, Manager, Director, Executive
        """
        if not self.experience_level:
            return

        try:
            if self._ai_search_active:
                # AI search has a different set of experience levels
                experience_mapping = {
                    "entry": "Entry-level",
                    "mid_senior_level": "Senior",
                    "director": "Director",
                    "executive": "Executive",
                    # Internship, Associate, Mid-Senior level are NOT available in AI search
                }
                unavailable = ["internship", "associate"]
                for key in unavailable:
                    if self.experience_level.get(key):
                        logger.warning(
                            f"Experience level '{key}' is not available in AI search mode, skipping"
                        )
            else:
                experience_mapping = {
                    "internship": "Internship",
                    "entry": "Entry level",
                    "associate": "Associate",
                    "mid_senior_level": "Mid-Senior level",
                    "director": "Director",
                    "executive": "Executive",
                }

            for exp_key, is_enabled in self.experience_level.items():
                if is_enabled and exp_key in experience_mapping:
                    exp_text = experience_mapping[exp_key]

                    # Try multiple selector approaches
                    exp_selectors = [
                        f"//label[contains(., '{exp_text}')]",
                        f"//input[@value='{exp_text}']/..",
                        f"label:has-text('{exp_text}')",
                        f"[data-test-experience-level-filter='{exp_key}']",
                    ]

                    exp_set = False
                    for selector in exp_selectors:
                        if await safe_click(self.page, selector):
                            logger.info(f"Experience level set: {exp_text}")
                            exp_set = True
                            break

                    if not exp_set:
                        logger.warning(f"Element not found for experience level: {exp_text}")

                    # await async_pause()

        except Exception as e:
            logger.error(f"Error setting experience level filter: {e}")

    async def _set_job_type_filter(self):
        """Set job type filter (async)"""
        if not self.job_types:
            return

        try:
            job_type_mapping = {
                "full_time": "Full-time",
                "contract": "Contract",
                "part_time": "Part-time",
                "temporary": "Temporary",
                "volunteer": "Volunteer",
                "internship": "Internship",
                "other": "Other",
            }

            for job_type_key, is_enabled in self.job_types.items():
                if is_enabled and job_type_key in job_type_mapping:
                    job_type_text = job_type_mapping[job_type_key]
                    # There are two internship checkboxes, so we need to select the second one
                    element_number = 1 if job_type_key == "internship" else 0

                    # Try multiple selector approaches
                    job_type_selectors = [
                        f"//label[contains(., '{job_type_text}')]",
                        f"//input[@value='{job_type_text}']/..",
                        f"label:has-text('{job_type_text}')",
                        f"[data-test-job-type-filter='{job_type_key}']",
                    ]

                    job_type_set = False
                    for selector in job_type_selectors:
                        if await safe_click(self.page, selector, element_number=element_number):
                            logger.info(f"Job type set: {job_type_text}")
                            job_type_set = True
                            break

                    if not job_type_set:
                        logger.warning(f"Element not found for job type: {job_type_text}")

                    # await async_pause()

        except Exception as e:
            logger.error(f"Error setting job type filter: {e}")

    async def _set_work_location_filter(self):
        """Set work location filter (remote/hybrid/on-site) - async"""
        try:
            work_location_filters = []
            if self.remote:
                work_location_filters.append("Remote")
            if self.hybrid:
                work_location_filters.append("Hybrid")
            if self.onsite:
                work_location_filters.append("On-site")

            for location_type in work_location_filters:
                # Try multiple selector approaches
                location_selectors = [
                    f"//label[contains(., '{location_type}')]",
                    f"//input[@value='{location_type}']/..",
                    f"label:has-text('{location_type}')",
                    f"[data-test-work-location-filter='{location_type.lower()}']",
                ]

                location_set = False
                for selector in location_selectors:
                    if await safe_click(self.page, selector):
                        logger.info(f"Location type set: {location_type}")
                        location_set = True
                        break

                if not location_set:
                    logger.warning(f"Element not found for location type: {location_type}")

                # await async_pause()

        except Exception as e:
            logger.error(f"Error setting work location filter: {e}")

    async def _apply_filters(self):
        """Apply set filters (async)"""
        try:
            # Find and click the "Show results" or "Apply" button
            apply_selectors = [
                "//button[contains(., 'Show') or contains(., 'Apply') or contains(., 'Done')]",
                "button[aria-label*='Show results']",
                "button[aria-label*='Apply filters']",
                ".jobs-search-dropdown__apply-button",
                ".search-reusables__filter-pill-button",
            ]

            for selector in apply_selectors:
                if await safe_click(self.page, selector, timeout=10000):
                    # await async_pause()
                    logger.info("Filters applied")
                    return True

            logger.warning("Could not find or click filter apply button")
            return False

        except Exception as e:
            logger.error(f"Error applying filters: {e}")
        return False

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

            # Navigate to LinkedIn jobs search
            await self.page.goto(
                "https://www.linkedin.com/jobs/search/", wait_until="domcontentloaded"
            )
            await async_pause(2, 3)

            # Try AI-powered search if enabled
            if LINKEDIN_AI_SEARCH_MODE:
                ai_success = await self._activate_ai_search()
                if ai_success:
                    self._ai_search_active = True
                    logger.info("AI-powered search activated successfully")
                    # Apply filters via chips (AI search uses chips, not "All filters" modal)
                    await self._apply_ai_search_filters()
                    logger.info("Search parameters successfully set (AI mode)")
                    return
                else:
                    logger.warning(
                        "AI search activation failed, falling back to classic keyword search"
                    )

            # Classic keyword search flow
            # Set basic search terms (keywords and location)
            await self._set_basic_search_terms()
            await self._commit_basic_search()

            # Open advanced filters modal
            if await self._open_all_filters():
                # Set various filters
                await self._set_date_posted_filter()
                await self._set_experience_level_filter()
                await self._set_job_type_filter()
                await self._set_work_location_filter()
                await self._set_easy_apply_filter()

                # Apply all filters
                if not await self._apply_filters():
                    logger.warning("Failed to apply filters, continuing with basic search")
            else:
                logger.warning("Could not open advanced filters, using basic search only")

            logger.info("Search parameters successfully set")

        except Exception as e:
            logger.error(f"Error setting search parameters: {e}")
            raise

    async def _set_easy_apply_filter(self):
        """Set Easy Apply filter toggle (async)"""
        if not EASY_APPLY_ONLY_MODE:
            return

        try:
            # First check if Easy Apply is already enabled
            input_selectors = [
                "//h3[contains(., 'Easy Apply')]/following::input[@role='switch'][1]",
                "input[role='switch'][data-artdeco-toggle-button='true']",
            ]

            for input_selector in input_selectors:
                input_element = await find_element_safely(self.page, input_selector)
                if input_element:
                    aria_checked = await input_element.get_attribute("aria-checked")
                    if aria_checked == "true":
                        logger.info("Easy Apply filter is already enabled")
                        return
                    break

            # Easy Apply is a toggle switch - click on the label or parent div, not the input
            easy_apply_selectors = [
                # Click on the parent div toggle container
                "//h3[contains(., 'Easy Apply')]/following::div[contains(@class, 'artdeco-toggle')][1]",
                # Alternative: find label by text
                "label[data-artdeco-toggle-label='true']:has(span:text('Toggle Easy Apply filter'))",
                # Fallback: click on the toggle text span
                "//h3[contains(., 'Easy Apply')]/following::span[@data-artdeco-toggle-text='true'][1]",
            ]

            easy_apply_toggled = False
            for selector in easy_apply_selectors:
                if await safe_click(self.page, selector):
                    logger.info("Easy Apply filter enabled")
                    easy_apply_toggled = True
                    # await async_pause()
                    break

            if not easy_apply_toggled:
                logger.warning("Could not find or toggle Easy Apply filter")

        except Exception as e:
            logger.error(f"Error setting Easy Apply filter: {e}")


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
