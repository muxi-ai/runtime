"""PDF text extraction utility."""
import sys

def extract_text(pdf_path: str) -> str:
    return f"Extracted text from {pdf_path}"

if __name__ == "__main__":
    print(extract_text(sys.argv[1] if len(sys.argv) > 1 else "input.pdf"))
