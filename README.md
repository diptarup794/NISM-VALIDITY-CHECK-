# NISM WebAutomation

Automate login, certificate validation, and data extraction from the NISM certification portal using Playwright, Azure OpenAI, and DeathByCaptcha.

## Features
- Automated login and navigation to NISM certification portal
- Captcha solving using:
  - DeathByCaptcha (DBC, paid, recommended for reliability)
  - EasyOCR (open source, fallback)
  - LLM-based (Azure OpenAI, for research/testing)
- PDF certificate field extraction using LLM
- Modern Flask web UI and REST API endpoints
- Detailed logging and error handling

## Setup

### 1. Clone the repository and install dependencies
```bash
pip install -r requirements.txt
playwright install
```

### 2. Place DeathByCaptcha client files
- Copy `deathbycaptcha.py` (and if needed, `deathbycaptcha_socket.py`) from the [official repo](https://github.com/DeathByCaptcha/deathbycaptcha-python) into your project root.
- **Do NOT install `deathbycaptcha` from PyPI.**

### 3. Environment Variables
Create a `.env` file in the project root with the following:
```
AZURE_OPENAI_API_KEY=your-azure-openai-key
AZURE_OPENAI_ENDPOINT=your-azure-endpoint
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_VERSION=2023-05-15
DBC_USERNAME=your-dbc-username
DBC_PASSWORD=your-dbc-password
```

## Usage

### CLI Automation
Run the main automation (headless by default):
```bash
python main.py --captcha_solver deathbycaptcha
```
- Use `--captcha_solver easyocr` to use OCR instead of DBC.
- Use `--pan`, `--first_name`, `--exam_name` to override defaults.

### Flask Web App
Start the web app:
```bash
python flask_app.py
```
- Visit [http://localhost:5000](http://localhost:5000) to use the UI.
- Upload a PDF to extract and validate certificate details.


## Captcha Solving Logic
- **DeathByCaptcha (default):** Most reliable, logs remaining credits after each use.
- **EasyOCR:** Open source fallback if DBC is not available.
- Logging will indicate which method is used and show DBC balance.

## Troubleshooting
- If you see import errors for `deathbycaptcha`, ensure you are using the local file, not the PyPI package.
- For DBC errors, check your credentials and account balance.
- For Playwright errors, ensure browsers are installed (`playwright install`).
- For Azure OpenAI errors, check your API key, endpoint, and deployment name.

## Credits
- [Playwright](https://playwright.dev/python/)
- [DeathByCaptcha](https://github.com/DeathByCaptcha/deathbycaptcha-python)
- [EasyOCR](https://github.com/JaidedAI/EasyOCR)
- [OpenAI Python SDK](https://github.com/openai/openai-python)

---
**Maintained by Diptarup.** 
