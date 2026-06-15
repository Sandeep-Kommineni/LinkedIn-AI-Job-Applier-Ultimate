import asyncio
import os
import random
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from config.constants import APP_CONFIG_FILE

try:
    from config.app_config import READY_MADE_RESUME_PATH
except ImportError:
    READY_MADE_RESUME_PATH = None

try:
    from config.app_config import READY_MADE_PHOTO_PATH
except ImportError:
    READY_MADE_PHOTO_PATH = None

# Import browser configuration
from config.logger_config import logger


class ConfigError(Exception):
    pass


chromeProfilePath = os.path.join(os.getcwd(), "chrome_profile", "linkedin_profile")


def load_yaml_file(yaml_path: Path) -> dict:
    """Load settings from YAML configuration file"""
    try:
        with open(yaml_path, "r", encoding="UTF-8") as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise yaml.YAMLError(f"Error in reading file {yaml_path}: {exc}")
    except FileNotFoundError:
        raise ConfigError(f"File not found: {yaml_path}")


def load_app_config() -> dict:
    """Загрузить конфигурацию приложения из YAML файла"""
    try:
        config = load_yaml_file(APP_CONFIG_FILE)
        return config or {}
    except Exception as e:
        # Fallback logging to stderr since we can't use logger here
        print(f"Ошибка при загрузке конфигурации приложения: {e}", file=sys.stderr)
        return {}


def save_yaml_file(yaml_path: Path, data: dict, sort_keys: bool = True) -> None:
    """Save YAML data atomically and flush it to disk."""
    yaml_path = Path(yaml_path)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = yaml_path.with_name(f".{yaml_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp_path, "w", encoding="UTF-8") as stream:
            yaml.safe_dump(
                data, stream, allow_unicode=True, default_flow_style=False, sort_keys=sort_keys
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, yaml_path)
        if hasattr(os, "O_DIRECTORY"):
            try:
                dir_fd = os.open(yaml_path.parent, os.O_DIRECTORY)
            except OSError:
                return
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def append_yaml_file(yaml_path: Path, data: dict) -> None:
    """Append data to YAML file"""
    # Append the log entry to the call log file
    try:
        with yaml_path.open("a", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
            f.write("\n")
        logger.info(f"Data appended to {yaml_path}")
    except yaml.YAMLError as exc:
        raise yaml.YAMLError(f"Error in reading file {yaml_path}: {exc}")


def pause(low: int = 0.5, high: int = 1) -> None:
    """
    Hold a random pause in the range from
    low seconds to high seconds.
    Used to simulate user behavior.
    """
    pause = round(random.uniform(low, high), 1)
    time.sleep(pause)


async def async_pause(low: float = 0.5, high: float = 1) -> None:
    """
    Hold a random pause without blocking the asyncio event loop.
    """
    pause_time = round(random.uniform(low, high), 1)
    await asyncio.sleep(pause_time)


def sleep(sleep_interval: Tuple[int, int]) -> None:
    """Analog of _pause, but waiting can be interrupted"""
    low, high = sleep_interval
    sleep_time = random.randint(low, high)
    time_to_wait = f"{sleep_time // 60} minutes, {sleep_time % 60} seconds"
    time.sleep(sleep_time)
    logger.info(f"Waiting lasted {time_to_wait}.")


def sanitize_text(text: str) -> str:
    """Clean the text of the question/answer"""
    sanitized_text = text.lower().strip().replace('"', "").replace("\\", "")
    sanitized_text = (
        re.sub(r"[\x00-\x1F\x7F]", "", sanitized_text)
        .replace("\n", " ")
        .replace("\r", "")
        .rstrip(",")
    )
    sanitized_text = re.sub(r"\s+", " ", sanitized_text)
    return sanitized_text


def get_ready_made_resume() -> Path | None:
    """Resolve the ready-made resume path and return it if it exists as a file, else None."""
    if not READY_MADE_RESUME_PATH:
        return None
    resolved = Path(READY_MADE_RESUME_PATH).resolve()
    return resolved if resolved.is_file() else None


def get_ready_made_photo() -> Path | None:
    """Resolve the ready-made photo path and return it if it exists as a file, else None."""
    if not READY_MADE_PHOTO_PATH:
        return None
    resolved = Path(READY_MADE_PHOTO_PATH).resolve()
    return resolved if resolved.is_file() else None


def validate_structured_resume_fields(structured_resume: Dict[str, Any]) -> List[str]:
    """
    Validate structured resume and return list of missing or placeholder fields.

    Args:
        structured_resume: Dictionary containing structured resume data

    Returns:
        List of missing field paths (e.g., ['personal_information.name', 'experience_details.0.position'])
    """
    missing_fields = []

    def check_field(value: Any, field_path: str) -> None:
        """Recursively check if field contains placeholder or is missing"""
        if isinstance(value, dict):
            for key, val in value.items():
                current_path = f"{field_path}.{key}" if field_path else key
                check_field(val, current_path)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                current_path = f"{field_path}.{i + 1}" if field_path else str(i + 1)
                check_field(item, current_path)
        elif isinstance(value, str):
            # Check for placeholder patterns
            if (value.startswith("[") and value.endswith("]")) or value in ["No info", ""]:
                missing_fields.append(field_path)
        elif value is None:
            missing_fields.append(field_path)

    check_field(structured_resume, "")
    return missing_fields


def format_missing_fields_display(missing_fields: List[str]) -> str:
    """
    Format missing fields for user-friendly display.

    Args:
        missing_fields: List of missing field paths

    Returns:
        Formatted string showing missing fields grouped by section
    """
    if not missing_fields:
        return "All fields are properly filled!"

    # Group fields by main section
    sections = {}
    for field in missing_fields:
        parts = field.split(".")
        if len(parts) >= 1:
            section = parts[0]
            if section not in sections:
                sections[section] = []
            sections[section].append(".".join(parts[1:]) if len(parts) > 1 else "")

    display_text = "Missing or placeholder fields found:\n\n"
    for section, fields in sections.items():
        display_text += f"📋 {section.replace('_', ' ').title()}:\n"
        for field in fields:
            if field:
                display_text += f"   • {field.replace('_', ' ').title()}\n"
        display_text += "\n"

    return display_text


def get_user_choice_with_timeout(timeout_seconds: int = 30) -> str:
    """
    Get user input with timeout. If no input within timeout, returns 'continue'.

    Args:
        timeout_seconds: Timeout in seconds

    Returns:
        User choice or 'continue' if timeout
    """
    result = {"choice": "continue"}

    def get_input():
        try:
            choice = input("Enter your choice (y/n): ").strip()
            result["choice"] = choice
        except (EOFError, KeyboardInterrupt):
            result["choice"] = "continue"

    input_thread = threading.Thread(target=get_input)
    input_thread.daemon = True
    input_thread.start()
    input_thread.join(timeout_seconds)

    return result["choice"]


def validate_and_prompt_resume_completion(
    structured_resume: Dict[str, Any], structured_resume_file: Path, resume_text_file: Path
) -> bool:
    """
    Validate structured resume fields and prompt user to complete missing information.

    Args:
        structured_resume: Dictionary containing structured resume data
        structured_resume_file: Path to structured resume YAML file
        resume_text_file: Path to resume text file

    Returns:
        True if user chooses to continue, False if user chooses to exit
    """
    logger.info("Validating structured resume fields...")

    missing_fields = validate_structured_resume_fields(structured_resume)

    if not missing_fields:
        logger.info("✅ All structured resume fields are properly filled!")
        return True

    logger.warning(f"Found {len(missing_fields)} missing or placeholder fields")

    # Display missing fields
    missing_display = format_missing_fields_display(missing_fields)
    print("\n" + "=" * 80)
    print("⚠️  STRUCTURED RESUME VALIDATION WARNING")
    print("=" * 80)
    print(missing_display)
    print("=" * 80)
    print("\nThe program may not be able to answer questions correctly with missing information.")
    print(
        f"\nWe recommend you to stop the program, fill missing information in {resume_text_file} and {structured_resume_file}, then restart."
    )
    print(
        f"""\nFilling missing fields in {structured_resume_file} is not necessary, you can delete this file, fill only text information in {resume_text_file} and restart the program - structured resumefile will be generated automatically from your text resume."""
    )
    print(
        f"\nIf you want to fill missing fields in {structured_resume_file} manually - use 'data/resume/structured_resume_template.yaml' as a reference for the structure of the resume."
    )
    print(
        "\nWould you like to continue anyway? If you make no choice in 30 seconds - the program will continue automatically."
    )
    print("\n" + "=" * 80)

    # Get user choice with timeout
    choice = get_user_choice_with_timeout(30)

    if choice == "y" or choice == "continue":
        print("\n⏰ Continuing program execution...")
        logger.info("User chose to continue or timeout reached")
        return True
    else:  # choice != 'y'
        print("\n📝 Please edit the following file to fill missing fields:")
        print(f"   {structured_resume_file}")
        print("\nThen run the program again.")
        logger.info("User chose to exit and edit structured resume file")
        return False


def debug_page_elements(page) -> None:
    """Debug function to log available elements on the page"""
    logger.debug("=== DEBUGGING PAGE ELEMENTS ===")
    try:
        # Log current URL
        try:
            logger.debug(f"Current URL: {page.url}")
        except Exception:
            pass

        # Look for any modal-related elements
        modal_elements = page.find_elements("css selector", "[class*='modal']")
        logger.debug(f"Found {len(modal_elements)} modal-related elements")
        for i, elem in enumerate(modal_elements[:5]):  # Log first 5
            try:
                class_name = elem.get_attribute("class")
                logger.debug(f"Modal element {i + 1}: class='{class_name}'")
            except Exception:
                pass

        # Look for any easy-apply related elements
        easy_apply_elements = page.find_elements("css selector", "[class*='easy-apply']")
        logger.debug(f"Found {len(easy_apply_elements)} easy-apply-related elements")
        for i, elem in enumerate(easy_apply_elements[:5]):  # Log first 5
            try:
                class_name = elem.get_attribute("class")
                logger.debug(f"Easy Apply element {i + 1}: class='{class_name}'")
            except Exception:
                pass

        # Look for any form-related elements
        form_elements = page.find_elements("css selector", "[class*='form']")
        logger.debug(f"Found {len(form_elements)} form-related elements")
        for i, elem in enumerate(form_elements[:5]):  # Log first 5
            try:
                class_name = elem.get_attribute("class")
                logger.debug(f"Form element {i + 1}: class='{class_name}'")
            except Exception:
                pass

    except Exception as e:
        logger.debug(f"Error during page debugging: {e}")
    logger.debug("=== END DEBUGGING ===")


def clean_structured_resume(structured_resume: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove items from structured resume that have placeholder values ('No info', None, '').

    Args:
        structured_resume: Dictionary containing structured resume data

    Returns:
        Cleaned structured resume with placeholder values removed
    """

    def clean_value(value: Any) -> Any:
        """Recursively clean values and remove placeholder entries"""
        if isinstance(value, dict):
            # Clean dictionary values and remove empty keys
            cleaned_dict = {}
            for key, val in value.items():
                cleaned_val = clean_value(val)
                if cleaned_val is not None:
                    cleaned_dict[key] = cleaned_val
            return cleaned_dict if cleaned_dict else None

        elif isinstance(value, list):
            # Clean list items and remove empty entries
            cleaned_list = []
            for item in value:
                cleaned_item = clean_value(item)
                if cleaned_item is not None:
                    cleaned_list.append(cleaned_item)
            return cleaned_list if cleaned_list else None

        elif isinstance(value, str):
            # Remove placeholder strings
            if value.strip() in ["No info", ""]:
                return None
            return value.strip() if value.strip() else None

        elif value is None:
            return None

        else:
            return value

    cleaned_resume = clean_value(structured_resume)
    return cleaned_resume if cleaned_resume is not None else {}


# Location keywords to currency mapping for salary inference
_LOCATION_CURRENCY_MAP = {
    # INR locations
    "india": "INR", "hyderabad": "INR", "bengaluru": "INR", "bangalore": "INR",
    "mumbai": "INR", "pune": "INR", "chennai": "INR", "delhi": "INR",
    "gurugram": "INR", "gurgaon": "INR", "noida": "INR", "kolkata": "INR",
    "ahmedabad": "INR", "jaipur": "INR", "chandigarh": "INR",
    "telangana": "INR", "karnataka": "INR", "maharashtra": "INR",
    "tamil nadu": "INR", "tamilnadu": "INR", "gandhinagar": "INR",
    # USD locations
    "united states": "USD", "usa": "USD", "us": "USD",
    "new york": "USD", "san francisco": "USD", "seattle": "USD",
    "austin": "USD", "boston": "USD", "chicago": "USD",
    "los angeles": "USD", "denver": "USD", "atlanta": "USD",
    "washington": "USD", "california": "USD", "texas": "USD",
    # GBP locations
    "united kingdom": "GBP", "uk": "GBP", "london": "GBP",
    "manchester": "GBP", "edinburgh": "GBP", "birmingham": "GBP",
    # EUR locations
    "germany": "EUR", "berlin": "EUR", "munich": "EUR",
    "france": "EUR", "paris": "EUR", "netherlands": "EUR",
    "amsterdam": "EUR", "ireland": "EUR", "dublin": "EUR",
    # CAD locations
    "canada": "CAD", "toronto": "CAD", "vancouver": "CAD", "montreal": "CAD",
    # AUD locations
    "australia": "AUD", "sydney": "AUD", "melbourne": "AUD",
}

# Approximate conversion rates to USD for non-INR/USD currencies
_CURRENCY_TO_USD = {
    "GBP": 1.27,
    "EUR": 1.08,
    "CAD": 0.73,
    "AUD": 0.65,
}

# Approximate INR to USD rate
_INR_TO_USD = 1 / 83  # ~83 INR per USD


def _infer_currency_from_location(job_location: str) -> str | None:
    """Infer currency from job location string."""
    if not job_location:
        return None
    loc_lower = job_location.lower()
    for keyword, currency in _LOCATION_CURRENCY_MAP.items():
        if keyword in loc_lower:
            return currency
    return None


def parse_salary_from_text(text: str, job_location: str = "") -> dict:
    """Parse salary information from job description text.

    Detects common salary formats in both INR and USD:
      - LPA: "5 LPA", "12 lpa", "5-12 LPA"
      - Lakhs: "₹5 lakhs", "5-8 lakh per annum"
      - Monthly INR: "₹50,000 per month", "₹10k/month"
      - Annual INR: "₹6,00,000", "600000 per year"
      - USD annual: "$60,000", "$60k-$80k"
      - USD monthly: "$5,000 per month"

    Returns:
        dict with keys:
          - found: bool
          - min_annual_inr: int or None
          - max_annual_inr: int or None
          - min_annual_usd: int or None
          - max_annual_usd: int or None
          - raw_match: str  (the text that was matched)
    """
    result = {
        "found": False,
        "min_annual_inr": None,
        "max_annual_inr": None,
        "min_annual_usd": None,
        "max_annual_usd": None,
        "min_annual_other_usd": None,
        "max_annual_other_usd": None,
        "raw_match": "",
        "inferred_currency": None,
    }

    if not text:
        return result

    # Infer currency from job location for ambiguous patterns
    inferred_currency = _infer_currency_from_location(job_location)
    result["inferred_currency"] = inferred_currency

    def _parse_number(s: str) -> float:
        """Parse a number string that may contain commas, k/K, or lakh/L."""
        s = s.strip().replace(",", "")
        multiplier = 1
        if s.lower().endswith("k"):
            s = s[:-1]
            multiplier = 1000
        elif s.lower().endswith("l") and not s.lower().endswith("lpa"):
            s = s[:-1]
            multiplier = 100000
        try:
            return float(s) * multiplier
        except ValueError:
            return 0

    # Pattern 1: X LPA / X-Y LPA / CTC: X LPA
    lpa_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*LPA",
        text,
        re.IGNORECASE,
    )
    if lpa_match:
        low = float(lpa_match.group(1)) * 100000
        high = float(lpa_match.group(2)) * 100000 if lpa_match.group(2) else low
        result["found"] = True
        result["min_annual_inr"] = int(low)
        result["max_annual_inr"] = int(high)
        result["raw_match"] = lpa_match.group(0)
        return result

    # Pattern 1b: CTC/stipend/salary: X (plain number after CTC keyword)
    # Uses location to infer currency when not explicitly stated
    ctc_plain_match = re.search(
        r"(?:CTC|stipend|salary|compensation)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*(?:lpa|lakhs?|per\s*annum|per\s*year|/\s*year|pa\b|annually)?",
        text,
        re.IGNORECASE,
    )
    if ctc_plain_match:
        raw_val = float(ctc_plain_match.group(1))
        high_raw = ctc_plain_match.group(2)

        if inferred_currency in ("USD", "GBP", "EUR", "CAD", "AUD"):
            # Non-INR location: treat small values as thousands, large as raw
            if raw_val <= 200:
                low = raw_val * 1000  # e.g. "salary: 60" -> $60,000
            else:
                low = raw_val
            if high_raw:
                high_val = float(high_raw)
                high = high_val * 1000 if high_val <= 200 else high_val
            else:
                high = low
            if inferred_currency == "USD":
                result["found"] = True
                result["min_annual_usd"] = int(low)
                result["max_annual_usd"] = int(high)
            else:
                # Convert to USD equivalent
                rate = _CURRENCY_TO_USD.get(inferred_currency, 1.0)
                result["found"] = True
                result["min_annual_other_usd"] = int(low * rate)
                result["max_annual_other_usd"] = int(high * rate)
        else:
            # INR location or unknown: treat small values as LPA, large as raw INR
            if raw_val <= 50:
                low = raw_val * 100000
            else:
                low = raw_val
            if high_raw:
                high_val = float(high_raw)
                high = high_val * 100000 if high_val <= 50 else high_val
            else:
                high = low
            result["found"] = True
            result["min_annual_inr"] = int(low)
            result["max_annual_inr"] = int(high)
        result["raw_match"] = ctc_plain_match.group(0)
        return result

    # Pattern 2: X lakh(s) per annum / X-Y lakhs
    lakh_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*lakhs?\s*(?:per\s*annum|per\s*year|/\s*year|p\.?a\.?|pa)?",
        text,
        re.IGNORECASE,
    )
    if lakh_match:
        low = float(lakh_match.group(1)) * 100000
        high = float(lakh_match.group(2)) * 100000 if lakh_match.group(2) else low
        result["found"] = True
        result["min_annual_inr"] = int(low)
        result["max_annual_inr"] = int(high)
        result["raw_match"] = lakh_match.group(0)
        return result

    # Pattern 3: ₹ amount per month / ₹X,XX,XXX/month
    inr_monthly_match = re.search(
        r"[₹]\s*(\d[\d,]*\.?\d*)\s*(?:k\b)?\s*(?:per\s*month|/\s*month|pm\b|monthly)",
        text,
        re.IGNORECASE,
    )
    if inr_monthly_match:
        raw_num = inr_monthly_match.group(1)
        num = _parse_number(raw_num)
        if "k" in text[inr_monthly_match.start() : inr_monthly_match.end()].lower():
            num *= 1000
        result["found"] = True
        result["min_annual_inr"] = int(num * 12)
        result["max_annual_inr"] = int(num * 12)
        result["raw_match"] = inr_monthly_match.group(0)
        return result

    # Pattern 4: ₹ annual amount (Indian number format or plain number)
    inr_annual_match = re.search(
        r"[₹]\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:per\s*(?:annum|year)|/\s*(?:annum|year)|p\.?a\.?|pa\b|per\s*year|CTC)?",
        text,
        re.IGNORECASE,
    )
    if inr_annual_match:
        raw_num = inr_annual_match.group(1)
        num = _parse_number(raw_num)
        # If number looks like monthly (less than 50000), treat as monthly
        if num < 50000:
            num *= 12
        result["found"] = True
        result["min_annual_inr"] = int(num)
        result["max_annual_inr"] = int(num)
        result["raw_match"] = inr_annual_match.group(0)
        return result

    # Pattern 5: $ amount per month (MUST come before plain monthly to avoid false matches)
    usd_monthly_match = re.search(
        r"\$\s*(\d[\d,]*\.?\d*)\s*(?:k\b)?\s*(?:per\s*month|/\s*month|pm\b|monthly)",
        text,
        re.IGNORECASE,
    )
    if usd_monthly_match:
        raw_num = usd_monthly_match.group(1)
        num = _parse_number(raw_num)
        if "k" in text[usd_monthly_match.start() : usd_monthly_match.end()].lower():
            num *= 1000
        result["found"] = True
        result["min_annual_usd"] = int(num * 12)
        result["max_annual_usd"] = int(num * 12)
        result["raw_match"] = usd_monthly_match.group(0)
        return result

    # Pattern 6: $ annual amount (range or single)
    usd_annual_match = re.search(
        r"\$\s*(\d[\d,]*\.?\d*)\s*(k\b)?\s*(?:-\s*(?:\$\s*)?(\d[\d,]*\.?\d*)\s*(k\b)?)?"
        r"\s*(?:per\s*(?:annum|year)|/\s*(?:annum|year)|p\.?a\.?|pa\b|per\s*year|annual|salary|CTC)?",
        text,
        re.IGNORECASE,
    )
    if usd_annual_match:
        raw_low = usd_annual_match.group(1)
        low = _parse_number(raw_low)
        if usd_annual_match.group(2):  # low has 'k' suffix
            low *= 1000
        if usd_annual_match.group(3):  # high value present
            raw_high = usd_annual_match.group(3)
            high = _parse_number(raw_high)
            if usd_annual_match.group(4):  # high has 'k' suffix
                high *= 1000
        else:
            high = low
        result["found"] = True
        result["min_annual_usd"] = int(low)
        result["max_annual_usd"] = int(high)
        result["raw_match"] = usd_annual_match.group(0)
        return result

    # Pattern 4b: Xk per month / X k/month / X,000 per month (no currency symbol)
    # MUST come after USD patterns to avoid matching digits inside '$5,000'
    # Uses location to infer currency
    plain_monthly_match = re.search(
        r"(?<!\$)(?<!\u20b9)(\d+(?:\.\d+)?)\s*k?\s*(?:per\s*month|/\s*month|\bpm\b|monthly)",
        text,
        re.IGNORECASE,
    )
    if plain_monthly_match:
        raw_num = plain_monthly_match.group(1)
        num = float(raw_num.replace(",", ""))
        # If 'k' is in the match, multiply by 1000
        if "k" in plain_monthly_match.group(0).lower():
            num *= 1000

        annual = num * 12  # monthly to annual

        if inferred_currency in ("USD", "GBP", "EUR", "CAD", "AUD"):
            # Non-INR location
            if inferred_currency == "USD":
                result["found"] = True
                result["min_annual_usd"] = int(annual)
                result["max_annual_usd"] = int(annual)
            else:
                rate = _CURRENCY_TO_USD.get(inferred_currency, 1.0)
                result["found"] = True
                result["min_annual_other_usd"] = int(annual * rate)
                result["max_annual_other_usd"] = int(annual * rate)
        else:
            # INR location or unknown
            result["found"] = True
            result["min_annual_inr"] = int(annual)
            result["max_annual_inr"] = int(annual)
        result["raw_match"] = plain_monthly_match.group(0)
        return result

    # Pattern 4c: INR X / INR X per month / INR X per year
    inr_prefix_match = re.search(
        r"INR\s*(\d[\d,]*\.?\d*)\s*(?:k\b)?\s*(?:per\s*(?:month|annum|year)|/\s*(?:month|annum|year)|pa\b)?",
        text,
        re.IGNORECASE,
    )
    if inr_prefix_match:
        raw_num = inr_prefix_match.group(1)
        num = _parse_number(raw_num)
        if "k" in inr_prefix_match.group(0).lower():
            num *= 1000
        match_text = inr_prefix_match.group(0).lower()
        if "month" in match_text:
            num *= 12  # monthly to annual
        result["found"] = True
        result["min_annual_inr"] = int(num)
        result["max_annual_inr"] = int(num)
        result["raw_match"] = inr_prefix_match.group(0)
        return result

    return result


def check_salary_threshold(
    job_description: str,
    salary_filter_config: dict,
    job_location: str = "",
) -> tuple[bool, str]:
    """Check if a job's salary meets the configured minimum threshold.

    Args:
        job_description: The full job description text.
        salary_filter_config: Dict from SalaryFilter.model_dump().
        job_location: The job's location string for currency inference.

    Returns:
        (should_skip, reason) tuple:
          - (False, "") if no salary found or salary meets threshold
          - (True, reason) if salary is explicitly below minimum

    Currency inference when not explicitly stated:
      - Job in India/Bengaluru/etc. -> INR thresholds
      - Job in US/New York/etc. -> USD thresholds
      - GBP/EUR/CAD/AUD -> converted to USD for comparison
    """
    if not salary_filter_config.get("enabled", False):
        return False, ""

    # Check for explicit unpaid/no-compensation keywords first
    unpaid_patterns = [
        r"\bunpaid\b",
        r"\bno\s+compensation\b",
        r"\bno\s+pay\b",
        r"\bvolunteer\s+(?:role|position|internship)\b",
        r"\bstipend[\s:]+(?:none|0|not\s+provided)\b",
    ]
    for pattern in unpaid_patterns:
        if re.search(pattern, job_description, re.IGNORECASE):
            return True, "Job explicitly mentions unpaid/no compensation — skipping"

    parsed = parse_salary_from_text(job_description, job_location)
    if not parsed["found"]:
        return False, ""

    min_inr = salary_filter_config.get("min_annual_inr") or 0
    min_usd = salary_filter_config.get("min_annual_usd") or 0

    # Check INR salary — skip only if the max offered is below our minimum
    if parsed["min_annual_inr"] is not None:
        detected_min = parsed["min_annual_inr"]
        detected_max = parsed["max_annual_inr"] or detected_min
        if detected_max < min_inr:
            return True, (
                f"Salary {parsed['raw_match']} ({detected_min:,}-{detected_max:,} INR/year) "
                f"is below minimum threshold ({min_inr:,} INR/year)"
            )

    # Check USD salary — skip only if the max offered is below our minimum
    if parsed["min_annual_usd"] is not None:
        detected_min = parsed["min_annual_usd"]
        detected_max = parsed["max_annual_usd"] or detected_min
        if detected_max < min_usd:
            return True, (
                f"Salary {parsed['raw_match']} (${detected_min:,}-${detected_max:,}/year) "
                f"is below minimum threshold (${min_usd:,}/year)"
            )

    # Check other currencies (GBP, EUR, CAD, AUD) — convert to USD and compare
    if parsed.get("min_annual_other_usd") is not None:
        detected_min = parsed["min_annual_other_usd"]
        detected_max = parsed.get("max_annual_other_usd") or detected_min
        if detected_max < min_usd:
            return True, (
                f"Salary {parsed['raw_match']} (~${detected_min:,}-~${detected_max:,} USD equiv/year) "
                f"is below minimum threshold (${min_usd:,}/year)"
            )

    return False, ""
