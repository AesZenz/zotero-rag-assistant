import os
from dotenv import load_dotenv
from src.ingestion.pdf_parser import extract_text_from_pdf, extract_metadata

load_dotenv()
PDF_PATH = os.environ["TEST_PDF_PATH"]

text = extract_text_from_pdf(PDF_PATH)
print("=== First 500 characters ===")
print(text[:500])

print("\n=== Metadata ===")
metadata = extract_metadata(PDF_PATH)
for key, value in metadata.items():
    print(f"{key}: {value}")
