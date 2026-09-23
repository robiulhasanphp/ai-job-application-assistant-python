import csv
import os
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException,
    NoSuchElementException,
)

# ============================================================
# CONFIG
# ============================================================
SEARCH_URL = (
    "https://www.stepstone.de/jobs/vollzeit/"
    "php-laravel-symfony-mysql-active-directory-entra-id-python"
    "?page=6"
    "&action=active_filter_removed%3BapplicationMethod%3BINTERNAL"
    "&us=40000"
    "&searchOrigin=Resultlist_top-search"
    "&di=IT&di=Ingenieurwesen&di=Administration"
    "&sdi=250949&sdi=251279&sdi=251192&sdi=251261&sdi=251125"
    "&sdi=251178&sdi=251263&sdi=251219&sdi=251275&sdi=251249&sdi=250882"
)

CV_PATH = r"C:\Users\robiu\Desktop\IT_PHP_Job\IT\Md_Robiul_Hasan_CV.pdf"
LOG_FILE = r"C:\Users\robiu\Desktop\IT_PHP_Job\stepstone_application_log.csv"
MAX_SEARCH_PAGES = 50
MAX_EXTERNAL_STEPS = 15
WAIT = 20

# One matching keyword is enough, as requested.
CV_KEYWORDS = [
    "PHP", "Laravel", "Symfony", "MySQL", "Active Directory", "Entra ID",
    "Microsoft Entra ID", "Python", "System Engineer", "System Engineering",
    "Systemadministrator", "System Administration", "IT-Systemadministrator",
    "IT Administrator", "IT Administration", "IT Support", "Software Developer",
    "Software Engineer", "Backend Developer", "Full Stack Developer", "Web Developer",
    "Microsoft", "Windows Server", "Linux", "SQL", "REST API", "API", "Git", "Docker",
]

PROFILE = {
    "first_name": "Robiul",
    "last_name": "Hasan",
    "email": "robiulhasan.bd1122@gmail.com",
    "phone": "17659483724",
    "street": "BrückenStraße",
    "house_number": "",
    "postcode": "47053",
    "city": "Duisburg",
    "country": "Deutschland",
    "birth_country": "Bangladesch",
    "nationality": "Bangladesh",
    "date_of_birth": "05/10/1992",
    "place_of_birth": "",
    "communication_language": "Englisch",
    "available_from": "01/10/2026",
    "salary": "50000",
    "relocation": "yes",
    "work_authorization": "yes",
    "disability": "no",
    "sponsorship": "no",
    "bechtle_referral": "no",
    "message": "Ich bin an dieser Stelle sehr interessiert.",
}

# Never invent an answer to a question for which there is no profile value.
# The script will stop that application and leave the page open for manual completion.
UNKNOWN_REQUIRED_IS_MANUAL = True

NEXT_WORDS = [
    "weiter", "nächster schritt", "nächste", "next", "continue", "proceed",
    "continue application", "weiter zum nächsten schritt", "fortfahren",
]
SUBMIT_WORDS = [
    "übermitteln", "bewerbung abschicken", "bewerbung absenden", "bewerbung senden",
    "bewerben", "submit", "submit application", "send application", "send my application",
    "complete application", "finish application", "application senden", "apply",
]
APPLY_WORDS = [
    "jetzt bewerben", "apply now", "apply", "bewerben", "ich bin interessiert",
    "bewerbung fortsetzen", "start application", "start your application",
]
ALREADY_WORDS = ["schon beworben", "bereits beworben", "already applied", "application submitted"]

# ============================================================
# BASIC HELPERS
# ============================================================
def clean(text):
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def norm(text):
    return clean(text).lower()


def wait_page(driver, timeout=WAIT):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass


def body_text(driver):
    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return ""


def safe_click(driver, element):
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center',behavior:'instant'});", element
        )
        time.sleep(0.25)
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)
        return True
    except Exception as exc:
        print("CLICK ERROR:", exc)
        return False


def wait_for_navigation_or_tab(driver, old_url, old_handles, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            current_handles = set(driver.window_handles)
            new_handles = current_handles - old_handles
            if new_handles:
                handle = next(iter(new_handles))
                driver.switch_to.window(handle)
                wait_page(driver)
                return "new_tab"
            if driver.current_url != old_url:
                wait_page(driver)
                return "same_tab"
        except Exception:
            pass
        time.sleep(0.35)
    return None


def log_result(title, url, matches, status):
    try:
        Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["time", "job", "url", "matches", "status"])
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"), title, url,
                " | ".join(matches), status,
            ])
    except Exception as exc:
        print("LOG ERROR:", exc)


def switch_back(driver, handle):
    try:
        driver.switch_to.window(handle)
        wait_page(driver)
        return True
    except Exception:
        return False


def close_current_application_tab(driver, results_handle):
    try:
        if driver.current_window_handle != results_handle:
            driver.close()
            driver.switch_to.window(results_handle)
            wait_page(driver)
    except Exception:
        try:
            driver.switch_to.window(results_handle)
        except Exception:
            pass

# ============================================================
# JOB LIST / JOB DETAIL
# ============================================================
def get_job_cards(driver):
    selectors = [
        "article[data-testid='job-item']",
        "[data-testid='job-item']",
        "article[id^='job-item-']",
    ]
    cards, seen = [], set()
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                key = element.get_attribute("id") or clean(element.text)[:250]
                if key and key not in seen:
                    seen.add(key)
                    cards.append(element)
            except Exception:
                pass
    return cards


def get_job_info(card):
    title = ""
    url = ""
    try:
        lines = [clean(x) for x in card.text.splitlines() if clean(x)]
        title = lines[0] if lines else ""
    except Exception:
        pass
    try:
        for link in card.find_elements(By.CSS_SELECTOR, "a[href]"):
            href = link.get_attribute("href")
            if href:
                url = href
                break
    except Exception:
        pass
    return title, url


def open_job_card(driver, card):
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    print("CLICKING ACTUAL JOB POST...")
    if not safe_click(driver, card):
        return False
    result = wait_for_navigation_or_tab(driver, old_url, old_handles, 15)
    if result:
        print("JOB OPENED:", result)
        time.sleep(1.5)
        return True
    print("JOB POST DID NOT OPEN.")
    return False


def already_applied(driver):
    page = norm(body_text(driver))
    if any(word in page for word in ALREADY_WORDS):
        return True
    try:
        for button in driver.find_elements(By.CSS_SELECTOR, "button[data-testid='harmonised-apply-button']"):
            txt = norm(button.text)
            if any(word in txt for word in ALREADY_WORDS):
                return True
    except Exception:
        pass
    return False


def find_cv_matches(driver):
    text = norm(body_text(driver))
    return list(dict.fromkeys(k for k in CV_KEYWORDS if norm(k) in text))

# ============================================================
# STEPSTONE APPLICATION ROUTING
# ============================================================
def visible_enabled(elements):
    for el in elements:
        try:
            if el.is_displayed() and el.is_enabled():
                yield el
        except Exception:
            continue


def find_stepstone_apply_button(driver):
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, "button[data-testid='harmonised-apply-button']")
        for el in visible_enabled(elements):
            txt = norm(el.text)
            if any(word in txt for word in ALREADY_WORDS):
                continue
            if any(word in txt for word in ["ich bin interessiert", "bewerbung fortsetzen", "bewerben", "apply"]):
                return el
    except Exception:
        pass
    # Generic fallback, but only within the application button area.
    xpaths = [
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'ich bin interessiert')]",
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ','abcdefghijklmnopqrstuvwxyzäöü'),'bewerbung fortsetzen')]",
        "//button[normalize-space()='Bewerben']",
        "//button[normalize-space()='Apply']",
    ]
    for xp in xpaths:
        try:
            for el in visible_enabled(driver.find_elements(By.XPATH, xp)):
                return el
        except Exception:
            pass
    return None


def find_stepstone_external_button(driver):
    selectors = [
        "button[data-testid='continueToCompanySite']",
        "button[aria-label='Jetzt bewerben']",
    ]
    for selector in selectors:
        try:
            for el in visible_enabled(driver.find_elements(By.CSS_SELECTOR, selector)):
                return el
        except Exception:
            pass
    try:
        for el in visible_enabled(driver.find_elements(By.XPATH, "//button[contains(., 'Jetzt bewerben') or contains(., 'Apply') or contains(., 'Bewerben')]") ):
            return el
    except Exception:
        pass
    return None


def start_stepstone_application(driver):
    button = find_stepstone_apply_button(driver)
    if not button:
        return False
    print("STEPSTONE APPLY:", clean(button.text))
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    if not safe_click(driver, button):
        return False
    result = wait_for_navigation_or_tab(driver, old_url, old_handles, 15)
    if result:
        print("APPLICATION PAGE:", result)
    else:
        time.sleep(2)
    wait_page(driver)
    return True


def start_external_application(driver):
    button = find_stepstone_external_button(driver)
    if not button:
        return False
    print("EXTERNAL APPLY BUTTON:", clean(button.text))
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    if not safe_click(driver, button):
        return False
    result = wait_for_navigation_or_tab(driver, old_url, old_handles, 20)
    if result:
        print("EXTERNAL SITE OPENED:", result)
        time.sleep(2)
        return True
    time.sleep(3)
    return True

# ============================================================
# GENERIC / THIRD-PARTY FORM ENGINE
# ============================================================
def label_text_for(driver, field):
    try:
        fid = field.get_attribute("id")
        if fid:
            labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{fid}']")
            if labels:
                return clean(" ".join(x.text for x in labels))
    except Exception:
        pass
    try:
        aria = field.get_attribute("aria-label") or field.get_attribute("placeholder")
        if aria:
            return clean(aria)
    except Exception:
        pass
    try:
        parent = field.find_element(By.XPATH, "..")
        return clean(parent.text)[:250]
    except Exception:
        return ""


def field_signature(driver, field):
    parts = [
        field.get_attribute("name") or "",
        field.get_attribute("id") or "",
        field.get_attribute("placeholder") or "",
        field.get_attribute("aria-label") or "",
        field.get_attribute("type") or "",
        label_text_for(driver, field),
    ]
    return norm(" ".join(parts))


def all_form_fields(driver):
    try:
        return driver.find_elements(By.CSS_SELECTOR, "input, textarea, select")
    except Exception:
        return []


def find_field(driver, keywords, types=None):
    keys = [norm(k) for k in keywords]
    for field in all_form_fields(driver):
        try:
            if not field.is_displayed() or field.get_attribute("disabled") is not None:
                continue
            if types and norm(field.get_attribute("type")) not in types:
                continue
            sig = field_signature(driver, field)
            if any(k in sig for k in keys):
                return field
        except Exception:
            continue
    return None


def set_text_field(driver, field, value):
    if not field or value == "":
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", field)
        field.click()
        try:
            field.clear()
        except Exception:
            pass
        field.send_keys(value)
        return True
    except Exception:
        try:
            driver.execute_script(
                "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input',{bubbles:true})); arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                field, value,
            )
            return True
        except Exception:
            return False


def set_first(driver, keywords, value, types=None):
    field = find_field(driver, keywords, types)
    if field and set_text_field(driver, field, value):
        print("FILLED:", label_text_for(driver, field), "=>", value)
        return True
    return False


def select_value(driver, field, values):
    try:
        sel = Select(field)
        opts = sel.options
        wanted = [norm(v) for v in values]
        for option in opts:
            text = norm(option.text)
            value = norm(option.get_attribute("value"))
            if any(w in text or w in value for w in wanted):
                sel.select_by_visible_text(option.text)
                return True
    except Exception:
        pass
    return False


def set_select(driver, keywords, values):
    field = find_field(driver, keywords)
    if field and norm(field.tag_name) == "select" and select_value(driver, field, values):
        print("SELECTED:", label_text_for(driver, field), "=>", values)
        return True
    return False


def choose_boolean(driver, keywords, yes):
    wanted = ["ja", "yes", "true", "y"] if yes else ["nein", "no", "false", "n"]
    keys = [norm(k) for k in keywords]
    # Prefer labels whose own text contains the question and an answer.
    for label in driver.find_elements(By.TAG_NAME, "label"):
        try:
            txt = norm(label.text)
            if not txt or not any(k in txt for k in keys):
                continue
            if any(w in txt for w in wanted):
                safe_click(driver, label)
                print("BOOLEAN:", label.text)
                return True
        except Exception:
            continue
    # Radio/checkbox groups: inspect each option's label text and surrounding group.
    for field in driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']"):
        try:
            if not field.is_displayed():
                continue
            fid = field.get_attribute("id")
            option_text = ""
            if fid:
                ls = driver.find_elements(By.CSS_SELECTOR, f"label[for='{fid}']")
                option_text = clean(" ".join(x.text for x in ls)) if ls else ""
            parent_text = clean(field.find_element(By.XPATH, "../..").text)
            group_text = norm(option_text + " " + parent_text)
            if any(k in group_text for k in keys) and any(w in norm(option_text) for w in wanted):
                if not field.is_selected():
                    safe_click(driver, field)
                return True
        except Exception:
            continue
    return False


def fill_profile_generic(driver):
    # Contact details
    set_first(driver, ["vorname", "first name", "given name", "firstname"], PROFILE["first_name"])
    set_first(driver, ["nachname", "last name", "surname", "lastname"], PROFILE["last_name"])
    set_first(driver, ["e-mail-adresse", "email address", "email", "e-mail"], PROFILE["email"])
    set_first(driver, ["telefonnummer", "telephone", "phone", "mobil", "mobile"], PROFILE["phone"])

    # Address
    set_first(driver, ["straße", "strasse", "street", "address line", "address"], PROFILE["street"])
    if PROFILE["house_number"]:
        set_first(driver, ["hausnummer", "house number"], PROFILE["house_number"])
    set_first(driver, ["postleitzahl", "plz", "postcode", "postal code", "zip"], PROFILE["postcode"])
    set_first(driver, ["stadt", "ort", "city"], PROFILE["city"])
    set_select(driver, ["land", "country"], [PROFILE["country"], "Germany"])

    # Personal details
    set_select(driver, ["geburtsland", "country of birth"], [PROFILE["birth_country"], "Bangladesh"])
    set_select(driver, ["staatsangehörigkeit", "staatsangehoerigkeit", "nationality"], [PROFILE["nationality"], "Bangladesh"])
    set_first(driver, ["geburtsdatum", "birth date", "date of birth", "birthday"], PROFILE["date_of_birth"])
    if PROFILE["place_of_birth"]:
        set_first(driver, ["geburtsort", "place of birth"], PROFILE["place_of_birth"])
    set_select(driver, ["kommunikationssprache", "communication language", "language"], [PROFILE["communication_language"], "English"])

    # Job details
    set_first(driver, ["frühestmöglicher eintrittstermin", "frühester eintritt", "earliest start", "available from", "start date", "verfügbar ab"], PROFILE["available_from"])
    set_first(driver, ["gehaltsvorstellung", "salary expectation", "expected salary", "desired salary", "gehalt"], PROFILE["salary"])
    set_first(driver, ["nachricht", "message", "cover message", "motivation"], PROFILE["message"])

    # Common yes/no questions. Only answer questions we explicitly know.
    choose_boolean(driver, ["umzug", "umzugsbereit", "relocation", "relocate"], PROFILE["relocation"] == "yes")
    choose_boolean(driver, ["arbeitserlaubnis", "aufenthaltserlaubnis", "work authorization", "work permit", "right to work"], PROFILE["work_authorization"] == "yes")
    choose_boolean(driver, ["schwerbehindert", "behinderung", "disability", "disabled"], PROFILE["disability"] == "yes")
    choose_boolean(driver, ["sponsorship", "visa sponsorship", "visum", "visa"], PROFILE["sponsorship"] == "yes")
    choose_boolean(driver, ["bechtle mitarbeitenden", "bechtle mitarbeiter", "employee referral", "referral"], PROFILE["bechtle_referral"] == "yes")


def upload_cv_if_requested(driver):
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
    except Exception:
        return False
    for inp in inputs:
        try:
            if not inp.is_displayed() and not inp.is_enabled():
                continue
            sig = field_signature(driver, inp)
            # Upload CV only for resume/CV/application documents, not arbitrary attachments.
            if any(k in sig for k in ["cv", "resume", "lebenslauf", "curriculum", "bewerbung", "resume file"]):
                inp.send_keys(CV_PATH)
                print("CV UPLOADED")
                return True
        except Exception:
            continue
    return False


def required_empty_fields(driver):
    missing = []
    for field in all_form_fields(driver):
        try:
            if not field.is_displayed() or field.get_attribute("disabled") is not None:
                continue
            required = field.get_attribute("required") is not None or field.get_attribute("aria-required") == "true"
            if not required:
                # Some sites mark required fields on their associated label.
                fid = field.get_attribute("id")
                if fid:
                    labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{fid}']")
                    required = any("*" in clean(x.text) for x in labels)
            if not required:
                continue
            typ = norm(field.get_attribute("type"))
            if typ in ("hidden", "submit", "button"):
                continue
            if typ in ("radio", "checkbox"):
                group_name = field.get_attribute("name")
                if group_name:
                    group = driver.find_elements(By.CSS_SELECTOR, f"input[name='{group_name}']")
                    if any(x.is_selected() for x in group):
                        continue
                elif field.is_selected():
                    continue
            elif norm(field.tag_name) == "select":
                try:
                    if not Select(field).first_selected_option.get_attribute("value"):
                        missing.append(label_text_for(driver, field) or field.get_attribute("name") or "select")
                except Exception:
                    pass
                continue
            else:
                value = field.get_attribute("value") or ""
                if not value.strip():
                    missing.append(label_text_for(driver, field) or field.get_attribute("name") or "field")
        except Exception:
            continue
    # Deduplicate
    out = []
    for x in missing:
        if x and x not in out:
            out.append(x)
    return out

# ============================================================
# GENERIC BUTTON INTELLIGENCE
# ============================================================
def button_text(el):
    try:
        return norm(el.text or el.get_attribute("aria-label") or el.get_attribute("value") or "")
    except Exception:
        return ""


def application_page_signal(driver):
    """
    Recognize normal forms, StepStone Smart Apply, and employer/ATS
    application URLs. Some modern React forms do not expose a normal
    <form> element, so URL/page structure is also used.
    """
    text = norm(body_text(driver))
    url = norm(driver.current_url)
    form_count = len(all_form_fields(driver))

    signals = [
        "application", "bewerbung", "bewerben", "lebenslauf", "resume",
        "contact details", "kontaktdetails", "personal information",
        "persönliche daten", "gehaltsvorstellung", "salary",
        "upload cv", "upload resume", "bewerbung abschicken",
        "bewerbung fortsetzen", "jetzt bewerben", "weiter",
    ]

    # StepStone's Smart Apply route is itself the application page.
    if "/application/" in url or "/application" in url:
        return True

    # Common ATS/application paths.
    if any(x in url for x in [
        "/apply", "/application", "/bewerbung", "/jobs/apply",
        "/careers/apply", "/job/apply", "/candidate",
    ]):
        return True

    return (
        form_count >= 1
        and sum(1 for s in signals if s in text) >= 1
    )


def find_next_or_apply_button(driver):
    candidates = []
    try:
        candidates.extend(driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit'], input[type='button'], a"))
    except Exception:
        pass
    scored = []
    for el in candidates:
        try:
            if not el.is_displayed() or not el.is_enabled():
                continue
            txt = button_text(el)
            if not txt:
                continue
            score = 0
            if any(w == txt for w in ["weiter", "next", "continue", "proceed"]):
                score += 80
            elif any(w in txt for w in NEXT_WORDS):
                score += 65
            if any(w in txt for w in APPLY_WORDS):
                score += 70
            if any(w in txt for w in SUBMIT_WORDS):
                score += 100
            if any(w in txt for w in ["login", "anmelden", "sign in", "registrieren", "register", "zurück", "back"]):
                score -= 100
            if score > 0:
                scored.append((score, el))
        except Exception:
            continue
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def is_final_submit_button(el):
    txt = button_text(el)
    if any(w in txt for w in ["weiter", "next", "continue", "proceed"]):
        return False
    return any(w in txt for w in SUBMIT_WORDS)


def confirmation_detected(driver):
    text = norm(body_text(driver))
    confirmations = [
        "vielen dank für ihre bewerbung", "vielen dank für deine bewerbung",
        "bewerbung wurde erfolgreich", "bewerbung erfolgreich", "application submitted",
        "application has been submitted", "thank you for applying", "thank you for your application",
        "erfolgreich übermittelt", "erfolgreich gesendet", "application received",
    ]
    return any(x in text for x in confirmations)

# ============================================================
# FINAL SUBMISSION / MANUAL COMPLETION CONTROL
# ============================================================
def confirm_final_submission(driver, title="", manual=False):
    """
    Every job must be confirmed before final submission.

    Automatic form completion is allowed, but the final submission is
    always gated by the terminal.

    YES  -> click the final application button
    DONE -> user already submitted manually
    NO   -> leave the application open and stop
    """
    print()
    print("=" * 72)
    print("FINAL APPLICATION CONFIRMATION")
    print("=" * 72)
    if title:
        print("JOB:", title)

    if manual:
        print("The script could not safely complete all required fields.")
        print("The application is still open in Chrome.")
        print()
        print("Complete/review the application manually, then choose:")
        print("  YES  = script clicks the final application button")
        print("  DONE = you already submitted manually")
        print("  NO   = stop and leave the application open")
        answer = input("Your choice [YES/DONE/NO]: ").strip().lower()
        if answer in ("yes", "y"):
            return "submit"
        if answer == "done":
            return "manual_submitted"
        return "stop"

    print("All known required fields have been filled.")
    print("Review the application in Chrome.")
    answer = input("Submit this job now? [YES/no]: ").strip().lower()
    return "submit" if answer in ("yes", "y") else "stop"


def submit_current_application(driver):
    """Submit only a high-confidence final application button."""
    button = find_next_or_apply_button(driver)
    if not button:
        return "final_button_not_found"

    if not is_final_submit_button(button):
        return "final_button_not_found"

    label = button_text(button)
    print("FINAL BUTTON:", label)

    old_url = driver.current_url
    old_handles = set(driver.window_handles)

    if not safe_click(driver, button):
        return "final_click_failed"

    wait_for_navigation_or_tab(driver, old_url, old_handles, 15)
    time.sleep(3)

    if confirmation_detected(driver):
        return "submitted_confirmed"

    return "submitted_unconfirmed"


# ============================================================
# EXTERNAL APPLICATION LOOP
# ============================================================
def process_external_application(driver):
    print("\n--- THIRD-PARTY APPLICATION ENGINE ---")
    original_handle = driver.current_window_handle
    try:
        for step in range(1, MAX_EXTERNAL_STEPS + 1):
            wait_page(driver)
            print(f"EXTERNAL STEP {step}: {driver.current_url}")

            if any(w in norm(body_text(driver)) for w in ALREADY_WORDS):
                print("ALREADY APPLIED -> CLOSE THIS APPLICATION TAB")
                return "Already applied"

            # Some ATSs have a first page with a separate Apply button.
            if not application_page_signal(driver):
                button = find_next_or_apply_button(driver)
                if button:
                    print("FIRST/START BUTTON:", clean(button.text))
                    old_url = driver.current_url
                    old_handles = set(driver.window_handles)
                    safe_click(driver, button)
                    wait_for_navigation_or_tab(driver, old_url, old_handles, 10)
                    time.sleep(1)
                    continue
                return "External application page not recognized; manual completion"

            fill_profile_generic(driver)
            upload_cv_if_requested(driver)
            time.sleep(0.5)

            missing = required_empty_fields(driver)
            if missing:
                # A required field may be an application-specific question that we cannot safely infer.
                print("REQUIRED FIELDS STILL EMPTY:")
                for item in missing[:20]:
                    print("  -", item)
                if UNKNOWN_REQUIRED_IS_MANUAL:
                    return "Manual completion required: " + " | ".join(missing[:10])

            button = find_next_or_apply_button(driver)
            if not button:
                return "No Next/Apply/Submit button found"

            txt = clean(button.text or button.get_attribute("value") or button.get_attribute("aria-label"))
            print("ACTION BUTTON:", txt)

            # Do not blindly click a generic button. It must be a high-confidence application control.
            if is_final_submit_button(button):
                missing = required_empty_fields(driver)
                if missing:
                    return "Manual completion required before final submit: " + " | ".join(missing[:10])

                decision = confirm_final_submission(driver)
                if decision != "submit":
                    return "Final submission not confirmed; application left open"

                result = submit_current_application(driver)
                if result == "submitted_confirmed":
                    return "Submitted and confirmation detected"
                if result == "submitted_unconfirmed":
                    return "Submitted; confirmation not detected"
                return "Final submission failed; application left open"

            # Next / Continue / Apply step.
            old_url = driver.current_url
            old_handles = set(driver.window_handles)
            if not safe_click(driver, button):
                return "Next/Apply click failed; manual completion"
            wait_for_navigation_or_tab(driver, old_url, old_handles, 15)
            time.sleep(1.5)

        return "Maximum external application steps reached; manual completion"
    except Exception as exc:
        print("EXTERNAL ENGINE ERROR:", exc)
        return "External engine error; manual completion"
    finally:
        # Do not close the page when manual work is required. The caller decides.
        pass

# ============================================================
# INTERNAL STEPSTONE FORM
# ============================================================
def upload_cv_stepstone(driver):
    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
        try:
            if inp.is_enabled():
                inp.send_keys(CV_PATH)
                print("CV UPLOADED TO STEPSTONE")
                return True
        except Exception:
            continue
    return False


def process_stepstone_internal(driver):
    upload_cv_stepstone(driver)
    fill_profile_generic(driver)
    missing = required_empty_fields(driver)
    if missing:
        return "Manual completion required: " + " | ".join(missing[:10])

    button = find_next_or_apply_button(driver)
    if not button:
        return "StepStone submit button not found"
    txt = clean(button.text)
    if is_final_submit_button(button):
        missing = required_empty_fields(driver)
        if missing:
            return "Manual completion required before final submit: " + " | ".join(missing[:10])

        decision = confirm_final_submission(driver)
        if decision != "submit":
            return "Final submission not confirmed; application left open"

        result = submit_current_application(driver)
        if result == "submitted_confirmed":
            return "StepStone submitted and confirmation detected"
        if result == "submitted_unconfirmed":
            return "StepStone submitted; confirmation not detected"
        return "StepStone final submission failed; application left open"
    # If internal flow has more than one page, process it through the same engine.
    return process_external_application(driver)

# ============================================================
# ONE JOB
# ============================================================
def process_job(driver, card, results_handle):
    title, card_url = get_job_info(card)
    if not open_job_card(driver, card):
        log_result(title, card_url, [], "Job post could not be opened")
        return

    application_handle = driver.current_window_handle
    job_url = driver.current_url
    print("JOB:", title)
    print("URL:", job_url)

    if already_applied(driver):
        print("SCHON BEWORBEN -> SKIP AND CLOSE TAB")
        log_result(title, job_url, [], "Already applied")
        close_current_application_tab(driver, results_handle)
        return

    matches = find_cv_matches(driver)
    print("CV MATCHES:", matches)
    if not matches:
        print("NO CV KEYWORD MATCH -> SKIP")
        log_result(title, job_url, [], "No CV keyword match")
        close_current_application_tab(driver, results_handle)
        return

    print("RELEVANT JOB -> APPLY")

    # StepStone internal route.
    if start_stepstone_application(driver):
        # It may now be an internal application page or an external company page.
        time.sleep(1)
        if already_applied(driver):
            log_result(title, job_url, matches, "Already applied")
            close_current_application_tab(driver, results_handle)
            return

        # If the StepStone internal application form is visible, use the profile engine.
        text = norm(body_text(driver))
        if any(x in text for x in ["kontaktdetails", "contact details", "bewerbung abschicken", "application"]):
            result = process_stepstone_internal(driver)
        else:
            # The button may have redirected to an employer/ATS.
            result = process_external_application(driver)

        print("APPLICATION RESULT:", result)

        if (
            result.startswith("Manual completion")
            or "manual completion" in result.lower()
            or "left open" in result.lower()
            or "not confirmed" in result.lower()
            or "final submission failed" in result.lower()
        ):
            # Keep the application tab open. The user can complete unknown fields.
            print()
            print("APPLICATION LEFT OPEN FOR MANUAL COMPLETION.")
            print("Finish/review it in Chrome, then return to this terminal.")

            decision = confirm_final_submission(
                driver,
                title=title,
                manual=True,
            )

            if decision == "submit":
                final_result = submit_current_application(driver)
                print("FINAL RESULT:", final_result)
                log_result(title, job_url, matches, final_result)
                if final_result.startswith("submitted"):
                    close_current_application_tab(driver, results_handle)
                    return

                print("Final submission was not completed.")
                print("Application remains open. Automation will stop.")
                log_result(title, job_url, matches, "Manual/failed final submission")
                switch_back(driver, results_handle)
                return

            if decision == "manual_submitted":
                print("USER CONFIRMED MANUAL SUBMISSION.")
                log_result(title, job_url, matches, "Submitted manually by user")
                close_current_application_tab(driver, results_handle)
                return

            print("NOT CONFIRMED -> application remains open.")
            print("Automation stops so the application cannot be skipped silently.")
            log_result(title, job_url, matches, "Submission not confirmed")
            switch_back(driver, results_handle)
            return

        log_result(title, job_url, matches, result)
        close_current_application_tab(driver, results_handle)
        return

    # StepStone detail page has an external "Jetzt bewerben" route.
    if start_external_application(driver):
        result = process_external_application(driver)
        print("EXTERNAL RESULT:", result)

        if (
            result.startswith("Manual completion")
            or "manual completion" in result.lower()
            or "left open" in result.lower()
            or "not confirmed" in result.lower()
            or "final submission failed" in result.lower()
        ):
            print()
            print("EXTERNAL APPLICATION LEFT OPEN FOR MANUAL COMPLETION.")
            print("Finish/review it in Chrome, then return to this terminal.")

            decision = confirm_final_submission(
                driver,
                title=title,
                manual=True,
            )

            if decision == "submit":
                final_result = submit_current_application(driver)
                print("FINAL RESULT:", final_result)
                log_result(title, job_url, matches, final_result)
                if final_result.startswith("submitted"):
                    close_current_application_tab(driver, results_handle)
                    return

                print("Final submission failed; application remains open.")
                switch_back(driver, results_handle)
                return

            if decision == "manual_submitted":
                print("USER CONFIRMED MANUAL SUBMISSION.")
                log_result(title, job_url, matches, "Submitted manually by user")
                close_current_application_tab(driver, results_handle)
                return

            print("NOT CONFIRMED -> application remains open.")
            print("Automation stops.")
            log_result(title, job_url, matches, "Submission not confirmed")
            switch_back(driver, results_handle)
            return

        log_result(title, job_url, matches, result)
        close_current_application_tab(driver, results_handle)
        return

    print("NO APPLICATION ROUTE DETECTED")
    log_result(title, job_url, matches, "Application button not found")
    close_current_application_tab(driver, results_handle)

# ============================================================
# SEARCH PAGINATION
# ============================================================
def go_next_search_page(driver):
    selectors = [
        "a[rel='next']",
        "a[aria-label*='Nächste']",
        "button[aria-label*='Nächste']",
        "a[aria-label*='Next']",
        "button[aria-label*='Next']",
        "[data-testid*='next']",
    ]
    old_url = driver.current_url
    for selector in selectors:
        try:
            for element in visible_enabled(driver.find_elements(By.CSS_SELECTOR, selector)):
                if element.get_attribute("aria-disabled") == "true":
                    continue
                if safe_click(driver, element):
                    time.sleep(3)
                    if driver.current_url != old_url or get_job_cards(driver):
                        return True
        except Exception:
            continue
    return False

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 72)
    print("STEPSTONE + THIRD-PARTY ATS APPLICATION AUTOMATION")
    print("=" * 72)

    if not os.path.isfile(CV_PATH):
        print("ERROR: CV NOT FOUND:", CV_PATH)
        return

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(options=options)

    try:
        # Manual login only. Do not automate credentials/CAPTCHA.
        driver.get("https://www.stepstone.de/")
        wait_page(driver)
        print("\nPlease log into StepStone manually, including CAPTCHA/security checks if shown.")
        input("Press ENTER after login is complete...")

        driver.get(SEARCH_URL)
        wait_page(driver)
        time.sleep(4)
        results_handle = driver.current_window_handle

        for page_number in range(1, MAX_SEARCH_PAGES + 1):
            switch_back(driver, results_handle)
            print("\n" + "=" * 72)
            print("SEARCH PAGE", page_number)
            print("=" * 72)

            cards = get_job_cards(driver)
            print("FOUND JOB CARDS:", len(cards))
            if not cards:
                break

            for index in range(len(cards)):
                switch_back(driver, results_handle)
                current_cards = get_job_cards(driver)
                if index >= len(current_cards):
                    break
                card = current_cards[index]
                try:
                    title, _ = get_job_info(card)
                except Exception:
                    title = ""
                print(f"\nJOB {index + 1}/{len(current_cards)}: {title}")
                try:
                    process_job(driver, card, results_handle)
                except Exception as exc:
                    print("JOB ERROR:", exc)
                    log_result(title, driver.current_url, [], "Job processing error: " + str(exc))
                    close_current_application_tab(driver, results_handle)
                time.sleep(1)

            switch_back(driver, results_handle)
            print("SEARCH PAGE COMPLETE.")
            if not go_next_search_page(driver):
                print("NO MORE SEARCH PAGES.")
                break
            time.sleep(3)

    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as exc:
        print("MAIN ERROR:", exc)
    finally:
        print("Browser left open. Close it manually when finished.")
        # Intentionally do not driver.quit(): manual-completion tabs must remain available.


if __name__ == "__main__":
    main()
