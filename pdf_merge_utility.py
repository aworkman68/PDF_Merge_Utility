"""PDF Merge Utility v1.2 — combine PDF, JPEG, PNG, and TXT files."""
from __future__ import annotations

import os
import tempfile
from io import BytesIO
from xml.sax.saxutils import escape
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pypdf import PdfReader, PdfWriter
import fitz  # PyMuPDF: render PDF pages to JPG or PNG
from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from tkinterdnd2 import DND_FILES, TkinterDnD


SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".txt"}


def image_to_pdf(path: Path) -> BytesIO:
    """Place a single image on one letter-size page, preserving proportions."""
    buffer = BytesIO()
    with Image.open(path) as original:
        # EXIF orientation is respected, and transparency is composited onto white.
        image = ImageOps.exif_transpose(original)
        image.load()
        if image.mode == "RGBA" or "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        page_width, page_height = letter
        margin = 36  # Half-inch margins
        max_width = page_width - 2 * margin
        max_height = page_height - 2 * margin
        scale = min(max_width / image.width, max_height / image.height)
        width, height = image.width * scale, image.height * scale
        pdf = canvas.Canvas(buffer, pagesize=letter)
        pdf.drawImage(ImageReader(image), (page_width - width) / 2,
                      (page_height - height) / 2, width, height)
        pdf.showPage()
        pdf.save()
    buffer.seek(0)
    return buffer


def _text_font() -> str:
    """Use a Unicode-capable font when available, otherwise Helvetica."""
    name = "MergeUnicode"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            return name
    return "Helvetica"


def text_to_pdf(path: Path) -> BytesIO:
    """Render UTF-8 (or Windows-1252) plain text onto letter-size pages."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    page_width, page_height = letter
    margin = 54
    font = _text_font()
    font_size = 10
    leading = 15
    y = page_height - margin
    pdf.setFont(font, font_size)
    available_width = page_width - 2 * margin

    def wrap_line(line: str):
        # Break long lines by measured rendered width without dropping whitespace.
        if not line:
            return [""]
        pieces = []
        current = ""
        for char in line:
            if current and pdfmetrics.stringWidth(current + char, font, font_size) > available_width:
                pieces.append(current)
                current = ""
            current += char
        if current or not pieces:
            pieces.append(current)
        return pieces

    for line in text.expandtabs(4).splitlines():
        for segment in wrap_line(line):
            if y < margin + leading:
                pdf.showPage()
                pdf.setFont(font, font_size)
                y = page_height - margin
            # PDF standard fonts cannot represent all Unicode characters.
            if font == "Helvetica":
                segment = segment.encode("cp1252", errors="replace").decode("cp1252")
            pdf.drawString(margin, y, segment)
            y -= leading
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer



def parse_page_selection(selection: str, page_count: int) -> list[int]:
    """Parse 1-based page ranges, returning sorted unique 0-based indices."""
    if page_count < 1:
        raise ValueError("The PDF has no pages.")
    if selection.strip().lower() == "all":
        return list(range(page_count))
    if not selection.strip():
        raise ValueError("Enter 'all' or a page selection such as 1-5, 8.")
    result = set()
    for token in selection.split(","):
        token = token.strip()
        if not token:
            raise ValueError("Empty page number in selection.")
        parts = token.split("-")
        if len(parts) not in (1, 2) or any(not p.strip().isdigit() for p in parts):
            raise ValueError(f"Invalid page selection: {token!r}")
        first = int(parts[0])
        last = int(parts[-1])
        if first < 1 or last > page_count or last < first:
            raise ValueError(f"Page range {token!r} must be within 1-{page_count} and in ascending order.")
        result.update(range(first - 1, last))
    return sorted(result)

class PDFMergeApp:
    def __init__(self, root: TkinterDnD.Tk) -> None:
        self.root = root
        self.root.title("PDF Merge Utility v1.2")
        self.root.geometry("800x550")
        self.root.minsize(590, 390)
        self.paths: list[Path] = []
        self.status = tk.StringVar(value="Add PDFs, JPGs, PNGs, or TXT files using the button or drag and drop.")
        self._build_ui()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)
        outer = ttk.Frame(notebook, padding=16)
        notebook.add(outer, text="Merge Files")
        split_tab = ttk.Frame(notebook, padding=16)
        notebook.add(split_tab, text="Split PDF")
        self._build_split_ui(split_tab)
        ttk.Label(outer, text="Merge Files", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Combine PDF, JPG, PNG, and TXT files in the order shown. Drag files here or use Add Files.").pack(anchor="w", pady=(3, 12))

        center = ttk.Frame(outer)
        center.pack(fill="both", expand=True)
        list_frame = ttk.Frame(center)
        list_frame.pack(side="left", fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, activestyle="none", font=("Segoe UI", 10))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind("<<Drop>>", self._drop)

        actions = ttk.Frame(center, padding=(12, 0, 0, 0))
        actions.pack(side="right", fill="y")
        for text, command in (
            ("Add Files...", self.add_files),
            ("Move Up", lambda: self.move(-1)),
            ("Move Down", lambda: self.move(1)),
            ("Remove Selected", self.remove_selected),
            ("Clear All", self.clear),
        ):
            ttk.Button(actions, text=text, command=command, width=18).pack(fill="x", pady=(0, 8))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(footer, textvariable=self.status).pack(side="left", fill="x", expand=True)
        self.merge_button = ttk.Button(footer, text="Merge & Save...", command=self.merge)
        self.merge_button.pack(side="right")


    def _build_split_ui(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Split PDF", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(parent, text="Extract selected pages as individual PDFs, JPGs, or PNGs (images at 200 DPI).").pack(anchor="w", pady=(4, 18))
        self.split_source = tk.StringVar()
        self.split_output = tk.StringVar()
        self.split_format = tk.StringVar(value="pdf")
        self.split_pages = tk.StringVar(value="all")
        self.split_status = tk.StringVar(value="Choose a source PDF to begin.")
        self.split_info = tk.StringVar(value="")

        ttk.Label(parent, text="Source PDF").pack(anchor="w")
        source_row = ttk.Frame(parent)
        source_row.pack(fill="x", pady=(3, 8))
        source_entry = ttk.Entry(source_row, textvariable=self.split_source, state="readonly")
        source_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(source_row, text="Browse...", command=self._browse_split_source).pack(side="left", padx=(8, 0))
        source_entry.drop_target_register(DND_FILES)
        source_entry.dnd_bind("<<Drop>>", self._drop_split_source)
        ttk.Label(parent, textvariable=self.split_info).pack(anchor="w", pady=(0, 12))

        ttk.Label(parent, text="Output format").pack(anchor="w")
        format_row = ttk.Frame(parent)
        format_row.pack(anchor="w", pady=(4, 14))
        for label, value in (("Individual PDFs", "pdf"), ("JPG images", "jpg"), ("PNG images", "png")):
            ttk.Radiobutton(format_row, text=label, value=value, variable=self.split_format).pack(side="left", padx=(0, 20))

        ttk.Label(parent, text="Pages to extract (all, or e.g. 1-5, 8, 12-15)").pack(anchor="w")
        ttk.Entry(parent, textvariable=self.split_pages, width=35).pack(anchor="w", pady=(4, 14))

        ttk.Label(parent, text="Output folder").pack(anchor="w")
        output_row = ttk.Frame(parent)
        output_row.pack(fill="x", pady=(4, 14))
        ttk.Entry(output_row, textvariable=self.split_output, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(output_row, text="Browse...", command=self._browse_split_output).pack(side="left", padx=(8, 0))

        ttk.Label(parent, text="Files are named source_page_001.pdf (or .jpg / .png) using original page numbers.", wraplength=690).pack(anchor="w", pady=(0, 16))
        footer = ttk.Frame(parent)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.split_status, wraplength=540).pack(side="left", fill="x", expand=True)
        self.split_button = ttk.Button(footer, text="Split PDF", command=self.split_pdf)
        self.split_button.pack(side="right")

    def _browse_split_source(self) -> None:
        filename = filedialog.askopenfilename(title="Choose PDF to split", filetypes=[("PDF files", "*.pdf")])
        if filename:
            self._set_split_source(filename)

    def _drop_split_source(self, event) -> None:
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self._set_split_source(paths[0])

    def _set_split_source(self, filename: str) -> None:
        path = Path(filename).expanduser()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            messagebox.showwarning("Invalid source", "Please select a PDF file.")
            return
        try:
            with fitz.open(str(path)) as doc:
                if doc.needs_pass:
                    raise ValueError("Password-protected PDFs are not supported.")
                count = len(doc)
            if count < 1:
                raise ValueError("The PDF has no pages.")
        except Exception as exc:
            messagebox.showerror("Cannot open PDF", str(exc))
            return
        self.split_source.set(str(path.resolve()))
        self.split_info.set(f"{count} page(s) in source PDF")
        self.split_status.set("Ready to split.")
        if not self.split_output.get():
            self.split_output.set(str(path.parent))

    def _browse_split_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.split_output.set(folder)

    def split_pdf(self) -> None:
        source_text, folder_text = self.split_source.get(), self.split_output.get()
        if not source_text or not folder_text:
            messagebox.showwarning("Missing selection", "Choose a source PDF and an output folder.")
            return
        source, folder = Path(source_text), Path(folder_text)
        if not source.is_file() or not folder.is_dir():
            messagebox.showerror("Invalid path", "The source PDF or output folder does not exist.")
            return
        kind = self.split_format.get()
        self.split_button.state(["disabled"])
        try:
            with fitz.open(str(source)) as doc:
                if doc.needs_pass:
                    raise ValueError("Password-protected PDFs are not supported.")
                indices = parse_page_selection(self.split_pages.get(), len(doc))
                width = max(3, len(str(len(doc))))
                destinations = [folder / f"{source.stem}_page_{i+1:0{width}d}.{kind}" for i in indices]
                # Never silently overwrite an existing file, including the source.
                collisions = [p for p in destinations if p.exists()]
                if collisions:
                    raise FileExistsError(f"{len(collisions)} output file(s) already exist. Move, rename, or remove them before splitting.\nFirst conflict: {collisions[0].name}")
                self.split_status.set(f"Extracting {len(indices)} page(s)...")
                self.root.update_idletasks()
                written = []
                try:
                    for idx, target in zip(indices, destinations):
                        # Create atomically to avoid overwriting files created concurrently.
                        with target.open("xb") as output:
                            written.append(target)
                            if kind == "pdf":
                                single = fitz.open()
                                try:
                                    single.insert_pdf(doc, from_page=idx, to_page=idx, links=True, annots=True)
                                    output.write(single.tobytes(garbage=3, deflate=True))
                                finally:
                                    single.close()
                            else:
                                pix = doc[idx].get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False)
                                output.write(pix.tobytes("jpeg" if kind == "jpg" else "png", jpg_quality=90))
                except Exception:
                    # Remove outputs created in this operation if processing fails.
                    for created in written:
                        try:
                            created.unlink(missing_ok=True)
                        except OSError:
                            pass
                    raise
            self.split_status.set(f"Extracted {len(indices)} page(s) as {kind.upper()} files.")
            messagebox.showinfo("Split complete", f"Created {len(indices)} {kind.upper()} file(s).\n\nSaved to:\n{folder}")
        except Exception as exc:
            self.split_status.set("Split failed. Source PDF was not changed.")
            messagebox.showerror("Could not split PDF", str(exc))
        finally:
            self.split_button.state(["!disabled"])

    def _refresh(self, selected: list[int] | None = None) -> None:
        self.listbox.delete(0, tk.END)
        for i, path in enumerate(self.paths, start=1):
            self.listbox.insert(tk.END, f"{i:02d}. {path.name}    —    {path.parent}")
        for i in selected or []:
            if 0 <= i < len(self.paths):
                self.listbox.selection_set(i)
        self.status.set(f"{len(self.paths)} file(s) selected")

    def _append(self, candidates: list[str]) -> None:
        existing = {os.path.normcase(str(p.resolve())) for p in self.paths}
        added = 0
        ignored = 0
        for name in candidates:
            path = Path(name).expanduser()
            if not path.is_file() or path.suffix.lower() not in SUPPORTED:
                ignored += 1
                continue
            canonical = os.path.normcase(str(path.resolve()))
            if canonical in existing:
                ignored += 1
                continue
            self.paths.append(path.resolve())
            existing.add(canonical)
            added += 1
        self._refresh()
        self.status.set(f"Added {added} file(s)" + (f"; ignored {ignored} duplicate/unsupported item(s)." if ignored else "."))

    def add_files(self) -> None:
        filenames = filedialog.askopenfilenames(title="Choose files to combine", filetypes=[("Supported files", "*.pdf *.jpg *.jpeg *.png *.txt"), ("PDF files", "*.pdf"), ("Images", "*.jpg *.jpeg *.png"), ("Text files", "*.txt"), ("All files", "*.*")])
        if filenames:
            self._append(list(filenames))

    def _drop(self, event) -> None:
        # Tk parses Windows drag paths correctly, including spaces and braces.
        self._append(list(self.root.tk.splitlist(event.data)))

    def move(self, direction: int) -> None:
        indices = list(self.listbox.curselection())
        if not indices:
            return
        chosen = set(indices)
        if direction < 0:
            for i in indices:
                if i > 0 and i - 1 not in chosen:
                    self.paths[i - 1], self.paths[i] = self.paths[i], self.paths[i - 1]
                    chosen.remove(i)
                    chosen.add(i - 1)
        else:
            for i in reversed(indices):
                if i < len(self.paths) - 1 and i + 1 not in chosen:
                    self.paths[i + 1], self.paths[i] = self.paths[i], self.paths[i + 1]
                    chosen.remove(i)
                    chosen.add(i + 1)
        self._refresh(sorted(chosen))

    def remove_selected(self) -> None:
        for i in reversed(self.listbox.curselection()):
            del self.paths[i]
        self._refresh()

    def clear(self) -> None:
        self.paths.clear()
        self._refresh()

    def merge(self) -> None:
        if len(self.paths) < 1:
            messagebox.showwarning("Select files", "Please add at least one supported file.")
            return
        destination = filedialog.asksaveasfilename(
            title="Save merged PDF as", defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")], initialfile="merged.pdf",
        )
        if not destination:
            return
        output = Path(destination).resolve()
        if any(os.path.normcase(str(output)) == os.path.normcase(str(p)) for p in self.paths):
            messagebox.showerror("Choose another filename", "The output cannot overwrite an input file.")
            return
        self.merge_button.state(["disabled"])
        self.status.set("Combining files...")
        self.root.update_idletasks()
        temp_path = None
        writer = PdfWriter()
        try:
            # Write to a temporary file in the destination directory so failures do not
            # leave a partially written PDF or replace an existing output file.
            for path in self.paths:
                try:
                    if path.suffix.lower() == ".pdf":
                        reader = PdfReader(str(path))
                        if reader.is_encrypted:
                            raise ValueError("Password-protected PDFs are not supported")
                        writer.append(reader)
                    else:
                        converted = (text_to_pdf(path) if path.suffix.lower() == ".txt"
                                     else image_to_pdf(path))
                        # Append while the converted PDF's in-memory stream is alive.
                        writer.append(PdfReader(converted))
                except Exception as exc:
                    raise ValueError(f"Could not process '{path.name}': {exc}") from exc
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", prefix=".pdf_merge_", dir=output.parent, delete=False) as temp:
                temp_path = Path(temp.name)
                writer.write(temp)
            os.replace(temp_path, output)
            temp_path = None
            self.status.set(f"Saved {len(writer.pages)} pages to {output.name}")
            messagebox.showinfo("Merge complete", f"Combined {len(self.paths)} files ({len(writer.pages)} pages).\n\nSaved to:\n{output}")
        except Exception as exc:
            self.status.set("Merge failed. No input files were changed.")
            messagebox.showerror("Could not merge PDFs", str(exc))
        finally:
            writer.close()
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            self.merge_button.state(["!disabled"])


def main() -> None:
    root = TkinterDnD.Tk()
    PDFMergeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
