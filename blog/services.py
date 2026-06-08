import base64
import os
from datetime import datetime

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from .models import WorkAssignment, WorkAssignmentDeadlineChange

class WorkAssignmentService:
    @staticmethod
    @transaction.atomic
    def reschedule_deadline(
        assignment: WorkAssignment, *,
        new_target_deadline=None,
        new_hard_deadline=None,
        new_time_window_start=None,
        new_time_window_end=None,
        reason: str = "",
        user=None,
        expected_deadline_version: int | None = None,
    ):
        # 1) защита от гонок: версия
        if expected_deadline_version is not None:
            updated = WorkAssignment.objects.filter(
                pk=assignment.pk, deadline_version=expected_deadline_version
            ).update(deadline_version=expected_deadline_version + 1)
            if updated == 0:
                raise RuntimeError("Конфликт версий дедлайна. Обновите карточку и повторите.")
            assignment.deadline_version = expected_deadline_version + 1

        # 2) запомним старые значения
        old = dict(
            target=assignment.target_deadline,
            hard=assignment.hard_deadline,
            tws=assignment.time_window_start,
            twe=assignment.time_window_end,
        )

        # 3) применим только переданные поля
        if new_target_deadline is not None:
            assignment.target_deadline = new_target_deadline
        if new_hard_deadline is not None:
            assignment.hard_deadline = new_hard_deadline
        if new_time_window_start is not None:
            assignment.time_window_start = new_time_window_start
        if new_time_window_end is not None:
            assignment.time_window_end = new_time_window_end

        # 4) проверки
        today = timezone.localdate()
        eff = assignment.effective_deadline
        if eff and eff < today:
            raise ValueError("Новый дедлайн не может быть в прошлом.")
        assignment.full_clean()

        # 5) аудит
        WorkAssignmentDeadlineChange.objects.create(
            assignment=assignment,
            old_target_deadline=old["target"],
            old_hard_deadline=old["hard"],
            old_time_window_start=old["tws"],
            old_time_window_end=old["twe"],
            new_target_deadline=assignment.target_deadline,
            new_hard_deadline=assignment.hard_deadline,
            new_time_window_start=assignment.time_window_start,
            new_time_window_end=assignment.time_window_end,
            reason=reason or "",
            changed_by=user,
        )

        # 6) служебные поля
        assignment.reschedule_count = (assignment.reschedule_count or 0) + 1

        # 7) сохранить
        assignment.save(update_fields=[
            "target_deadline","hard_deadline","time_window_start","time_window_end",
            "reschedule_count","deadline_version",
            "date_of_change","last_editor"
        ])

        return assignment


class UniversalRKDService:
    _IMAGE_MIMES = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "webp": "image/webp",
    }

    @staticmethod
    def generate_approval_sheet(rkd, user):
        """Генерирует PDF «Лист утверждения» и сохраняет в rkd.approval_document."""
        signatures = rkd.signatures.select_related("signed_by").order_by("role")

        sig_data = []
        for sig in signatures:
            img_b64 = None
            date_str = ""
            if sig.signature_file:
                try:
                    ext = sig.signature_file.name.rsplit(".", 1)[-1].lower()
                    mime = UniversalRKDService._IMAGE_MIMES.get(ext)
                    if mime:
                        with sig.signature_file.open("rb") as f:
                            raw = f.read()
                        img_b64 = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
                    try:
                        mtime = os.path.getmtime(sig.signature_file.path)
                        date_str = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y")
                    except Exception:
                        pass
                except Exception:
                    pass
            sig_data.append({
                "role": sig.get_role_display(),
                "signed_by": (
                    sig.signed_by.get_full_name() or sig.signed_by.username
                    if sig.signed_by else "—"
                ),
                "img_b64": img_b64,
                "date": date_str,
            })

        context = {
            "rkd": rkd,
            "signatures": sig_data,
            "generated_at": timezone.now(),
        }

        html_string = render_to_string("pdf/approval_sheet_template.html", context)
        pdf_bytes = HTML(string=html_string).write_pdf()

        desig = (rkd.desig_document or str(rkd.pk)).replace("/", "_").replace(" ", "_")
        filename = f"ЛУ_{desig}.pdf"

        if rkd.approval_document:
            rkd.approval_document.delete(save=False)

        rkd.approval_document.save(filename, ContentFile(pdf_bytes), save=True)

        return filename
