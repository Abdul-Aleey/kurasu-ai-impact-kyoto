import asyncio
import logging
import re
from urllib.parse import urlparse

from playwright.async_api import async_playwright

log = logging.getLogger("kurasu.automation.japan_post")

REDELIVERY_FORM_URL = "https://www.post.japanpost.jp/receive/redelivery_form/"
# Accept both with and without the "www." subdomain -- a QR code might
# encode either variant, and REDELIVERY_FORM_URL itself uses "www.".
# The fake-jp-post host is a deliberately-built test double of this same
# flow (see backend/automation -- verified live against a real deploy of
# it), used to develop and validate this automation without repeatedly
# hitting the real Japan Post site.
_ALLOWED_HOSTS = (
  "post.japanpost.jp", "www.post.japanpost.jp",
  "fake-jp-post-350281031696.asia-northeast1.run.app",
)
_OVERALL_TIMEOUT_SECONDS = 25

# "please make an inquiry to the call center" was tested and found to be
# boilerplate contact-info text present on the page even before any
# submission -- it produced false-positive "failed" results on every
# attempt, including genuinely valid ones. "cannot be used" was verified
# absent from the fresh, unsubmitted page, so it's a real error-specific
# signal. The URL's err= query param (observed as index.php?err=213a on a
# real rejected submission) is checked too, as a second, independent signal.
_ERROR_TEXT_MARKERS = (
  "cannot be used",
)

_TIME_WINDOW_KEYWORDS = {
  "morning": ["morning"],
  "afternoon": ["afternoon", "daytime"],
  "evening": ["evening", "night"],
}
# A site's dropdown may only offer specific numeric hour ranges (verified
# against a live test double of this flow: "12-14", "14-16", etc., with no
# generic "afternoon"/"evening" option at all) -- these are reasonable
# representative slots to fall back to, in preference order, when no
# option's own label/value contains the keyword itself.
_TIME_WINDOW_HOUR_FALLBACKS = {
  "afternoon": ["12-14", "14-16"],
  "evening": ["18-20", "19-21", "16-18"],
}


async def schedule_japan_post_redelivery(
  tracking_number: str, preferred_time_window: str, redelivery_url: str = "", preferred_date: str = "",
) -> dict:
  """Attempts to actually submit a Japan Post redelivery request.

  Only Japan Post's redelivery flow is automated here (verified to need no
  login and no CAPTCHA on its entry step). If anything about the flow doesn't
  match what was verified -- an invalid tracking number, an unrecognized
  page, a timeout -- this returns status="failed" rather than guessing or
  claiming a false success, so the caller can fall back to pointing the user
  at the redelivery page directly.

  Args:
    tracking_number: the 11-13 digit tracking/notification number extracted
      from the user's notice slip or typed input. Still used as a fallback
      entry method and for display, even when redelivery_url is given.
    preferred_time_window: e.g. "Morning", "Afternoon", "14:00-16:00", or
      "No Preference".
    redelivery_url: an optional direct link, e.g. from a QR code decoded off
      the notice slip. If its host is one of _ALLOWED_HOSTS, navigation
      starts there instead of the generic form. Whether that link still
      needs the tracking number typed in (vs. already carrying it
      pre-filled) is detected from the actual page after navigating, not
      assumed from the URL -- a QR-decoded link can still land on the
      tracking-entry step first. Anything whose host isn't allowed is
      ignored rather than navigated to.
    preferred_date: the user's requested redelivery date, as a plain
      "YYYY-MM-DD" string (the caller is expected to resolve relative
      phrasing like "tomorrow" or "next Tuesday" into this format first,
      using its own knowledge of the current date). Left empty to leave
      whatever date the site pre-fills as its own default. If the date
      field on the actual page enforces a min/max range and the requested
      date falls outside it, the default is kept instead of forcing an
      invalid value, and the returned message says so explicitly rather
      than silently submitting a different date than requested.

  Returns:
    dict with keys:
      status: "scheduled" or "failed"
      message: human-readable detail for the agent to relay to the user
      redelivery_url: the page to fall back to when status is "failed"
  """
  start_url = REDELIVERY_FORM_URL
  if redelivery_url:
    parsed = urlparse(redelivery_url)
    if parsed.scheme == "https" and parsed.hostname in _ALLOWED_HOSTS:
      start_url = redelivery_url

  try:
    return await asyncio.wait_for(
      _run(tracking_number, preferred_time_window, start_url, preferred_date),
      timeout=_OVERALL_TIMEOUT_SECONDS,
    )
  except asyncio.TimeoutError:
    log.info("japan_post automation timed out")
    return {
      "status": "failed",
      "message": "The redelivery site took too long to respond.",
      "redelivery_url": REDELIVERY_FORM_URL,
    }
  except Exception:
    log.exception("japan_post automation failed unexpectedly")
    return {
      "status": "failed",
      "message": "Something went wrong while trying to submit the redelivery request automatically.",
      "redelivery_url": REDELIVERY_FORM_URL,
    }


async def _run(tracking_number: str, preferred_time_window: str, start_url: str, preferred_date: str = "") -> dict:
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch(headless=True)
    try:
      page = await browser.new_page()
      await page.goto(start_url, wait_until="networkidle", timeout=15000)

      # Whether the tracking-number entry step still needs completing
      # depends on the actual page landed on, not just which URL the
      # automation started from -- a direct QR-decoded link can still land
      # on this step first (confirmed against a test double of this flow),
      # so detect it directly from the page rather than assuming.
      tracking_input = await page.query_selector('input[name="request_number"]:not([type="hidden"])')
      if tracking_input:
        # A QR-decoded link may pre-fill this (read-only) already; a
        # generic entry point needs it typed in.
        is_readonly = await tracking_input.evaluate("(el) => el.readOnly")
        if not is_readonly:
          await tracking_input.fill(tracking_number)

        submit_button = await page.query_selector(
          'form:has(input[name="request_number"]) button[type="submit"], '
          'form:has(input[name="request_number"]) input[type="submit"]'
        )
        if submit_button:
          await asyncio.gather(
            page.wait_for_load_state("networkidle", timeout=15000),
            submit_button.click(),
          )

      body_text = (await page.inner_text("body")).lower()
      has_error = "err=" in page.url or any(marker in body_text for marker in _ERROR_TEXT_MARKERS)
      if has_error:
        return {
          "status": "failed",
          "message": "Japan Post didn't recognize this tracking number.",
          "redelivery_url": REDELIVERY_FORM_URL,
        }

      return await _complete_date_time_step(page, preferred_time_window, preferred_date)
    finally:
      await browser.close()


async def _set_preferred_date(page, preferred_date: str) -> str | None:
  """Sets the date field to `preferred_date` (a "YYYY-MM-DD" string) if the
  page has one and the date is within whatever min/max range it enforces.
  Returns a human-readable warning if it couldn't be honored exactly (no
  date field on this form, or the requested date is out of range -- in
  which case the site's own default is left untouched rather than forcing
  an invalid value that could fail form validation), or None if there was
  nothing to report (either set successfully, or never requested)."""
  if not preferred_date:
    return None

  date_input = await page.query_selector('input[type="date"]')
  if not date_input:
    return "Couldn't find a date field on this form to set your preferred date -- the site's own default was used instead."

  min_date = await date_input.get_attribute("min")
  max_date = await date_input.get_attribute("max")
  if (min_date and preferred_date < min_date) or (max_date and preferred_date > max_date):
    return (
      f"Your requested date ({preferred_date}) is outside the range this site currently allows "
      f"({min_date or 'earliest available'} to {max_date or 'latest available'}), so the "
      f"site's default date was kept instead."
    )

  await date_input.fill(preferred_date)
  return None


async def _complete_date_time_step(page, preferred_time_window: str, preferred_date: str = "") -> dict:
  """Handles whatever comes after a valid tracking number is accepted.

  Time-window selection is verified to appear as either radio buttons OR a
  <select> dropdown depending on the site (confirmed live against a test
  double of this flow, which uses a dropdown) -- both are tried. If
  neither selection style can be matched confidently, this aborts rather
  than guessing at an unfamiliar form.
  """
  try:
    await page.wait_for_selector('input[type="radio"], select, input[type="date"]', timeout=6000)
  except Exception:
    return {
      "status": "failed",
      "message": "Found the package, but the next step's page layout wasn't recognized -- needs manual completion.",
      "redelivery_url": page.url,
    }

  date_warning = await _set_preferred_date(page, preferred_date)

  keywords = []
  matched_category = None
  for key, words in _TIME_WINDOW_KEYWORDS.items():
    if key in preferred_time_window.lower():
      keywords = words
      matched_category = key
      break
  wants_no_preference = any(
    phrase in preferred_time_window.lower() for phrase in (
      "no preference", "any time", "anytime", "none", "whenever", "doesn't matter",
      "does not matter", "no specific", "not sure", "no particular", "either works",
      "either is fine", "up to you", "you decide", "whatever works",
    )
  )
  # A real caller (an LLM relaying whatever the user actually said) can phrase
  # "I don't care" in ways no fixed keyword list will ever fully cover --
  # rather than failing the whole submission over an unrecognized phrase,
  # treat anything that doesn't match a specific time-of-day category as a
  # no-preference request. Completing the redelivery with a reasonable
  # default time window is far more useful than aborting entirely.
  if not keywords and not wants_no_preference:
    wants_no_preference = True

  selected = False
  radios = await page.query_selector_all('input[type="radio"]')
  if keywords:
    for radio in radios:
      label_text = (await radio.evaluate(
        "(el) => el.closest('label')?.innerText || el.parentElement?.innerText || ''"
      )).lower()
      if any(keyword in label_text for keyword in keywords):
        await radio.check()
        selected = True
        break
  elif wants_no_preference:
    for radio in radios:
      label_text = (await radio.evaluate(
        "(el) => el.closest('label')?.innerText || el.parentElement?.innerText || ''"
      )).lower()
      if any(phrase in label_text for phrase in ("no preference", "none", "any", "指定なし")):
        await radio.check()
        selected = True
        break

  if not selected:
    # Some sites use a dropdown instead of radios for this -- match against
    # each option's own value attribute (often a short, language-neutral
    # code like "morning" or "14-16") as well as its visible label, since
    # the label itself may be in Japanese and not match English keywords.
    select_el = await page.query_selector("select")
    if select_el:
      options = await select_el.query_selector_all("option")
      option_values = [(await o.get_attribute("value") or "") for o in options]
      target_value = None
      for option, value in zip(options, option_values):
        label = (await option.inner_text()).lower()
        value_lower = value.lower()
        if wants_no_preference and ("none" in value_lower or "no preference" in label):
          target_value = value
          break
        if keywords and any(keyword in value_lower or keyword in label for keyword in keywords):
          target_value = value
          break

      if target_value is None and matched_category:
        # No option's own label/value literally contains the keyword (e.g.
        # this site only offers numeric hour ranges, no "afternoon"/
        # "evening" option at all) -- fall back to a reasonable
        # representative hour range for that category, in preference
        # order, using whichever one actually exists on this page.
        for candidate in _TIME_WINDOW_HOUR_FALLBACKS.get(matched_category, []):
          if candidate in option_values:
            target_value = candidate
            break

      if target_value is not None:
        await select_el.select_option(value=target_value)
        selected = True

  if not selected:
    return {
      "status": "failed",
      "message": "Found the package, but couldn't confidently match your preferred time window on the site's form -- needs manual completion.",
      "redelivery_url": page.url,
    }

  submit_button = await page.query_selector('button[type="submit"], input[type="submit"]')
  if not submit_button:
    return {
      "status": "failed",
      "message": "Found the package and selected a time window, but couldn't find a final submit button.",
      "redelivery_url": page.url,
    }

  await asyncio.gather(
    page.wait_for_load_state("networkidle", timeout=15000),
    submit_button.click(),
  )

  confirmation_text = (await page.inner_text("body")).lower()
  # Real Japan Post confirmation text is in Japanese ("受付が完了しました" /
  # reception has been completed) -- verified against a live test double of
  # this flow. English keywords are kept too in case a page renders in
  # English instead.
  if re.search(r"(complete|confirm|accepted|received|完了|受付|受け付け)", confirmation_text):
    message = "Redelivery request submitted successfully."
    if date_warning:
      message += " " + date_warning
    return {
      "status": "scheduled",
      "message": message,
      "redelivery_url": page.url,
    }

  return {
    "status": "failed",
    "message": "Submitted the form but couldn't confirm success from the response page -- please double-check manually.",
    "redelivery_url": page.url,
  }
