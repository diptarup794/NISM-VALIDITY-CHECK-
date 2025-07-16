import os
import json
import fitz  # PyMuPDF
import openai
from dotenv import load_dotenv
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
import subprocess
import tempfile
import deathbycaptcha
import logging
from deathbycaptcha import SocketClient

# Load Azure OpenAI credentials
load_dotenv()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
DBC_USERNAME = os.getenv("DBC_USERNAME")
DBC_PASSWORD = os.getenv("DBC_PASSWORD")

PDF_PROMPT = '''
You are an expert at extracting structured data from certificate documents. Given the following text extracted from a NISM certificate PDF, extract the following fields:
- PAN number (e.g., FVLPS5539H)
- First name (e.g., ANKIT)
- Exam name (e.g., NISM Series V-A: Mutual Fund Distributors Certification Examination)
Return the result as a JSON object with keys: pan, first_name, exam_name.

PDF TEXT:
{text}
'''

def extract_text_from_pdf(pdf_path):
    with fitz.open(pdf_path) as doc:
        text = "\n".join(page.get_text() for page in doc)
    return text

def extract_fields_with_llm(text):
    if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT or not AZURE_OPENAI_API_VERSION:
        raise RuntimeError("Missing Azure OpenAI configuration. Please set all required environment variables.")
    prompt = PDF_PROMPT.format(text=text)
    client = openai.AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
    )
    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        temperature=0.0,
    )
    content = response.choices[0].message.content
    try:
        data = json.loads(content)
    except Exception:
        return None
    return data

def solve_captcha_with_deathbycaptcha(image_path, username=None, password=None):
    username = username or DBC_USERNAME
    password = password or DBC_PASSWORD
    if not username or not password:
        raise ValueError("DeathByCaptcha credentials not provided. Set DBC_USERNAME and DBC_PASSWORD as env vars or pass as arguments.")
    try:
        logging.info("[INFO] Using DeathByCaptcha (SocketClient) for captcha solving.")
        client = SocketClient(username, password)
        balance = client.get_balance()
        logging.info(f"[INFO] DBC Remaining Credits: {balance} US cents")
        with open(image_path, 'rb') as f:
            captcha = client.decode(f)
        if captcha and 'text' in captcha:
            logging.info(f"[INFO] DBC Captcha solution: {captcha['text']}")
            return captcha['text']
        else:
            logging.error(f"[ERROR] Failed to solve captcha with DBC. Response: {captcha}")
            return None
    except Exception as e:
        logging.error(f"[ERROR] Exception in DBC: {e}", exc_info=True)
        return None

def call_main_py_with_dbc(pan, first_name, exam_name):
    cmd = [
        "python", "main.py",
        "--pan", pan,
        "--first_name", first_name,
        "--exam_name", exam_name,
        "--captcha_solver", "deathbycaptcha"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    import re
    match = re.search(r'\{[\s\S]*\}', result.stdout)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None

app = Flask(__name__)
app.secret_key = os.urandom(24)

TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NISM Certificate Extractor</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css"/>
    <style>
        body { background: linear-gradient(120deg, #f8fafc 0%, #e0e7ff 100%); }
        .card-custom { box-shadow: 0 4px 24px #0002; border-radius: 1.5rem; background: linear-gradient(120deg, #fff 60%, #f0f4ff 100%); animation: fadeIn 1s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(30px);} to { opacity: 1; transform: none; } }
        .spinner-overlay, .spinner-validation {
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(255,255,255,0.7);
            z-index: 9999;
            display: flex; align-items: center; justify-content: center;
        }
        .spinner-validation { background: rgba(0,0,0,0.2); }
        .result-icon {
            font-size: 3rem;
            margin-bottom: 0.5rem;
            transition: transform 0.3s;
        }
        .result-status-valid { color: #22c55e; animation: bounce 1s; }
        .result-status-expired { color: #ef4444; animation: shake 1s; }
        @keyframes bounce { 0%,100%{transform:translateY(0);} 50%{transform:translateY(-10px);} }
        @keyframes shake { 0%,100%{transform:translateX(0);} 25%{transform:translateX(-5px);} 75%{transform:translateX(5px);} }
        .gradient-bar { height: 6px; border-radius: 6px; background: linear-gradient(90deg, #6366f1, #22d3ee, #22c55e); margin-bottom: 1.5rem; }
    </style>
    <script>
        function showExtractionSpinner() {
            document.getElementById('spinner-overlay').style.display = 'flex';
        }
        function hideExtractionSpinner() {
            document.getElementById('spinner-overlay').style.display = 'none';
        }
        function showValidationSpinner() {
            document.getElementById('spinner-validation').style.display = 'flex';
        }
        function hideValidationSpinner() {
            document.getElementById('spinner-validation').style.display = 'none';
        }
        window.onload = function() { hideExtractionSpinner(); hideValidationSpinner(); };
    </script>
</head>
<body>
<div id="spinner-overlay" class="spinner-overlay" style="display:none;">
    <div class="d-flex flex-column align-items-center">
      <i class="fa-solid fa-file-pdf fa-3x text-primary mb-3 animate__animated animate__pulse animate__infinite"></i>
      <div class="spinner-border text-primary" style="width: 4rem; height: 4rem;" role="status"></div>
      <div class="mt-3 fw-semibold text-primary">Extracting information from PDF...</div>
    </div>
</div>
<div id="spinner-validation" class="spinner-validation" style="display:none;">
    <div class="d-flex flex-column align-items-center">
      <i class="fa-solid fa-magnifying-glass-chart fa-3x text-info mb-3 animate__animated animate__pulse animate__infinite"></i>
      <div class="spinner-border text-info" style="width: 4rem; height: 4rem;" role="status"></div>
      <div class="mt-3 fw-semibold text-info">Validating certificate...</div>
    </div>
</div>
<div class="container py-5">
    <div class="row justify-content-center">
        <div class="col-lg-7 col-md-9 col-12">
            <div class="text-center mb-4">
                <h1 class="display-5 fw-bold">NISM Certificate Extractor</h1>
                <div class="gradient-bar mx-auto" style="width: 120px;"></div>
                <p class="lead">Upload your NISM certificate PDF to extract and validate your certification.</p>
            </div>
            <form method="POST" enctype="multipart/form-data" class="bg-white p-4 rounded shadow-sm mb-4" onsubmit="showExtractionSpinner()">
                <div class="mb-3">
                    <label for="pdf" class="form-label">Upload PDF</label>
                    <input class="form-control" type="file" id="pdf" name="pdf" accept="application/pdf" required>
                </div>
                {% if pan_needed %}
                <div class="mb-3">
                    <label for="pan" class="form-label">PAN number could not be extracted or is redacted. Please enter PAN number manually:</label>
                    <input class="form-control" type="text" id="pan" name="pan" required>
                </div>
                {% endif %}
                <button type="submit" class="btn btn-primary w-100 py-2">Extract & Validate</button>
            </form>
            {% if result %}
            <div class="card card-custom p-4 mt-4 animate__animated animate__fadeIn">
                <div class="card-body text-center">
                    {% if result.status == 'valid' %}
                        <div class="result-icon result-status-valid">✅</div>
                    {% elif result.status == 'expired' %}
                        <div class="result-icon result-status-expired">⏰</div>
                    {% else %}
                        <div class="result-icon">❓</div>
                    {% endif %}
                    <h5 class="card-title mb-3 text-primary fw-bold">Validation Result</h5>
                    <div class="mb-2"><span class="fw-semibold">Status:</span> <span class="{% if result.status == 'valid' %}text-success{% elif result.status == 'expired' %}text-danger{% endif %}">{{ result.status or '-' }}</span></div>
                    <div class="mb-2"><span class="fw-semibold">Exam Name:</span> {{ result.exam_name or '-' }}</div>
                    <div class="mb-2"><span class="fw-semibold">Exam Date:</span> {{ result.exam_date or '-' }}</div>
                    <div class="mb-2"><span class="fw-semibold">Certificate Valid Upto:</span> {{ result.certificate_valid_upto or '-' }}</div>
                    <div class="mb-2"><span class="fw-semibold">Enrolment No.:</span> {{ result.enrolment_no or '-' }}</div>
                </div>
            </div>
            <script>hideExtractionSpinner(); hideValidationSpinner();</script>
            {% endif %}
            {% with messages = get_flashed_messages() %}
              {% if messages %}
                <div class="alert alert-warning mt-3 animate__animated animate__fadeIn">{{ messages[0] }}</div>
              {% endif %}
            {% endwith %}
        </div>
    </div>
</div>
<script>
    // Show validation spinner after extraction
    {% if result %}
    setTimeout(function(){ showValidationSpinner(); }, 200);
    setTimeout(function(){ hideValidationSpinner(); }, 1200);
    {% endif %}
</script>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    pan_needed = False
    if request.method == 'POST':
        pdf_file = request.files.get('pdf')
        pan = request.form.get('pan', '').strip()
        if pdf_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                pdf_path = tmp.name
                pdf_file.save(pdf_path)
            text = extract_text_from_pdf(pdf_path)
            fields = extract_fields_with_llm(text)
            if fields:
                # Check if PAN is missing or redacted
                pan_extracted = fields.get('pan', '')
                if (not pan_extracted or 'x' in pan_extracted.lower()) and not pan:
                    pan_needed = True
                    os.unlink(pdf_path)
                    return render_template_string(TEMPLATE, result=None, pan_needed=pan_needed)
                if not pan:
                    pan = pan_extracted
                first_name = fields.get('first_name', '')
                exam_name = fields.get('exam_name', '')
                result = call_main_py_with_dbc(pan, first_name, exam_name)
                os.unlink(pdf_path)
            else:
                flash('Could not extract fields from PDF. Please try another file.')
                os.unlink(pdf_path)
    return render_template_string(TEMPLATE, result=result, pan_needed=pan_needed)

@app.route('/api/extract-fields', methods=['POST'])
def api_extract_fields():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No PDF uploaded'}), 400
    pdf_file = request.files['pdf']
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_path = tmp.name
        pdf_file.save(pdf_path)
    text = extract_text_from_pdf(pdf_path)
    fields = extract_fields_with_llm(text)
    os.unlink(pdf_path)
    if not fields:
        return jsonify({'error': 'Could not extract fields from PDF'}), 400
    return jsonify(fields)

@app.route('/api/validate-certificate', methods=['POST'])
def api_validate_certificate():
    data = request.json
    pan = data.get('pan', '') if data else ''
    first_name = data.get('first_name', '') if data else ''
    exam_name = data.get('exam_name', '') if data else ''
    if not pan or not first_name or not exam_name:
        return jsonify({'error': 'Missing required fields'}), 400
    result = call_main_py_with_dbc(pan, first_name, exam_name)
    if not result:
        return jsonify({'error': 'Validation failed'}), 400
    return jsonify(result)

@app.route('/api/extract-and-validate', methods=['POST'])
def api_extract_and_validate():
    pdf_file = request.files.get('pdf')
    pan = request.form.get('pan', '').strip()
    if not pdf_file:
        return jsonify({'error': 'No PDF uploaded'}), 400
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_path = tmp.name
        pdf_file.save(pdf_path)
    text = extract_text_from_pdf(pdf_path)
    fields = extract_fields_with_llm(text)
    os.unlink(pdf_path)
    if not fields:
        return jsonify({'error': 'Could not extract fields from PDF'}), 400
    pan_extracted = fields.get('pan', '')
    if (not pan_extracted or 'x' in pan_extracted.lower()) and not pan:
        return jsonify({'error': 'PAN number required', 'fields': fields}), 400
    if not pan:
        pan = pan_extracted
    first_name = fields.get('first_name', '')
    exam_name = fields.get('exam_name', '')
    result = call_main_py_with_dbc(pan, first_name, exam_name)
    if not result:
        return jsonify({'error': 'Validation failed'}), 400
    return jsonify(result)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True) 