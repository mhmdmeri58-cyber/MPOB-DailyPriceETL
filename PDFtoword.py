"""PDF to Word converter.

Install once:   pip install pdf2docx
Use:            python pdf_to_word.py file.pdf
                python pdf_to_word.py a.pdf b.pdf
                python pdf_to_word.py            (opens a file picker)
"""

import sys
from pathlib import Path

try:
    from pdf2docx import Converter
except ImportError:
    sys.exit("Missing library. Run: pip install pdf2docx")


def convert(pdf_path: Path) -> Path:
    out = pdf_path.with_suffix(".docx")
    cv = Converter(str(pdf_path))
    try:
        cv.convert(str(out))
    finally:
        cv.close()
    return out


def pick_files():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    files = filedialog.askopenfilenames(
        title="Choose PDF files", filetypes=[("PDF files", "*.pdf")]
    )
    return [Path(f) for f in files]


def main():
    files = [Path(a) for a in sys.argv[1:]] or pick_files()
    if not files:
        sys.exit("No file chosen.")
    for f in files:
        if f.suffix.lower() != ".pdf" or not f.exists():
            print(f"Skipped (not a PDF or not found): {f}")
            continue
        print(f"Converting {f.name} ...")
        print(f"Saved {convert(f)}")


if __name__ == "__main__":
    main()