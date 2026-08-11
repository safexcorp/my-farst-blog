import types

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


def _backfill_wa_codes(sender, **kwargs):
    from .helpers import next_free_wa_code
    from .models import Post, WorkAssignment, WorkAssignmentSubtask

    posts_to_code = list(
        Post.objects.filter(wa_code__isnull=True).order_by("pk")
    )
    if posts_to_code:
        taken = set(
            Post.objects.exclude(wa_code__isnull=True).values_list("wa_code", flat=True)
        )
        for post in posts_to_code:
            code = next_free_wa_code(taken)
            taken.add(code)
            Post.objects.filter(pk=post.pk).update(wa_code=code)

    unnumbered_post_ids = list(
        WorkAssignment.objects.filter(post_id__isnull=False, wa_number__isnull=True)
        .values_list("post_id", flat=True)
        .distinct()
    )
    for post_id in unnumbered_post_ids:
        pks = list(
            WorkAssignment.objects.filter(post_id=post_id)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        for i, pk in enumerate(pks, start=1):
            WorkAssignment.objects.filter(pk=pk).update(wa_number=i)

    unnumbered_wa_ids = list(
        WorkAssignmentSubtask.objects.filter(
            work_assignment_id__isnull=False, subtask_number__isnull=True
        )
        .values_list("work_assignment_id", flat=True)
        .distinct()
    )
    for wa_id in unnumbered_wa_ids:
        from django.db.models import Max
        last = (
            WorkAssignmentSubtask.objects.filter(work_assignment_id=wa_id)
            .exclude(subtask_number__isnull=True)
            .aggregate(m=Max("subtask_number"))["m"]
            or 0
        )
        pks = list(
            WorkAssignmentSubtask.objects.filter(
                work_assignment_id=wa_id, subtask_number__isnull=True
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        for offset, pk in enumerate(pks, start=1):
            WorkAssignmentSubtask.objects.filter(pk=pk).update(
                subtask_number=last + offset
            )


def _close_subtasks_for_closed_parents(sender, **kwargs):
    from django.db.models import Q
    from django.utils import timezone
    from .models import WorkAssignment, WorkAssignmentSubtask

    non_terminal = Q(control_status__isnull=True) | Q(
        control_status__in=WorkAssignment.ACTIVE_STATUSES
    )
    stale = WorkAssignmentSubtask.objects.filter(non_terminal).filter(
        work_assignment__control_status__in=WorkAssignment.TERMINAL_STATUSES
    ).select_related("work_assignment")

    today = timezone.localdate()
    for subtask in stale:
        subtask.control_status = subtask.work_assignment.control_status
        subtask.control_date = today
        subtask.save(update_fields=["control_status", "control_date"])


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blog"
    verbose_name = _("PLC (Управление жизненным циклом продуктов)")

    def ready(self):
        from django.contrib import admin
        from django.contrib.admin.options import BaseModelAdmin
        from django.contrib.auth import get_user_model
        from django.core.exceptions import ValidationError

        post_migrate.connect(_backfill_wa_codes, sender=self)
        post_migrate.connect(_close_subtasks_for_closed_parents, sender=self)

        #выбрать неактивного пользователя нельзя -
        # при сохранении формы падает ошибка валидации.
        User = get_user_model()
        _orig_formfield_for_foreignkey = BaseModelAdmin.formfield_for_foreignkey

        def formfield_for_foreignkey(self, db_field, request, **kwargs):
            field = _orig_formfield_for_foreignkey(self, db_field, request, **kwargs)
            if field is not None and db_field.related_model is User:
                orig_clean = field.clean

                def clean(value, _orig_clean=orig_clean):
                    user = _orig_clean(value)
                    if user is not None and not user.is_active:
                        raise ValidationError("Этот пользователь неактивен, его нельзя выбрать.")
                    return user

                field.clean = clean
            return field

        BaseModelAdmin.formfield_for_foreignkey = formfield_for_foreignkey

        site = admin.site
        _orig_get_app_list = site.get_app_list

        def get_app_list(self, request, app_label=None):
            app_list = _orig_get_app_list(request, app_label)
            first = [a for a in app_list if a.get("app_label") == "blog"]
            rest = [a for a in app_list if a.get("app_label") != "blog"]
            return first + rest

        site.get_app_list = types.MethodType(get_app_list, site)
