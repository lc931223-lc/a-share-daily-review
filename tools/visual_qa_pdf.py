import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader


def embedded_font_names(reader: PdfReader) -> set[str]:
    names: set[str] = set()
    for page in reader.pages:
        fonts = page.get("/Resources", {}).get("/Font", {})
        for font in fonts.values():
            base_font = font.get_object().get("/BaseFont")
            if base_font:
                names.add(str(base_font))
    return names


def main(argv: list[str] | None = None) -> int:
    if not argv:
        print("usage: python tools/visual_qa_pdf.py <report.pdf>")
        return 1
    pdf_path = Path(argv[0]).resolve()
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 1

    reader = PdfReader(pdf_path)
    if not reader.pages:
        print("PDF has no pages")
        return 1
    fonts = embedded_font_names(reader)
    if not any("SourceHanSans" in name for name in fonts):
        print(f"Source Han Sans font not found: {sorted(fonts)}")
        return 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if "数据质量" not in text:
        print("数据质量 section not found")
        return 1

    output_dir = Path("tmp") / "pdf-qa" / pdf_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = output_dir / pdf_path.stem
    completed = subprocess.run(
        ["pdftoppm", "-png", str(pdf_path), str(output_prefix)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout)
        return completed.returncode
    print(f"PDF QA passed: pages={len(reader.pages)} fonts={sorted(fonts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
