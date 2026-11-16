"""Documents: upload, extraction, passages, retrieval filters, deletion and isolation."""

import io
import os
from pathlib import Path

import pytest
from docx import Document as Docx
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app import extract


def pdf(*pages: str) -> bytes:
    buffer = io.BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=A4)
    for text in pages:
        y = 800
        for line in text.split("\n"):
            sheet.drawString(50, y, line)
            y -= 16
        sheet.showPage()
    sheet.save()
    return buffer.getvalue()


def docx(*paragraphs: str) -> bytes:
    doc = Docx()
    for text in paragraphs:
        doc.add_paragraph(text)
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Dividend per share", "3.00"
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def xlsx() -> bytes:
    book = Workbook()
    book.active.title = "P&L"
    for row in (["Item", "FY24", "FY25"], ["Revenue", 532, 608], ["PAT", 351, 429]):
        book.active.append(row)
    book.create_sheet("Volumes").append(["DAM volume BU", 61.2])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def upload(client, subject_id, data: bytes, filename: str, **form):
    return client.post("/documents", data={"subject_id": subject_id, **form},
                       files={"file": (filename, data, "application/octet-stream")})


@pytest.fixture
def company(new_user):
    client = new_user()
    client.subject = client.post("/subjects", json={"name": "Northgate Power Exchange"}).json()["id"]
    return client


AR25 = pdf("Northgate Power Exchange Annual Report FY25\nRevenue from operations was 608 crore in FY25.",
           "Auditor's report\nThe auditor drew attention to related party transactions with Northgate Gas.")


def test_pdf_upload_is_extracted_page_by_page(company):
    r = upload(company, company.subject, AR25, "Northgate_Annual_Report_FY25.pdf")
    assert r.status_code == 201, r.text
    doc = company.get(f"/documents/{r.json()['id']}").json()
    assert (doc["status"], doc["pages"], doc["passages"], doc["format"]) == ("ready", 2, 2, "pdf")
    assert (doc["doc_type"], doc["period"], doc["title"]) == ("annual report", "FY25", "Northgate_Annual_Report_FY25")
    assert len(doc["sha256"]) == 64 and doc["size_bytes"] == len(AR25)

    passages = company.get(f"/documents/{doc['id']}/passages").json()
    assert [(p["page"], p["label"]) for p in passages] == [(1, "p. 1"), (2, "p. 2")]
    assert "608 crore" in passages[0]["body"] and "related party" in passages[1]["body"]
    assert [p["page"] for p in company.get(f"/documents/{doc['id']}/passages", params={"page": 2}).json()] == [2]


def test_word_and_excel_are_extracted(company):
    word = upload(company, company.subject, docx("Management expects volumes to grow.", "Coupling starts with DAM."),
                  "Q2FY26 concall transcript.docx").json()
    sheet = upload(company, company.subject, xlsx(), "financials.xlsx", period="FY25", doc_type="results").json()
    assert (word["doc_type"], word["period"]) == ("concall", "Q2 FY26")

    [body] = [p["body"] for p in company.get(f"/documents/{word['id']}/passages").json()]
    assert "Coupling starts with DAM." in body and "Dividend per share | 3.00" in body
    sheets = company.get(f"/documents/{sheet['id']}/passages").json()
    assert [(p["page"], p["label"]) for p in sheets] == [(1, "P&L"), (2, "Volumes")]
    assert "Revenue | 532 | 608" in sheets[0]["body"]


def test_original_file_comes_back_unchanged(company):
    doc = upload(company, company.subject, AR25, "ar.pdf").json()
    r = company.get(f"/documents/{doc['id']}/file")
    assert r.content == AR25 and r.headers["content-type"] == "application/pdf"
    assert 'filename="ar.pdf"' in r.headers["content-disposition"]


def test_bad_uploads_are_refused_or_reported(company):
    assert upload(company, company.subject, b"just some text", "notes.pdf").status_code == 415
    assert upload(company, company.subject, b"MZ\x90\x00 program", "report.pdf").status_code == 415
    assert upload(company, company.subject, b"%PDF-1.7 " + b"0" * 2_100_000, "big.pdf").status_code == 413
    assert upload(company, "00000000-0000-0000-0000-000000000000", AR25, "ar.pdf").status_code == 404

    broken = upload(company, company.subject, b"%PDF-1.7 this is not really a pdf", "broken.pdf").json()
    assert company.get(f"/documents/{broken['id']}").json()["status"] == "failed"
    blank = upload(company, company.subject, pdf(""), "scan.pdf").json()
    got = company.get(f"/documents/{blank['id']}").json()
    assert got["status"] == "no_text" and "scanned" in got["status_note"]

    assert upload(company, company.subject, AR25, "ar.pdf").status_code == 201
    assert upload(company, company.subject, AR25, "same-file-renamed.pdf").status_code == 409


def test_file_name_cannot_escape_the_storage_folder(company, app):
    doc = upload(company, company.subject, AR25, "../../../../tmp/evil.pdf").json()
    assert doc["filename"] == "evil.pdf"
    stored = Path(app.state.config.files_dir) / company.user_id / doc["id"]
    assert stored.read_bytes() == AR25


def test_metadata_can_be_corrected(company):
    doc = upload(company, company.subject, AR25, "scan0001.pdf").json()
    assert (doc["doc_type"], doc["period"]) == ("other", "")
    fixed = company.patch(f"/documents/{doc['id']}", json={"doc_type": "annual report", "period": "FY25",
                                                          "doc_date": "2025-07-30", "title": "Annual report FY25"})
    assert fixed.json()["period"] == "FY25" and fixed.json()["doc_date"] == "2025-07-30"
    assert company.patch(f"/documents/{doc['id']}", json={}).status_code == 422


def test_retrieval_finds_the_right_passage_and_respects_filters(company):
    other = company.post("/subjects", json={"name": "Other Co"}).json()["id"]
    ar25 = upload(company, company.subject, AR25, "Annual report FY25.pdf").json()
    upload(company, company.subject, pdf("Annual Report FY24\nRevenue from operations was 532 crore in FY24."),
           "Annual report FY24.pdf")
    upload(company, other, pdf("Other Co revenue from operations was 999 crore."), "Other AR FY25.pdf")
    company.post("/notes", json={"title": "Revenue view", "subject_id": company.subject, "blocks": [
        {"id": "b1", "content": [{"text": "My read: revenue growth tracks traded volume."}]}]})

    everything = company.get("/retrieve", params={"q": "what was revenue from operations?"}).json()
    assert len(everything["passages"]) == 3

    scoped = company.get("/retrieve", params={"q": "what was revenue from operations?",
                                              "subject_id": company.subject, "period": "FY25"}).json()
    [hit] = scoped["passages"]
    assert hit["document_id"] == ar25["id"] and hit["page"] == 1 and hit["label"] == "p. 1"
    assert "608 crore" in hit["body"] and "<<Revenue>>" in hit["snippet"]
    assert [n["title"] for n in scoped["notes"]] == ["Revenue view"]

    by_type = company.get("/retrieve", params={"q": "revenue", "doc_type": "concall"}).json()
    assert by_type["passages"] == []
    auditor = company.get("/retrieve", params={"q": "auditor related party", "subject_id": company.subject}).json()
    assert auditor["passages"][0]["page"] == 2
    assert company.get("/retrieve", params={"q": "   "}).json() == {"passages": [], "notes": []}
    assert company.get("/retrieve", params={"q": "zebra unicorn"}).json()["passages"] == []


def test_delete_leaves_no_text_no_passage_and_no_file(company, owner, app):
    doc = upload(company, company.subject, pdf("Unique marker quokka-7731 appears only here."), "marker.pdf").json()
    stored = Path(app.state.config.files_dir) / company.user_id / doc["id"]
    assert stored.exists()
    assert len(company.get("/retrieve", params={"q": "quokka-7731"}).json()["passages"]) == 1

    assert company.delete(f"/documents/{doc['id']}").status_code == 204
    assert not stored.exists()
    assert company.get(f"/documents/{doc['id']}").status_code == 404
    assert company.get(f"/documents/{doc['id']}/passages").status_code == 404
    assert company.get(f"/documents/{doc['id']}/file").status_code == 404
    assert company.get("/retrieve", params={"q": "quokka-7731"}).json()["passages"] == []
    for table in ("document", "chunk"):
        for needle in ("quokka-7731", doc["sha256"]):
            left = owner.execute(f"SELECT count(*) FROM {table} WHERE to_jsonb({table})::text LIKE %s",
                                 (f"%{needle}%",))
            assert left.fetchone()[0] == 0, (table, needle)
    # The same file can be uploaded again afterwards.
    again = upload(company, company.subject, pdf("Unique marker quokka-7731 appears only here."), "m.pdf")
    assert again.status_code == 201


def test_deleting_a_company_removes_its_documents_and_files(company, app):
    doc = upload(company, company.subject, AR25, "ar.pdf").json()
    stored = Path(app.state.config.files_dir) / company.user_id / doc["id"]
    company.delete(f"/subjects/{company.subject}")
    assert not stored.exists()
    assert company.get(f"/documents/{doc['id']}").status_code == 404


def test_other_users_cannot_reach_documents(company, new_user, app):
    doc = upload(company, company.subject, pdf("Confidential wombat-551 working."), "private.pdf").json()
    [passage] = company.get(f"/documents/{doc['id']}/passages").json()
    b = new_user()
    theirs = b.post("/subjects", json={"name": "B Co"}).json()["id"]

    assert b.get("/documents", params={"subject_id": company.subject}).json() == []
    for path in ("", "/passages", "/file"):
        assert b.get(f"/documents/{doc['id']}{path}").status_code == 404
    assert b.patch(f"/documents/{doc['id']}", json={"title": "mine now"}).status_code == 404
    assert b.delete(f"/documents/{doc['id']}").status_code == 404
    assert b.get("/retrieve", params={"q": "wombat-551"}).json() == {"passages": [], "notes": []}
    assert upload(b, company.subject, AR25, "ar.pdf").status_code == 404
    # The same file under B's own company is B's own copy, stored separately.
    mine = upload(b, theirs, pdf("Confidential wombat-551 working."), "private.pdf").json()
    assert mine["id"] != doc["id"]
    assert sorted(os.listdir(app.state.config.files_dir + "/" + b.user_id)) == [mine["id"]]
    assert company.get(f"/documents/{doc['id']}/passages").json()[0]["id"] == passage["id"]


# ------------------------------------------------------------ extraction, without the web layer

def test_passages_respect_the_limit_and_lose_nothing():
    paragraph = "Sentence one is here. " * 40           # ~880 characters
    text = "\n\n".join([paragraph.strip()] * 5) + "\n\n" + "x" * 4000
    cut = extract.passages(text, limit=1800)
    assert all(len(p) <= 1800 for p in cut)
    assert "".join(cut).replace("\n", "").replace(" ", "") == text.replace("\n", "").replace(" ", "")
    assert extract.passages("") == [] and extract.passages("short") == ["short"]


@pytest.mark.parametrize("name, doc_type, period", [
    ("IEX_Annual_Report_FY25.pdf", "annual report", "FY25"),
    ("IEX Q4FY26 Earnings Call Transcript.pdf", "concall", "Q4 FY26"),
    ("Investor Presentation Q1 FY2026.pdf", "presentation", "Q1 FY26"),
    ("results-fy-24.xlsx", "results", "FY24"),
    ("CRISIL rating rationale.pdf", "credit rating", ""),
    ("AR FY2024-25.pdf", "annual report", "FY24"),
    ("random.pdf", "other", ""),
])
def test_metadata_guess(name, doc_type, period):
    assert extract.guess_metadata(name) == {"doc_type": doc_type, "period": period}


def test_sniff_judges_content_not_name():
    assert extract.sniff(AR25) == "pdf" and extract.sniff(docx("x")) == "docx" and extract.sniff(xlsx()) == "xlsx"
    assert extract.sniff(b"PK\x03\x04 not a real zip") is None and extract.sniff(b"") is None
