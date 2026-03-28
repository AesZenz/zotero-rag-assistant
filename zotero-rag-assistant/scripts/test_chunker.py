import os
from dotenv import load_dotenv
from src.ingestion.pdf_parser import extract_text_from_pdf, extract_metadata
from src.ingestion.chunker import chunk_document

load_dotenv()
PDF_PATH = os.environ["TEST_PDF_PATH"]

text = extract_text_from_pdf(PDF_PATH)
metadata = extract_metadata(PDF_PATH)

chunks = chunk_document(text, metadata)

print(f"=== Chunks created: {len(chunks)} ===\n")

print("--- First chunk ---")
print(f"token_count : {chunks[0]['token_count']}")
print(f"chars       : [{chunks[0]['start_char']}, {chunks[0]['end_char']})")
print(f"text preview: {chunks[0]['text'][:200]!r}")

print("\n--- Last chunk ---")
print(f"token_count : {chunks[-1]['token_count']}")
print(f"chars       : [{chunks[-1]['start_char']}, {chunks[-1]['end_char']})")
print(f"text preview: {chunks[-1]['text'][:200]!r}")

print("\n=== Token count distribution ===")
token_counts = [c["token_count"] for c in chunks]
print(f"min   : {min(token_counts)}")
print(f"max   : {max(token_counts)}")
print(f"mean  : {sum(token_counts) / len(token_counts):.1f}")
print(f"total : {sum(token_counts)}")
