"""
External Job Resume Generator — Tailor your resume for ANY job posting.

Works with any source:
  - URL from any site (LinkedIn, Indeed, Glassdoor, company careers pages)
  - Job description text file
  - Direct text input via command line

Usage:
  # From a URL (any job site)
  python tools/external_resume.py --url "https://company.com/careers/job-123"

  # From a text file containing the job description
  python tools/external_resume.py --file "path/to/job_description.txt"

  # From direct text (use quotes for multi-line)
  python tools/external_resume.py --text "Job Title: ML Engineer\nCompany: Acme\nRequirements: Python, PyTorch..."

Output:
  Tailored resume PDF saved to: data/resumes/External Job Resumes/{Company}_{Title}.pdf
"""

import argparse
import asyncio
import base64
import re
import sys
from pathlib import Path

import dotenv

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.constants import RESUME_DIR
from config.logger_config import logger

from src.job_manager.resume_anonymizer import ResumeAnonymizer
from src.llm.llm_manager import GPTAnswerer
from src.pydantic_models.prompt_models import ResumeStructure
from src.resume_builder.resume_generator import ResumeGenerator
from src.resume_builder.resume_manager import ResumeManager
from src.resume_builder.style_manager import StyleManager
from src.utils.browser_utils import create_playwright_browser, save_browser_session, stop_tracing
from src.utils.utils import load_yaml_file

EXTERNAL_RESUME_DIR = Path(RESUME_DIR) / "External Job Resumes"


def setup_resume_pipeline(llm_api_key: str, llm_proxy: str, resume_text: str, resume_structured: dict):
    """Set up the resume generation pipeline."""
    resume_anonymizer = ResumeAnonymizer(resume_structured)
    resume_anonymizer.anonymize_personal_information()
    anonymized_structured = resume_anonymizer.resume_anonymized
    anonymized_text = resume_anonymizer.anonymize_text(resume_text)

    llm = GPTAnswerer(llm_api_key, llm_proxy)
    llm.set_resume(anonymized_structured, anonymized_text)

    style_manager = StyleManager()
    resume_generator = ResumeGenerator(llm, resume_anonymizer)
    resume_manager = ResumeManager(llm_api_key, style_manager, resume_generator)
    resume_manager.choose_style()

    return llm, resume_manager


async def scrape_job_from_url(page, url: str) -> dict:
    """Load any job page and extract job description, title, and company.

    Uses generic extraction that works across any job site:
    - LinkedIn, Indeed, Glassdoor, company career pages, etc.
    """
    logger.info(f"Loading job page: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(4)

    # Extract metadata from page
    title = await _extract_meta_title(page)
    company = await _extract_meta_company(page)

    # Extract visible job description text
    job_description = await _extract_visible_text(page)

    if not job_description:
        logger.error("Could not extract any text from the page")
        return {"title": title, "company": company, "description": ""}

    # If title wasn't in metadata, try to extract from description text
    if not title:
        title = _guess_title_from_text(job_description)
    if not company:
        company = _guess_company_from_text(job_description)

    logger.info(f"Extracted: title='{title}', company='{company}'")
    logger.info(f"Description length: {len(job_description)} characters")

    return {"title": title, "company": company, "description": job_description}


async def _extract_meta_title(page) -> str | None:
    """Try to extract job title from common meta tags and HTML elements."""
    strategies = [
        # Open Graph / Twitter meta
        """document.querySelector('meta[property="og:title"]')?.content""",
        """document.querySelector('meta[name="twitter:title"]')?.content""",
        """document.querySelector('meta[name="title"]')?.content""",
        # Common job title selectors across sites
        """document.querySelector('h1[class*="job"]')?.textContent""",
        """document.querySelector('[class*="job-title"]')?.textContent""",
        """document.querySelector('[class*="jobTitle"]')?.textContent""",
        """document.querySelector('[data-testid="jobTitle"]')?.textContent""",
        """document.querySelector('h1')?.textContent""",
        # Indeed-specific
        """document.querySelector('.jobsearch-JobInfoHeader-title')?.textContent""",
        # Glassdoor
        """document.querySelector('[class*="job-title"]')?.textContent""",
    ]
    for js in strategies:
        try:
            result = await page.evaluate(js)
            if result:
                text = result.strip()
                if len(text) > 3 and len(text) < 150:
                    return text
        except Exception:
            continue
    return None


async def _extract_meta_company(page) -> str | None:
    """Try to extract company name from common meta tags and HTML elements."""
    strategies = [
        """document.querySelector('meta[property="og:site_name"]')?.content""",
        """document.querySelector('meta[name="author"]')?.content""",
        """document.querySelector('[class*="company-name"]')?.textContent""",
        """document.querySelector('[class*="companyName"]')?.textContent""",
        """document.querySelector('[data-testid="company-name"]')?.textContent""",
        """document.querySelector('[class*="employer"]')?.textContent""",
        # Indeed
        """document.querySelector('[data-testid="company-name"]')?.textContent""",
        # LinkedIn
        """document.querySelector('a[href*="/company/"]')?.textContent""",
    ]
    for js in strategies:
        try:
            result = await page.evaluate(js)
            if result:
                text = result.strip()
                if len(text) > 1 and len(text) < 100:
                    return text
        except Exception:
            continue
    return None


async def _extract_visible_text(page) -> str:
    """Extract all visible text from the page, focusing on job description areas."""
    try:
        text = await page.evaluate(
            """() => {
                // Try to find job description container first
                const descSelectors = [
                    '[class*="job-description"]',
                    '[class*="jobDescription"]',
                    '[class*="description"]',
                    '[id*="job-description"]',
                    '[id*="description"]',
                    '[data-testid*="description"]',
                    'article',
                    'main',
                ];
                for (const sel of descSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.textContent.trim().length > 200) {
                        return el.textContent.trim();
                    }
                }
                // Fallback: get all visible text from body
                return document.body.innerText;
            }"""
        )
        # Clean up: remove excessive whitespace, limit length
        if text:
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r' {2,}', ' ', text)
            # Take first 10000 chars (job descriptions are usually within this)
            return text[:10000].strip()
    except Exception as e:
        logger.debug(f"Visible text extraction failed: {e}")
    return ""


def _guess_title_from_text(text: str) -> str | None:
    """Try to guess job title from the first few lines of description text."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:10]:
        # Job titles are typically short lines (5-80 chars)
        if 5 < len(line) < 80 and not line.startswith(('http', '•', '-', '*', 'About', 'We')):
            return line
    return None


def _guess_company_from_text(text: str) -> str | None:
    """Try to guess company name from description text."""
    # Look for "Company: X" or "at X" patterns
    patterns = [
        r"(?:Company|Employer|Organization)\s*[:\-]\s*(.+?)(?:\n|$)",
        r"(?:at|@)\s+([A-Z][A-Za-z\s]+?)(?:\n|,|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:2000])
        if match:
            company = match.group(1).strip()
            if 2 < len(company) < 60:
                return company
    return None


def load_job_from_file(file_path: str) -> dict:
    """Load job description from a text file."""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return {"title": None, "company": None, "description": ""}

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        logger.error(f"File is empty: {file_path}")
        return {"title": None, "company": None, "description": ""}

    title = _guess_title_from_text(text)
    company = _guess_company_from_text(text)

    logger.info(f"Loaded from file: title='{title}', company='{company}'")
    return {"title": title, "company": company, "description": text}


def load_job_from_text(text: str) -> dict:
    """Create job info from direct text input."""
    title = _guess_title_from_text(text)
    company = _guess_company_from_text(text)
    logger.info(f"From text input: title='{title}', company='{company}'")
    return {"title": title, "company": company, "description": text}


async def generate_resume(
    job_info: dict, llm: GPTAnswerer, resume_manager: ResumeManager
) -> str | None:
    """Generate a tailored resume from job info and save as PDF."""
    title = job_info.get("title") or "Unknown_Role"
    company = job_info.get("company") or "Unknown_Company"
    description = job_info.get("description", "")

    if not description:
        logger.error("No job description available — cannot generate resume")
        return None

    # Build a job dict for the LLM
    job_dict = {
        "job_title": title,
        "company_name": company,
        "job_description": description,
        "location": "",
        "url": "",
        "company_description": "",
    }
    llm.set_job(job_dict)

    logger.info(f"Generating tailored resume for '{title}' at '{company}'...")
    pdf_base64 = await resume_manager.pdf_base64()

    # Save
    EXTERNAL_RESUME_DIR.mkdir(parents=True, exist_ok=True)
    safe_company = re.sub(r'[^\w\s-]', '', company).strip().replace(' ', '_')
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    # Truncate long names
    safe_company = safe_company[:50]
    safe_title = safe_title[:50]
    filename = f"{safe_company}_{safe_title}.pdf"
    filepath = EXTERNAL_RESUME_DIR / filename

    with open(filepath, "wb") as f:
        f.write(base64.b64decode(pdf_base64))

    logger.info(f"Resume saved: {filepath}")
    return str(filepath)


async def main():
    parser = argparse.ArgumentParser(
        description="Generate a tailored resume from any job posting"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Job posting URL (any site)")
    group.add_argument("--file", help="Path to a text file with the job description")
    group.add_argument("--text", help="Direct job description text")
    args = parser.parse_args()

    # Load secrets and resume data
    dotenv.load_dotenv()
    secrets = {**dotenv.dotenv_values(".env")}
    llm_api_key = secrets.get("llm_api_key")
    llm_proxy = secrets.get("llm_proxy")

    resume_text_path = Path(RESUME_DIR) / "resume_text.txt"
    resume_structured_path = Path(RESUME_DIR) / "structured_resume.yaml"

    if not resume_text_path.exists():
        print(f"Error: Resume text not found at {resume_text_path}")
        sys.exit(1)
    resume_text = resume_text_path.read_text(encoding="utf-8")

    if not resume_structured_path.exists():
        print(f"Error: Structured resume not found at {resume_structured_path}")
        sys.exit(1)
    resume_structured = load_yaml_file(resume_structured_path)
    resume_structured = ResumeStructure(**resume_structured).model_dump()

    # Get job info based on input mode
    job_info = {"title": None, "company": None, "description": ""}

    if args.url:
        # URL mode — use browser to scrape any job site
        browser, context, page = await create_playwright_browser()
        try:
            job_info = await scrape_job_from_url(page, args.url)
        finally:
            try:
                if context:
                    await save_browser_session(context)
                    await stop_tracing(context)
                if browser:
                    await browser.close()
                elif context:
                    await context.close()
            except Exception:
                pass

    elif args.file:
        job_info = load_job_from_file(args.file)

    elif args.text:
        job_info = load_job_from_text(args.text)

    if not job_info.get("description"):
        print("\n❌ Could not extract job description. Please try:")
        print("  --url <job_url>     for any job posting URL")
        print("  --file <path>       for a text file with the job description")
        print("  --text <text>       for direct text input")
        sys.exit(1)

    # Set up resume pipeline and generate
    llm, resume_manager = setup_resume_pipeline(
        llm_api_key, llm_proxy, resume_text, resume_structured
    )

    result = await generate_resume(job_info, llm, resume_manager)

    print("\n" + "=" * 60)
    print("EXTERNAL JOB RESUME GENERATOR")
    print("=" * 60)
    if result:
        print(f"  ✅ Resume saved: {result}")
    else:
        print("  ❌ Failed to generate resume")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
