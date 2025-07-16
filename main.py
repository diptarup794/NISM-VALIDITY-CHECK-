import asyncio
from playwright.async_api import async_playwright
import easyocr
from urllib.parse import urljoin
import openai
import os
from dotenv import load_dotenv
import argparse
import datetime
import json
from deathbycaptcha import SocketClient
import logging

LOGIN_URL = "https://certifications.nism.ac.in/nismskills/login.htm"
USERNAME = "vinay.khosla.2008@gmail.com"
PASSWORD = "HAUoGifZlol3l5"
PAN = "FVLPS5539H"
CANDIDATE_NAME = "ANKIT"
MAX_CAPTCHA_RETRIES = 3

# Load Azure OpenAI credentials
load_dotenv()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

async def extract_exam_details_with_llm(html, exam_name):
    if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT or not AZURE_OPENAI_API_VERSION:
        raise RuntimeError("Missing Azure OpenAI configuration. Please set all required environment variables.")
    prompt = f"""
You are an expert at extracting tabular data from HTML. Given the following HTML of a certification results page, search for the exam with the name most similar to: '{exam_name}'.

- If the exam is found under the 'Active Certifications' section, return status: "active".
- If the exam is found under the 'Expired Certifications' section, return status: "expired".
- If the exam is not found at all, return status: "invalid" and leave other fields empty or null.

Return the following fields as JSON:
- status ("active", "expired", or "invalid")
- exam_name
- exam_date
- certificate_valid_upto
- enrolment_no

HTML:
{html}
"""
    client = openai.AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
    )
    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.0,
    )
    return response.choices[0].message.content

def check_certificate_validity(certificate_valid_upto):
    try:
        cert_date = datetime.datetime.strptime(certificate_valid_upto, "%d-%b-%Y")
        today = datetime.datetime.now()
        return "expired" if cert_date < today else "valid"
    except Exception:
        return "unknown"

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pan', type=str, default=None)
    parser.add_argument('--first_name', type=str, default=None)
    parser.add_argument('--exam_name', type=str, default=None)
    parser.add_argument('--captcha_solver', type=str, choices=['easyocr', 'deathbycaptcha'], default='easyocr')
    return parser.parse_args()

def solve_captcha_with_deathbycaptcha(image_path, username=None, password=None):
    username = username or os.getenv('DBC_USERNAME')
    password = password or os.getenv('DBC_PASSWORD')
    if not username or not password:
        raise ValueError("DeathByCaptcha credentials not provided. Set DBC_USERNAME and DBC_PASSWORD as env vars or pass as arguments.")
    try:
        logging.info("[INFO] Using DeathByCaptcha (SocketClient) for captcha solving.")
        client = SocketClient(username, password)
        balance = client.get_balance()
        logging.info(f"[INFO] DBC Remaining Credits: {balance} US cents")
        with open(image_path, 'rb') as f:
            captcha = client.decode(f)
        if captcha and 'text' in captcha and captcha['text']:
            logging.info(f"[INFO] DBC Captcha solution: {captcha['text']}")
            return str(captcha['text'])
        else:
            logging.error(f"[ERROR] Failed to solve captcha with DBC. Response: {captcha}")
            return ""
    except Exception as e:
        logging.error(f"[ERROR] Exception in DBC: {e}", exc_info=True)
        return ""

async def run():
    args = get_args()
    pan = args.pan if args.pan else "FVLPS5539H"
    candidate_name = args.first_name if args.first_name else "ANKIT"
    exam_name = args.exam_name if args.exam_name else "NISM Series V-A: Mutual Fund Distributors Certification Examination."
    captcha_solver = getattr(args, 'captcha_solver', None)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            # Go to the login page
            await page.goto(LOGIN_URL)

            # Wait for the input fields to be visible
            await page.wait_for_selector('#Text1', timeout=15000)
            await page.wait_for_selector('#Password1', timeout=15000)

            # Fill in the username and password
            await page.fill('#Text1', USERNAME)
            await page.fill('#Password1', PASSWORD)

            # Click the submit button
            await page.click('#Submit1')

            # Wait for the "View Skills Registry" link to appear
            await page.wait_for_selector('a:has-text("View Skills Registry")', timeout=15000)
            await page.click('a:has-text("View Skills Registry")')

            # Wait for the PAN, Name, and Captcha fields to appear on the new page
            await page.wait_for_selector('#ctl00_cntplhldMainData_Pan_1', timeout=15000)
            await page.wait_for_selector('#ctl00_cntplhldMainData_FName_1', timeout=15000)
            await page.wait_for_selector('#ctl00_cntplhldMainData_Image1', timeout=15000)

            # Fill PAN and Name
            await page.fill('#ctl00_cntplhldMainData_Pan_1', pan)
            await page.fill('#ctl00_cntplhldMainData_FName_1', candidate_name)

            for attempt in range(1, MAX_CAPTCHA_RETRIES + 1):
                print(f"Attempt {attempt} to solve captcha...")
                captcha_img = await page.query_selector('#ctl00_cntplhldMainData_Image1')
                if not captcha_img:
                    raise Exception("Captcha image not found!")
                await captcha_img.screenshot(path='captcha.png')
                print("Captcha image saved as captcha.png")

                if captcha_solver == "deathbycaptcha":
                    logging.info("[INFO] Selected captcha solver: DeathByCaptcha (DBC)")
                    captcha_text = solve_captcha_with_deathbycaptcha('captcha.png')
                else:
                    logging.info("[INFO] Selected captcha solver: OCR (EasyOCR)")
                    print("[INFO] Using OCR (EasyOCR) for captcha solving.")
                    reader = easyocr.Reader(['en'])
                    result = reader.readtext('captcha.png', detail=0)
                    captcha_text = ''.join([str(r) for r in result])
                    captcha_text = ''.join(filter(str.isalnum, captcha_text))
                print(f"Captcha result: {captcha_text}")

                # Ensure captcha_text is a string
                captcha_text = captcha_text or ""
                await page.fill('#ctl00_cntplhldMainData_txtCaptcha', captcha_text)
                await page.click('#ctl00_cntplhldMainData_BtnSubmit')
                try:
                    await page.wait_for_selector('#ctl00_cntplhldMainData_CustomValidator6', timeout=3000)
                    error_visible = await page.is_visible('#ctl00_cntplhldMainData_CustomValidator6')
                    if error_visible:
                        print("Captcha failed, retrying...")
                        continue
                except Exception:
                    print("Captcha accepted or error not detected.")
                    break
            else:
                print("Failed to solve captcha after multiple attempts.")
                await page.screenshot(path="captcha_failed.png")
                return

            # Wait for the results page to load
            await page.wait_for_timeout(2000)
            await page.screenshot(path="results_page.png")
            print("Results page screenshot saved as results_page.png")
            html = await page.content()
            with open("results_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Results page HTML saved as results_page.html")

            print("Extracting exam details using Azure OpenAI...")
            details = await extract_exam_details_with_llm(html, exam_name)
            # Parse details as JSON if possible
            if not details:
                print("No details returned from LLM.")
                return
            try:
                details_json = json.loads(details)
            except Exception:
                print(details)
                return
            cert_valid_upto = details_json.get("certificate_valid_upto")
            if cert_valid_upto:
                status = check_certificate_validity(cert_valid_upto)
                details_json["status"] = status
            print("Final extracted details:")
            print(json.dumps(details_json, indent=2))
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"Error: {e}")
            await page.screenshot(path="error_screenshot.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run()) 