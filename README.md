# PDF Merge Utility v1.2

A free, offline Windows Python app for **merging** PDF/JPG/PNG/TXT files and **splitting** PDFs into individual PDF, JPG, or PNG files.

## Install and launch

Requires Python 3.10+ with Tkinter. Extract the ZIP, open PowerShell in the extracted folder, and run:

```powershell
py -m pip install -r requirements.txt
```

Then double-click `run_pdf_merge.bat` or run `python pdf_merge_utility.py`.

## Merge Files tab

Add multiple PDFs, JPGs, PNGs, or TXT files using **Add Files** or drag and drop. Arrange them with Move Up/Down, remove unwanted files, and select **Merge & Save** to choose the output PDF filename. Existing PDF pages are retained; images are fitted to US Letter pages with half-inch margins; text is wrapped onto letter-size pages.

## Split PDF tab (new in v1.2)

1. Choose a multipage source PDF using **Browse**, or drag it onto the Source PDF field.
2. Choose **Individual PDFs**, **JPG images**, or **PNG images**.
3. Enter `all` to extract every page, or page numbers/ranges such as `1-5, 8, 12-15`.
4. Choose an output folder and click **Split PDF**.

Output files are named like `Document_page_001.pdf`, `Document_page_002.jpg`, etc., retaining original page numbers. JPG and PNG files are rendered at **200 DPI**. JPG images use quality 90 and a white background. The individual PDF outputs keep PDF page content as PDF (not rasterized). Output files that already exist are **not overwritten**; choose a different folder or move/rename existing files.

### Notes

- All processing is offline. Original files are not modified.
- Password-protected PDFs are not supported.
- Split page ranges are 1-based and sorted in ascending order; repeated page numbers are extracted once.
- Very large PDFs and high-resolution pages can use significant memory and disk space.
- If processing fails, newly created split files are removed where possible.
- This version has passed automated checks, but the Windows GUI should be validated on your computer.
