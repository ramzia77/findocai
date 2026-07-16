# Sample documents

This directory holds small, synthetic financial documents used to exercise the
ingestion → chunking → embedding → RAG/extraction pipeline end to end. They
are **not real client data** — they are written from scratch, modeled on the
public conventions of loan agreements, invoices, and SEC financial-statement
excerpts (this environment has no internet access to fetch live public
filings, so realistic synthetic stand-ins are used instead).

Each sample intentionally includes a fake SSN/account number so the
`PIIRedactor` in `ingestion/cleaner.py` has something real to catch — do not
replace these with genuine personal data.

- `sample_loan_agreement.txt` — a short commercial loan agreement with
  numbered sections/covenants.
- `sample_invoice.txt` — a vendor invoice with line items.
- `sample_financial_statement.txt` — a 10-K-style excerpt (MD&A + balance
  sheet highlights).

`ingestion/loader.py` reads `.txt` files as a single page (no OCR needed) and
reads `.pdf` files via `pdfplumber` with an OCR fallback — drop real public
PDFs (e.g. SEC EDGAR filings) in here too if you want to exercise the PDF/OCR
path locally.
