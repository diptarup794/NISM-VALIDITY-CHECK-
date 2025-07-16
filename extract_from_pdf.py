import sys
import os
import fitz  # PyMuPDF
import openai
from dotenv import load_dotenv
import subprocess
import json

# Load Azure OpenAI credentials
load_dotenv()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

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
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    return text

def extract_fields_with_llm(text):
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
        print("Failed to parse LLM output as JSON. Output was:\n", content)
        raise
    return data

def main():
    # Set the PDF path directly here
    pdf_path = r"c:\Users\Diptarup\Downloads\_ NISM V A 20250106194711800.pdf"
    text = extract_text_from_pdf(pdf_path)
    fields = extract_fields_with_llm(text)
    print("Extracted fields:", fields)
    # Call main.py with extracted info as arguments
    cmd = [
        sys.executable, "main.py",
        "--pan", fields["pan"],
        "--first_name", fields["first_name"],
        "--exam_name", fields["exam_name"]
    ]
    subprocess.run(cmd)

if __name__ == "__main__":
    main() 