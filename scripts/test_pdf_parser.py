from src.config import settings
from src.ingestion.pdf_parser import extract_text_from_pdf, extract_metadata

PDF_PATH = settings.test_pdf_path

text = extract_text_from_pdf(PDF_PATH)
print("=== First 500 characters ===")
print(text[:500])

print("\n=== Metadata ===")
metadata = extract_metadata(PDF_PATH)
for key, value in metadata.items():
    print(f"{key}: {value}")
