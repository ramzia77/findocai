from __future__ import annotations # this future is aspeacial module and from is python keyword 
#lets the older version of ptyhon to use the newer version of python feautures that has been added in the newer version of python
#it is important to know what the loader produces , only then the later stages make sense 
# converts the pdf into python objects that the rag system can work on 
# only reads the document doesnt create any embeddings or chunks or anything else

# annotations allow the types , python tries to evaluate these types first and then evalauet them 

import argparse #argparse is a built in python library that allows us to create command line interfaces for your programs 
#argparse - when a python script is running it generates the arguments that are passed to the script and then parses them into a format that is easy to work with in the script, the type of it and also shows
# the --help output automatically showing the usage examples 
#withit argaprse everytime you wanted a different pdf you will have to edit the code 

import hashlib # for exmaple there are two files with the same name but different content , hashing creates a unique id for each file based on its content , so if the content changes the hash changes and if the content is same the hash is same
#this is useful becasue the RAG system can detect if the document has changed or not 

from datetime import datetime, timezone
# the time stamp is stored in the metadat of the document to know when the document is ingested into the system , this is useful for knowing when the document was last updated and also for knowing when the document was last used
from pathlib import Path
#path makes working with files a lot cleaner and easier , it is a built in python library that allows us to work with files and directories in a more object oriented way , it is a wrapper around the os module and makes working with files a lot easier
# so then file isnt just a tetx but it becomes apath object that knows everything about the file 


from pydantic import BaseModel
# pydantic helps define structured data 


from ingestion.metadata import DocType, DocumentMetadata
#DocType define the type of document that is being ingestedinto the system
# this is important because the RAG system can use this information to know what kind of info and how to process 

MIN_NATIVE_TEXT_CHARS = 20  # below this, a page is assumed to be a scanned image needing OCR

#class is a pythin keyword and every class has its own properties and over here every class has the same properties and methods and the class is a blueprint
# of whcih it creates an object and the object is an instance of the class and the object has its own properties and methods and the object can be used to access the properties and methods of the class


class PageContent(BaseModel):
    page_number: int # this is a field or an attribute and the semi colon introduces type annoatation and the type of the field is int and the field is required and the field is not optional
    text: str
    used_ocr: bool = False

# page content has the information like the page number , the text of the page and whether the ocr was used or not , this is important because t
# he RAG system can use this information to know what kind of info and how to process it
#suppose the pdf has three pages then the page content will genearte page1 , page2 and page 3 
#and all of these will be stores in a list and the list will be stored in the loaded document object and the loaded document object will be returned to the user
# the inheritance of the BaseModel class - which already know how to define a dat amodel, validate it , serialize it, convert it to json 
# this is the advantage of object oriented programming that reuses the existing functionality 

class LoadedDocument(BaseModel):
    metadata: DocumentMetadata
    pages: list[PageContent]
# this is the main output of the loader and it contains the metadata of the document and the pages of the document and the pages are stored in a list and each page is an instance of the PageContent class and the metadata is an instance of the DocumentMetadata class

def _sha256_file(path: Path) -> str: # this is a function that allows us to reuse the code without 
    #the underscore at the beginning of the function indicates that the function is for internal use in this file 
    h = hashlib.sha256() 
    with open(path, "rb") as f: # with is a python keyword that allows us to open a file and automatically close it when we are done with it , this is important because it prevents memory leaks and also prevents the file from being locked by the operating system
        for chunk in iter(lambda: f.read(65536), b""): #rb is read binary mode bcs pdfs are not text files , they are binary files , the iter function is a loop 

            h.update(chunk) # to be read in chunks bcause the file can be very large and reading it all at once can cause memory issues. 
    return h.hexdigest()


#every class has only one perpose 


class DocumentLoader:
    """Extracts per-page text from a PDF, falling back to OCR for pages whose
    native text layer is too sparse (e.g. scanned pages).""" #docstrings that describes the purpose of the class and the class is a blueprint for creating objects and the object is an instance of the class and the object has its own properties and methods and the object can be used to access the properties and methods of the class

    def __init__(self, ocr_enabled: bool = True, ocr_lang: str = "eng"): #dunder methods is called whenever you create an object 

        self.ocr_enabled = ocr_enabled
        self.ocr_lang = ocr_lang

    def load(self, path: str, doc_type: DocType = DocType.OTHER) -> LoadedDocument:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"No such file: {path}")

        pages = self._extract_native_text(file_path)
        if self.ocr_enabled and file_path.suffix.lower() != ".txt":
            pages = [
                self._ocr_page(file_path, page) if self._needs_ocr(page) else page
                for page in pages
            ]

        doc_id = hashlib.sha256(file_path.name.encode("utf-8")).hexdigest()[:16]
        metadata = DocumentMetadata(
            doc_id=doc_id,
            filename=file_path.name,
            doc_type=doc_type,
            source_path=str(file_path),
            num_pages=len(pages),
            ingested_at=datetime.now(timezone.utc).isoformat(),
            sha256=_sha256_file(file_path),
        )
        return LoadedDocument(metadata=metadata, pages=pages)

    def _extract_native_text(self, path: Path) -> list[PageContent]:
        if path.suffix.lower() == ".txt":
            # Plain-text documents (e.g. vendored sample docs) are treated as a
            # single page; no OCR is ever needed for them.
            text = path.read_text(encoding="utf-8")
            return [PageContent(page_number=1, text=text)]

        import pdfplumber

        pages: list[PageContent] = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages.append(PageContent(page_number=i, text=text))
        return pages

    def _needs_ocr(self, page: PageContent) -> bool:
        return len(page.text.strip()) < MIN_NATIVE_TEXT_CHARS

    def _ocr_page(self, path: Path, page: PageContent) -> PageContent:
        try:
            import pytesseract
            from pdf2image import convert_from_path

            images = convert_from_path(
                str(path), first_page=page.page_number, last_page=page.page_number
            )
            if not images:
                return page
            text = pytesseract.image_to_string(images[0], lang=self.ocr_lang)
            return PageContent(page_number=page.page_number, text=text, used_ocr=True)
        except Exception:
            # OCR deps (pip packages) or the underlying Tesseract/Poppler
            # binaries aren't available -- degrade to whatever native text
            # extraction found rather than failing the whole ingest request.
            return page


def _main() -> None:
    parser = argparse.ArgumentParser(description="Load a PDF and inspect extracted text quality.")
    parser.add_argument("--path", required=True, help="Path to the PDF file.")
    parser.add_argument(
        "--doc-type", default=DocType.OTHER.value, choices=[d.value for d in DocType]
    )
    parser.add_argument("--inspect", action="store_true", help="Print per-page extracted text.")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR fallback.")
    args = parser.parse_args()

    loader = DocumentLoader(ocr_enabled=not args.no_ocr)
    doc = loader.load(args.path, doc_type=DocType(args.doc_type))

    print(f"doc_id={doc.metadata.doc_id} filename={doc.metadata.filename} pages={doc.metadata.num_pages}")
    if args.inspect:
        for page in doc.pages:
            print(f"\n--- page {page.page_number} (ocr={page.used_ocr}, chars={len(page.text)}) ---")
            print(page.text[:2000])


if __name__ == "__main__":
    _main()
