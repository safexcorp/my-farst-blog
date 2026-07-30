from django.db import transaction
from django.utils import timezone

from .models import WorkAssignment, WorkAssignmentDeadlineChange

_UNSET = object()

class WorkAssignmentService:
    @staticmethod
    @transaction.atomic
    def reschedule_deadline(
        assignment: WorkAssignment, *,
        new_target_deadline=None,
        new_time_window_start=None,
        new_time_window_end=None,
        new_hard_deadline=_UNSET,
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
        hard_reset = False
        if new_target_deadline is not None:
            assignment.target_deadline = new_target_deadline
        if new_time_window_start is not None:
            assignment.time_window_start = new_time_window_start
        if new_time_window_end is not None:
            assignment.time_window_end = new_time_window_end
        if new_hard_deadline is not _UNSET:
            assignment.hard_deadline = new_hard_deadline
        elif new_target_deadline is not None and new_target_deadline != old["target"] and old["hard"] is not None:
            assignment.hard_deadline = None
            hard_reset = True

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

        assignment._hard_deadline_reset = hard_reset
        return assignment


class UniversalRKDService:
    @staticmethod
    def generate_approval_sheet(rkd, user):
        from approvals.sheet_service import generate_approval_sheet
        return generate_approval_sheet(rkd)

    @staticmethod
    def generate_acquaintance_sheet(rkd, process):
        from approvals.sheet_service import generate_acquaintance_sheet
        return generate_acquaintance_sheet(rkd, process)
