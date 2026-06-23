import os
import re
from datetime import datetime

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from .document_types import get_config_for_document, signer_department_label
from .models import ApprovalSheetRecord


def _safe_part(value: str, fallback: str = "doc") -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", (value or "").strip())
    return cleaned or fallback


def _build_rows(records) -> list[dict]:
    rows = []
    for i, rec in enumerate(records, start=1):
        fio = rec.cert_cn or (
            rec.signed_by.get_full_name() or rec.signed_by.username
            if rec.signed_by else "—"
        )
        date_str = rec.signed_at.strftime("%d.%m.%Y") if rec.signed_at else ""
        position = rec.position or signer_department_label(rec.signed_by) or "—"
        rows.append({
            "number": i,
            "role": rec.role_label or "—",
            "position": position,
            "fio": fio,
            "cert_cn": rec.cert_cn or "",
            "cert_issuer": rec.cert_issuer or "",
            "date": date_str,
        })
    return rows


def _collect_rkd_approval_rows(rkd) -> list[dict]:
    rows = []
    for i, sig in enumerate(
        rkd.signatures.select_related("signed_by__profile").order_by("role"), start=1
    ):
        date_str = ""
        if getattr(sig, "signed_at", None):
            date_str = sig.signed_at.strftime("%d.%m.%Y")
        elif sig.signature_file:
            try:
                mtime = os.path.getmtime(sig.signature_file.path)
                date_str = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y")
            except Exception:
                pass
        cert_cn = getattr(sig, "cert_cn", "") or ""
        fio = cert_cn or (
            sig.signed_by.get_full_name() or sig.signed_by.username
            if sig.signed_by else "—"
        )
        rows.append({
            "number": i,
            "role": sig.get_role_display(),
            "position": signer_department_label(sig.signed_by) or "—",
            "fio": fio,
            "cert_cn": cert_cn,
            "cert_issuer": getattr(sig, "cert_issuer", "") or "",
            "date": date_str,
        })
    return rows


def _collect_rkd_acquaintance_rows(rkd, process) -> list[dict]:
    from blog.models import UniversalRKDAcknowledgment

    acks = (
        UniversalRKDAcknowledgment.objects
        .filter(rkd=rkd, process=process)
        .select_related("signed_by__profile", "department")
        .order_by("step_order", "pk")
    )
    rows = []
    for i, ack in enumerate(acks, start=1):
        fio = ack.cert_cn or (
            ack.signed_by.get_full_name() or ack.signed_by.username
            if ack.signed_by else "—"
        )
        date_str = ack.signed_at.strftime("%d.%m.%Y") if ack.signed_at else ""
        rows.append({
            "number": i,
            "position": ack.position or signer_department_label(ack.signed_by) or "—",
            "fio": fio,
            "cert_cn": ack.cert_cn or "",
            "cert_issuer": ack.cert_issuer or "",
            "date": date_str,
        })
    return rows


def _collect_generic_rows(process, sheet_type) -> list[dict]:
    records = (
        ApprovalSheetRecord.objects
        .filter(process=process, sheet_type=sheet_type)
        .select_related("signed_by__profile", "department")
        .order_by("step_order", "pk")
    )
    return _build_rows(records)


def _render_pdf(document, *, sheet_title: str, rows: list[dict], show_role: bool = False) -> bytes:
    cfg = get_config_for_document(document)
    context = {
        "sheet_title": sheet_title,
        "center_line": cfg.get_center_line(document),
        "doc_info_lines": cfg.get_doc_info_lines(document),
        "rows": rows,
        "show_role": show_role,
        "generated_at": timezone.now(),
    }
    html_string = render_to_string("pdf/workflow_sheet_template.html", context)
    return HTML(string=html_string).write_pdf()


def _save_pdf(document, field_name: str, prefix: str, name_part: str, pdf_bytes: bytes):
    cfg = get_config_for_document(document)
    filename = f"{prefix}_{_safe_part(name_part, str(document.pk))}.pdf"
    existing = getattr(document, field_name, None)
    if existing:
        existing.delete(save=False)
    getattr(document, field_name).save(filename, ContentFile(pdf_bytes), save=True)
    return filename


def generate_approval_sheet(document, process=None):
    cfg = get_config_for_document(document)
    if cfg.key == "rkd":
        rows = _collect_rkd_approval_rows(document)
    else:
        rows = _collect_generic_rows(process, ApprovalSheetRecord.SHEET_APPROVAL)

    pdf_bytes = _render_pdf(
        document, sheet_title="Лист утверждения", rows=rows, show_role=True,
    )
    name_part = cfg.get_center_line(document)
    return _save_pdf(
        document,
        cfg.approval_document_field,
        cfg.approval_filename_prefix,
        name_part,
        pdf_bytes,
    )


def generate_acquaintance_sheet(document, process):
    cfg = get_config_for_document(document)
    if cfg.key == "rkd":
        rows = _collect_rkd_acquaintance_rows(document, process)
    else:
        rows = _collect_generic_rows(process, ApprovalSheetRecord.SHEET_ACQUAINTANCE)

    pdf_bytes = _render_pdf(document, sheet_title="Лист ознакомления", rows=rows)
    name_part = cfg.get_center_line(document)
    return _save_pdf(
        document,
        cfg.acquaintance_document_field,
        cfg.acquaintance_filename_prefix,
        name_part,
        pdf_bytes,
    )
