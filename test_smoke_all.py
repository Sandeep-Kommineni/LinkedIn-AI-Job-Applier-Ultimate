"""Standalone smoke-test script for all recent feature changes.

Run with:  python test_smoke_all.py
No API keys or browser required.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pydantic_models.config_models import SalaryFilter, SearchConfig
from src.resume_builder.style_manager import StyleManager
from src.utils.utils import check_salary_threshold, parse_salary_from_text


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


# ── 1. Salary parser ────────────────────────────────────────────────────────
section("1. Salary Parser")

test_cases = [
    ("Salary: 3 LPA",                     True,  "INR",  300000),
    ("CTC: 5-12 LPA",                     True,  "INR",  500000),
    ("₹50,000 per month",                 True,  "INR",  600000),
    ("$60k-$80k per year",                True,  "USD",  60000),
    ("We are looking for a ML engineer.", False, None,   None),
    ("4.5 lpa",                           True,  "INR",  450000),
    ("₹100k per month",                   True,  "INR",  1200000),
    ("$5,000 per month",                  True,  "USD",  60000),
    ("10 lakh per annum",                 True,  "INR",  1000000),
]

all_ok = True
for text, expect_found, expect_currency, expect_min in test_cases:
    result = parse_salary_from_text(text)
    ok = result["found"] == expect_found
    if expect_found and expect_currency == "INR":
        ok = ok and result["min_annual_inr"] == expect_min
    elif expect_found and expect_currency == "USD":
        ok = ok and result["min_annual_usd"] == expect_min
    status = "PASS" if ok else "FAIL"
    all_ok = all_ok and ok
    extra = f"  raw='{result.get('raw_match', '')}'" if result["found"] else ""
    print(f"  [{status}] '{text}' -> found={result['found']}{extra}")

# ── 2. Salary threshold logic ───────────────────────────────────────────────
section("2. Salary Threshold Check")

cfg = {"enabled": True, "min_annual_inr": 500000, "min_annual_usd": 14000}

threshold_cases = [
    ("CTC: 3 LPA",                      True,  "low INR skipped"),
    ("CTC: 8 LPA",                      False, "acceptable INR"),
    ("CTC: 20 LPA",                     False, "high INR always allowed"),
    ("₹30,000 per month",               True,  "low monthly skipped"),
    ("$10,000 per year",                True,  "low USD skipped"),
    ("$60,000 per year",                False, "acceptable USD"),
    ("Great opportunity, no salary.",   False, "no salary → allow"),
]

for text, expect_skip, label in threshold_cases:
    skip, reason = check_salary_threshold(text, cfg)
    ok = skip == expect_skip
    status = "PASS" if ok else "FAIL"
    all_ok = all_ok and ok
    detail = reason if skip else "allowed"
    print(f"  {status} {label}: {detail}")

# Disabled filter
skip, _ = check_salary_threshold("3 LPA", {"enabled": False})
ok = skip is False
all_ok = all_ok and ok
print(f"  [{'PASS' if ok else 'FAIL'}] disabled filter allows everything: skip={skip}")

# ── 3. Pydantic config validation ───────────────────────────────────────────
section("3. SearchConfig + SalaryFilter Pydantic Model")

yaml_data = {
    "positions": ["AI Engineer"],
    "remote": True,
    "salary_filter": {"enabled": True, "min_annual_inr": 500000, "min_annual_usd": 14000},
    "company_blacklist": ["Turing", "Mercor"],
    "location_blacklist": ["Delhi"],
    "date": {"24_hours": True},
}
try:
    cfg_model = SearchConfig(**yaml_data)
    ok = cfg_model.salary_filter.enabled is True
    ok = ok and cfg_model.salary_filter.min_annual_inr == 500000
    ok = ok and "Turing" in cfg_model.company_blacklist
    ok = ok and cfg_model.date.day_24_hours is True  # alias works
    status = "PASS" if ok else "FAIL"
    all_ok = all_ok and ok
    print(f"  {status} SearchConfig parsed: salary={cfg_model.salary_filter}, "
          f"blacklist={cfg_model.company_blacklist}, date={cfg_model.date}")
except Exception as e:
    all_ok = False
    print(f"  [FAIL] SearchConfig failed: {e}")

# Empty salary_filter defaults to disabled
try:
    cfg2 = SearchConfig(positions=["X"])
    ok = cfg2.salary_filter.enabled is False
    status = "PASS" if ok else "FAIL"
    all_ok = all_ok and ok
    print(f"  {status} Default SalaryFilter disabled: {cfg2.salary_filter.enabled}")
except Exception as e:
    all_ok = False
    print(f"  [FAIL] Default SalaryFilter failed: {e}")

# ── 4. Style manager detects Cobalt Pro ─────────────────────────────────────
section("4. Style Manager — Cobalt Pro Detection")

sm = StyleManager()
sm.set_styles_directory(Path("src/resume_builder/resume_style"))
styles = sm.get_styles()

if "Cobalt Pro" in styles:
    file_name, author = styles["Cobalt Pro"]
    print(f"  [PASS] Cobalt Pro detected: file={file_name}, author={author}")
else:
    all_ok = False
    print("  [FAIL] Cobalt Pro NOT found in styles")
    print(f"    Available: {list(styles.keys())}")

# ── 5. Blacklist check ──────────────────────────────────────────────────────
section("5. Blacklist Logic")

from src.job_manager.search_customizer import BaseSearchCustomizer

# Concrete subclass for testing (BaseSearchCustomizer is abstract)
class TestCustomizer(BaseSearchCustomizer):
    async def set_search_params(self):
        pass

tc = TestCustomizer(page=None)
tc.company_blacklist = ["Turing", "Mercor", "Crossing Hurdles"]
tc.title_blacklist = ["Senior", "Staff"]
tc.location_blacklist = ["Delhi", "Mumbai"]

blacklist_cases = [
    ("ML Engineer",  "Turing",           "Hyderabad",  True,  "company blacklisted"),
    ("ML Engineer",  "Google",           "Delhi",      True,  "location blacklisted"),
    ("Senior Dev",   "Google",           "Hyderabad",  True,  "title blacklisted"),
    ("AI Engineer",  "Google",           "Hyderabad",  False, "clean job allowed"),
    ("ML Intern",    "Crossing Hurdles", "Remote",     True,  "company blacklisted"),
]

for title, company, location, expect, label in blacklist_cases:
    result = tc.is_job_blacklisted(title, company, location)
    ok = result == expect
    status = "PASS" if ok else "FAIL"
    all_ok = all_ok and ok
    print(f"  {status} {label}: {title} @ {company} ({location})")

# ── Summary ─────────────────────────────────────────────────────────────────
section("SUMMARY")
if all_ok:
    print("  [PASS] All smoke tests passed!")
else:
    print("  [FAIL] Some tests failed -- review output above.")
    sys.exit(1)
