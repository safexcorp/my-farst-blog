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


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blog"
    verbose_name = _("PLC (Управление жизненным циклом продуктов)")

    def ready(self):
        from django.contrib import admin

        post_migrate.connect(_backfill_wa_codes, sender=self)

        site = admin.site
        _orig_get_app_list = site.get_app_list

        def get_app_list(self, request, app_label=None):
            app_list = _orig_get_app_list(request, app_label)
            first = [a for a in app_list if a.get("app_label") == "blog"]
            rest = [a for a in app_list if a.get("app_label") != "blog"]
            return first + rest

        site.get_app_list = types.MethodType(get_app_list, site)
