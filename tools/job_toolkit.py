"""
Job Toolkit — Direct URL Apply & Resume Tailoring from URL.

Usage:
    # Apply directly to one or more job URLs
    python tools/job_toolkit.py apply URL1 [URL2 ...]

    # Generate tailored resume(s) from job description URL(s)
    python tools/job_toolkit.py resume URL1 [URL2 ...]

    # Both: generate resume AND apply
    python tools/job_toolkit.py both URL1 [URL2 ...]

Output:
    Tailored resumes saved to: data/resumes/Manually Created Resumes/
    Named: {Company}_{JobTitle}.pdf
"""

import asyncio
import base64
import os
import re
import sys
from pathlib import Path

import dotenv

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.constants import (
    BROWSER_STORAGE_STATE,
    RESUME_DIR,
    RESUME_TEXT_TEMPLATE_FILE,
)
from config.logger_config import logger

from src.job_manager.linkedin.authenticator_linkedin import LinkedInAuthenticator
from src.job_manager.linkedin.job_manager_linkedin import LinkedInJobManager
from src.job_manager.linkedin.search_customizer_linkedin import SearchCustomizer
from src.job_manager.resume_anonymizer import ResumeAnonymizer
from src.llm.llm_manager import GPTAnswerer
from src.pydantic_models.config_models import Secrets
from src.pydantic_models.prompt_models import ResumeStructure
from src.resume_builder.resume_generator import ResumeGenerator
from src.resume_builder.resume_manager import ResumeManager
from src.resume_builder.style_manager import StyleManager
from src.utils.browser_utils import create_playwright_browser, save_browser_session, stop_tracing
from src.utils.utils import load_yaml_file, save_yaml_file

TAILORED_RESUME_DIR = Path(RESUME_DIR) / "Manually Created Resumes"


async def login(page) -> bool:
    """Authenticate with LinkedIn using saved session or credentials."""
    secrets = {**dotenv.dotenv_values(".env")}
    secrets_config = Secrets(**secrets)

    authenticator = LinkedInAuthenticator(page)
    authenticator.set_parameters(secrets_config.linkedin_email, secrets_config.linkedin_password)
    success = await authenticator.start()
    if success:
        logger.info("Successfully logged into LinkedIn")
    else:
        logger.error("Failed to log into LinkedIn")
    return success


def setup_resume_pipeline(llm_api_key: str, llm_proxy: str, resume_text: str, resume_structured: dict):
    """Set up the resume generation pipeline (shared by both features)."""
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

    return llm, resume_manager, anonymized_structured, anonymized_text


async def generate_tailored_resume(
    page, job_url: str, llm: GPTAnswerer, resume_manager: ResumeManager
) -> str | None:
    """Scrape job description from URL and generate a tailored resume PDF.

    Returns the path to the saved PDF, or None on failure.
    """
    logger.info(f"Scraping job description from: {job_url}")

    # Navigate to the job page
    await page.goto(job_url, wait_until="domcontentloaded")
    await asyncio.sleep(3)

    # Extract job details using the same logic as LinkedInJobManager
    job_manager_temp = LinkedInJobManager(page, "", None, None)
    job = await job_manager_temp._get_detailed_job_description()

    if not job.job_title and not job.company_name:
        logger.error(f"Could not extract job details from {job_url}")
        return None

    company = job.company_name or "Unknown_Company"
    title = job.job_title or "Unknown_Role"

    logger.info(f"Job: {title} at {company}")

    if not job.job_description:
        logger.error(f"No job description found for {title} at {company}")
        return None

    # Set the job for resume tailoring
    job_dict = job.model_dump()
    llm.set_job(job_dict)

    # Generate tailored resume PDF
    logger.info(f"Generating tailored resume for {title} at {company}...")
    pdf_base64 = await resume_manager.pdf_base64()

    # Save to tailored resumes folder
    TAILORED_RESUME_DIR.mkdir(parents=True, exist_ok=True)

    # Clean filename
    safe_company = re.sub(r'[^\w\s-]', '', company).strip().replace(' ', '_')
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    filename = f"{safe_company}_{safe_title}.pdf"
    filepath = TAILORED_RESUME_DIR / filename

    with open(filepath, "wb") as f:
        f.write(base64.b64decode(pdf_base64))

    logger.info(f"Tailored resume saved: {filepath}")
    return str(filepath)


async def apply_to_url(page, job_url: str, linkedin_email: str, resume_anonymizer) -> str:
    """Navigate to a job URL and apply using the existing Easy Apply flow.

    Returns: 'Success', 'Skip', or 'Error'.
    """
    logger.info(f"Applying to: {job_url}")

    search_component = SearchCustomizer(page)
    job_manager = LinkedInJobManager(page, linkedin_email, resume_anonymizer, search_component)

    vacancy = {"url": job_url}
    result = await job_manager.apply_job(vacancy)
    logger.info(f"Result for {job_url}: {result}")
    return result


async def main():
    """Main entry point for the toolkit."""
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1].lower()
    urls = sys.argv[2:]

    if mode not in ("apply", "resume", "both"):
        print(f"Unknown mode: {mode}. Use 'apply', 'resume', or 'both'.")
        sys.exit(1)

    if not urls:
        print("Please provide at least one job URL.")
        sys.exit(1)

    # Validate URLs
    for url in urls:
        if "linkedin.com/jobs/view/" not in url and "linkedin.com/jobs/" not in url:
            print(f"Warning: {url} doesn't look like a LinkedIn job URL. Proceeding anyway.")

    # Load secrets
    dotenv.load_dotenv()
    secrets = {**dotenv.dotenv_values(".env")}
    secrets_config = Secrets(**secrets)
    llm_api_key = secrets.get("llm_api_key")
    llm_proxy = secrets.get("llm_proxy")

    # Load resume data
    resume_text_path = Path(RESUME_DIR) / "resume_text.txt"
    resume_structured_path = Path(RESUME_DIR) / "structured_resume.yaml"

    if not resume_text_path.exists():
        logger.error(f"Resume text not found: {resume_text_path}")
        sys.exit(1)

    resume_text = resume_text_path.read_text(encoding="utf-8")

    if resume_structured_path.exists():
        resume_structured = load_yaml_file(resume_structured_path)
        resume_structured = ResumeStructure(**resume_structured).model_dump()
    else:
        logger.error(f"Structured resume not found: {resume_structured_path}")
        sys.exit(1)

    # Set up browser and login
    browser, context, page = await create_playwright_browser()
    try:
        if not await login(page):
            sys.exit(1)

        results = []

        if mode in ("resume", "both"):
            llm, resume_manager, anon_structured, anon_text = setup_resume_pipeline(
                llm_api_key, llm_proxy, resume_text, resume_structured
            )

            for url in urls:
                try:
                    path = await generate_tailored_resume(page, url, llm, resume_manager)
                    results.append(("resume", url, path or "FAILED"))
                except Exception as e:
                    logger.error(f"Resume generation failed for {url}: {e}")
                    results.append(("resume", url, f"ERROR: {e}"))

        if mode in ("apply", "both"):
            resume_anonymizer = ResumeAnonymizer(resume_structured)
            resume_anonymizer.anonymize_personal_information()

            for url in urls:
                try:
                    result = await apply_to_url(
                        page, url, secrets_config.linkedin_email, resume_anonymizer
                    )
                    results.append(("apply", url, result))
                except Exception as e:
                    logger.error(f"Apply failed for {url}: {e}")
                    results.append(("apply", url, f"ERROR: {e}"))

        # Print summary
        print("\n" + "=" * 60)
        print("TOOLKIT RESULTS")
        print("=" * 60)
        for action, url, result in results:
            status_icon = "✅" if result not in ("FAILED", "Error") and "ERROR" not in str(result) else "❌"
            print(f"  {status_icon} [{action}] {url}")
            print(f"     -> {result}")
        print("=" * 60)

    finally:
        # Cleanup
        try:
            if context:
                await save_browser_session(context)
                await stop_tracing(context)
            if browser:
                await browser.close()
            elif context:
                await context.close()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
