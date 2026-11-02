import hashlib
from io import BytesIO
from textwrap import wrap

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.models.filing import FilingDocument, FilingEnvelope
from app.services.document_service import upload_document


def sample_document(filing: FilingEnvelope, document_type_code: str, title: str) -> FilingDocument:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        }
    )
    lines = [
        "DEMONSTRATION ONLY - NOT A COURT FILING",
        "",
        *wrap(title, width=72),
        "",
        "This is synthetic sample content for evaluating MUEFS.",
        "Upload your own test documents through the filing workflow.",
        "Do not use this sample as a legal form or evidence.",
    ]
    commands = ["BT /F1 12 Tf 50 720 Td 18 TL"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({escaped}) Tj T*")
    commands.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("latin-1", errors="replace"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/Title": title, "/Author": "MUEFS synthetic demo"})
    output = BytesIO()
    writer.write(output)
    content = output.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    key = f"demo/{digest}.pdf"
    upload_document(content, key, "application/pdf")
    return FilingDocument(
        envelope_id=filing.id,
        document_type_code=document_type_code,
        title=title,
        file_key=key,
        file_size_bytes=len(content),
        mime_type="application/pdf",
        sha256_hash=digest,
        page_count=1,
        is_text_searchable=True,
        pii_warnings=[],
        retained_at=filing.submitted_at,
    )
