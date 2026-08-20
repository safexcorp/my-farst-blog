import base64

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .admin_forms import MyProfileForm, RejectTaskForm, StartApprovalForm
from .apps import GROUP_ADMIN
from .document_types import (
    DOCUMENT_TYPE_FILTER_CHOICES,
    get_config_by_key,
    get_config_for_document,
    get_config_for_process,
    get_document_from_process,
    processes_for_user_q,
    resolve_documents,
    task_doc_context,
    user_can_view_process,
)
from .models import (
    Department,
    DepartmentMember,
    Vacation,
    ApprovalRoute,
    AcknowledgmentRoute,
    ApprovalRouteStep,
    ApprovalProcess,
    ApprovalTask,
    Notification,
)
from .services import ApprovalEngine, resolve_assignee, _resolve_step_users


def is_approval_admin(user):
    return user.groups.filter(name=GROUP_ADMIN).exists()


class ProcessDocumentTypeFilter(admin.SimpleListFilter):
    title = "Тип документа"
    parameter_name = "document_type"

    def lookups(self, request, model_admin):
        return DOCUMENT_TYPE_FILTER_CHOICES

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        cfg = get_config_by_key(value)
        ct = cfg.get_content_type()
        if value == "rkd":
            return queryset.filter(Q(content_type=ct) | Q(rkd__isnull=False)).distinct()
        return queryset.filter(content_type=ct)


class ProcessRouteActionFilter(admin.SimpleListFilter):
    title = "Тип шага маршрута"
    parameter_name = "route_action"

    def lookups(self, request, model_admin):
        return (
            (ApprovalRouteStep.ACTION_SIGN, "Согласование / подпись"),
            (ApprovalRouteStep.ACTION_ACK, "Ознакомление"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(
            tasks__step__action_type=value,
            tasks__kind=ApprovalTask.KIND_REVIEW,
        ).distinct()


def _task_has_signature(task):
    return bool(task.signature_b64) or bool(task.signature_file)


def _eds_download_links(task):
    sig_url = reverse(
        "admin:approvals_approvalprocess_download_sig",
        args=[task.process_id, task.pk],
    )
    payload_url = reverse(
        "admin:approvals_approvalprocess_download_payload",
        args=[task.process_id, task.pk],
    )
    return format_html(
        '<a href="{}" target="_blank" style="font-weight:600;">Скачать .sig</a>'
        ' &nbsp;|&nbsp; '
        '<a href="{}" target="_blank">Скачать подписанный файл</a>',
        sig_url, payload_url,
    )


class _AdminOrPermissionMixin:
    """Доступ есть у группы «Согласование: Администратор» ИЛИ у любого,
    кому явно выданы соответствующие Django-права (view/add/change/delete) —
    аддитивно, права группы «Администратор» этим не урезаются."""

    def has_module_permission(self, request):
        return is_approval_admin(request.user) or super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return is_approval_admin(request.user) or super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return is_approval_admin(request.user) or super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return is_approval_admin(request.user) or super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return is_approval_admin(request.user) or super().has_delete_permission(request, obj)


class _ChildOfParentPermissionMixin:
    """Права на подсущность = права на родителя (self.parent_model) — своего
    отдельного права у неё нет, доступна только через родителя."""

    def _parent_can(self, request, action):
        parent_admin = admin.site._registry.get(self.parent_model)
        return bool(parent_admin) and getattr(parent_admin, f"has_{action}_permission")(request)

    def has_view_permission(self, request, obj=None):
        return self._parent_can(request, "view") or self._parent_can(request, "change")

    def has_add_permission(self, request, obj=None):
        return self._parent_can(request, "change")

    def has_change_permission(self, request, obj=None):
        return self._parent_can(request, "change")

    def has_delete_permission(self, request, obj=None):
        return self._parent_can(request, "change")


class DepartmentMemberInline(_ChildOfParentPermissionMixin, admin.TabularInline):
    model = DepartmentMember
    extra = 1
    autocomplete_fields = ("user",)
    verbose_name = "Сотрудник роли"
    verbose_name_plural = "Сотрудники роли (главный + заместители по очереди)"

    class Media:
        js = ("approvals/js/inline_order.js",)


@admin.register(Department)
class DepartmentAdmin(_AdminOrPermissionMixin, admin.ModelAdmin):
    list_display = ("name", "code", "members_preview", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    inlines = [DepartmentMemberInline]

    @admin.display(description="Состав")
    def members_preview(self, obj):
        parts = []
        for m in obj.members.select_related("user").order_by("-is_main", "order"):
            role = "главный" if m.is_main else f"зам.{m.order}"
            parts.append(f"{m.user} ({role})")
        return ", ".join(parts) or "—"


@admin.register(Vacation)
class VacationAdmin(_AdminOrPermissionMixin, admin.ModelAdmin):
    list_display = (
        "user", "absence_type", "start_date", "end_date",
        "days_display", "reason",
    )
    list_filter = ("absence_type", "start_date", "end_date")
    search_fields = ("user__username", "user__last_name", "reason")
    autocomplete_fields = ("user",)
    date_hierarchy = "start_date"
    fields = ("user", "absence_type", ("start_date", "end_date"), "reason")

    @admin.display(description="Дней", ordering="start_date")
    def days_display(self, obj):
        return obj.days if obj.days is not None else "—"


def _route_steps_preview(obj):
    steps = obj.steps.select_related("department", "org_department").order_by("order")
    if not steps:
        return "—"
    lines = []
    for s in steps:
        if s.target_type == ApprovalRouteStep.TARGET_ALL:
            lines.append(format_html("<div><b>{}.</b> {}</div>", s.order, s.target_label))
            continue

        people = [u for u in _resolve_step_users(s) if u]
        names = [u.get_full_name() or u.username for u in people]
        if names:
            who = ", ".join(names[:8])
            if len(names) > 8:
                who += f" и ещё {len(names) - 8}"
        else:
            who = "не назначен"
        lines.append(format_html("<div><b>{}.</b> {} — {}</div>", s.order, s.target_label, who))
    return format_html_join("", "{}", ((line,) for line in lines))


_WORK_STATUS_ORDER = ("assigned", "in_progress", "reschedule_pending", "review", "done")
_WORK_STATUS_LABELS = {
    "assigned": "Ожидает принятия",
    "in_progress": "В работе",
    "reschedule_pending": "Согласование переноса срока",
    "review": "На проверке",
    "done": "Завершённые",
}


def _group_work_by_status(items):
    buckets = {key: [] for key in _WORK_STATUS_ORDER}
    for item in items:
        st = item.control_status
        if st in ("on_time", "rescheduled", "partial", "not_done"):
            key = "done"
        elif st == "assigned":
            key = "assigned"
        elif st == "review":
            key = "review"
        elif st == "reschedule_pending":
            key = "reschedule_pending"
        else:
            key = "in_progress"
        buckets[key].append(item)
    for key in ("assigned", "in_progress"):
        buckets[key].sort(key=lambda wa: not wa.is_urgent)
    return [
        {
            "key": key,
            "label": _WORK_STATUS_LABELS[key],
            "items": buckets[key],
            "count": len(buckets[key]),
        }
        for key in _WORK_STATUS_ORDER
    ]


def _group_issued_work_by_lanes(items):
    """Те же колонки по статусу, но каждая разбита на дорожки по исполнителю."""
    buckets = _group_work_by_status(items)
    for bucket in buckets:
        lanes_map = {}
        order = []
        for wa in bucket["items"]:
            key = wa.executor_id or 0
            if key not in lanes_map:
                lanes_map[key] = {"executor": wa.executor, "items": []}
                order.append(key)
            lanes_map[key]["items"].append(wa)
        lanes = [lanes_map[key] for key in order]
        lanes.sort(key=lambda lane: (lane["executor"].username.lower() if lane["executor"] else "￿"))
        bucket["lanes"] = lanes
    return buckets


def _group_subtasks_by_status(items):
    buckets = {key: [] for key in _WORK_STATUS_ORDER}
    for item in items:
        st = item.control_status
        if st in ("on_time", "rescheduled", "partial", "not_done"):
            key = "done"
        elif st == "review":
            key = "review"
        elif st == "reschedule_pending":
            key = "reschedule_pending"
        elif st == "in_progress":
            key = "in_progress"
        else:
            key = "assigned"
        buckets[key].append(item)
    for key in buckets:
        buckets[key].sort(key=lambda s: (s.work_assignment_id, s.subtask_number or 0, s.pk))
    return [
        {
            "key": key,
            "label": _WORK_STATUS_LABELS[key],
            "items": buckets[key],
            "count": len(buckets[key]),
        }
        for key in _WORK_STATUS_ORDER
    ]


def _collect_responsible_items(user, limit_per_model=200):
    """Все объекты во всех моделях, где пользователь — «Текущий ответственный»."""
    from django.apps import apps
    from django.contrib.auth import get_user_model
    from django.core.exceptions import FieldDoesNotExist
    from django.db.models import ForeignKey
    from django.urls import NoReverseMatch

    user_model = get_user_model()
    excluded_labels = {"blog.workassignment", "blog.workassignmentsubtask"}
    items = []
    for model in apps.get_models():
        if model._meta.label_lower in excluded_labels:
            continue
        try:
            field = model._meta.get_field("current_responsible")
        except FieldDoesNotExist:
            continue
        if not isinstance(field, ForeignKey):
            continue
        if field.remote_field.model is not user_model:
            continue
        try:
            objs = list(
                model.objects.filter(current_responsible=user).order_by("-pk")[:limit_per_model]
            )
        except Exception:
            # Пропускаем модель, если её таблица недоступна / рассинхронизирована со схемой.
            continue
        for obj in objs:
            try:
                url = reverse(
                    f"admin:{model._meta.app_label}_{model._meta.model_name}_change",
                    args=[obj.pk],
                )
            except NoReverseMatch:
                url = ""
            items.append({
                "title": str(obj),
                "model_label": str(model._meta.verbose_name),
                "admin_url": url,
            })
    items.sort(key=lambda x: (x["model_label"], x["title"]))
    return items


class ApprovalRouteStepInline(_ChildOfParentPermissionMixin, admin.TabularInline):
    """Шаги маршрута согласования — только по роли, последовательно."""
    model = ApprovalRouteStep
    extra = 1
    fields = ("order", "department")
    verbose_name = "Шаг маршрута"
    verbose_name_plural = "Шаги маршрута (по порядку)"

    class Media:
        js = ("approvals/js/inline_order.js",)


class AckRouteStepInline(_ChildOfParentPermissionMixin, admin.StackedInline):
    """Шаги маршрута ознакомления — по роли, отделу, всем или руководителям."""
    model = ApprovalRouteStep
    extra = 1
    fields = ("order", "target_type", "department", "org_department")
    verbose_name = "Шаг маршрута"
    verbose_name_plural = "Шаги маршрута (по порядку)"

    class Media:
        js = (
            "approvals/js/inline_order.js",
            "approvals/js/ack_step_target.js",
        )


@admin.register(ApprovalRoute)
class ApprovalRouteAdmin(_AdminOrPermissionMixin, admin.ModelAdmin):
    list_display = ("name", "steps_preview", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    fields = ("name", "description", "is_active")
    inlines = [ApprovalRouteStepInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(kind=ApprovalRoute.KIND_APPROVAL)

    def save_model(self, request, obj, form, change):
        obj.kind = ApprovalRoute.KIND_APPROVAL
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model is ApprovalRouteStep:
            instances = formset.save(commit=False)
            for obj in formset.deleted_objects:
                obj.delete()
            for obj in instances:
                obj.action_type = ApprovalRouteStep.ACTION_SIGN
                obj.target_type = ApprovalRouteStep.TARGET_ROLE
                obj.org_department = None
                obj.save()
            formset.save_m2m()
        else:
            super().save_formset(request, form, formset, change)

    @admin.display(description="Маршрут (роли → ответственные)")
    def steps_preview(self, obj):
        return _route_steps_preview(obj)


@admin.register(AcknowledgmentRoute)
class AcknowledgmentRouteAdmin(_AdminOrPermissionMixin, admin.ModelAdmin):
    list_display = ("name", "steps_preview", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    fields = ("name", "description", "is_active")
    inlines = [AckRouteStepInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(kind=ApprovalRoute.KIND_ACK)

    def save_model(self, request, obj, form, change):
        obj.kind = ApprovalRoute.KIND_ACK
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model is ApprovalRouteStep:
            instances = formset.save(commit=False)
            for obj in formset.deleted_objects:
                obj.delete()
            for obj in instances:
                obj.action_type = ApprovalRouteStep.ACTION_ACK
                if obj.target_type != ApprovalRouteStep.TARGET_ROLE:
                    obj.department = None
                if obj.target_type != ApprovalRouteStep.TARGET_DEPARTMENT:
                    obj.org_department = None
                obj.save()
            formset.save_m2m()
        else:
            super().save_formset(request, form, formset, change)

    @admin.display(description="Маршрут (адресаты ознакомления)")
    def steps_preview(self, obj):
        return _route_steps_preview(obj)


class ApprovalTaskInline(admin.TabularInline):
    """Только просмотр — задачи создаёт/меняет ApprovalEngine, не форма."""
    model = ApprovalTask
    extra = 0
    can_delete = False
    fields = (
        "kind", "department", "assigned_to", "status", "is_recheck",
        "eds_info", "eds_download", "comment", "created_at", "resolved_at",
    )
    readonly_fields = fields
    verbose_name = "Задача"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
    verbose_name_plural = "История задач"

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="ЭЦП")
    def eds_info(self, obj):
        if not _task_has_signature(obj):
            return "—"
        parts = []
        if obj.signer_cn:
            parts.append(obj.signer_cn)
        if obj.signer_cert_issuer:
            parts.append(f"УЦ: {obj.signer_cert_issuer}")
        if obj.signer_cert_valid_to:
            parts.append(f"до {obj.signer_cert_valid_to}")
        return " · ".join(parts) if parts else "Подписано"

    @admin.display(description="Скачать")
    def eds_download(self, obj):
        if not _task_has_signature(obj):
            return "—"
        return _eds_download_links(obj)


@admin.register(ApprovalProcess)
class ApprovalProcessAdmin(admin.ModelAdmin):
    list_display = (
        "document_link", "document_type_display", "route", "status_display", "current_order",
        "eds_count", "started_by", "created_at",
    )
    list_filter = ("status", "route", ProcessDocumentTypeFilter, ProcessRouteActionFilter)
    search_fields = (
        "rkd__name", "rkd__desig_document",
        "object_id",
    )
    inlines = [ApprovalTaskInline]
    actions = ["cancel_action"]
    fieldsets = (
        ("Согласование", {
            "fields": (
                "content_type", "object_id", "rkd", "route", "status",
                "current_order", "started_by", "created_at", "finished_at",
            ),
        }),
        ("Электронные подписи (ЭЦП)", {
            "description": (
                "Файлы для проверки подлинности подписи. "
                "Для проверки в КриптоПро нужны оба файла: .sig и подписанный документ."
            ),
            "fields": ("eds_signatures_block",),
        }),
    )

    def has_module_permission(self, request):
        return request.user.is_authenticated

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return is_approval_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_approval_admin(request.user)

    def get_readonly_fields(self, request, obj=None):
        names = [f.name for f in self.model._meta.fields]
        names.append("eds_signatures_block")
        return names

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            "rkd", "route", "started_by", "content_type",
        )
        if is_approval_admin(request.user):
            return qs
        return qs.filter(processes_for_user_q(request.user)).distinct()

    @admin.display(description="Документ")
    def document_link(self, obj):
        doc = get_document_from_process(obj)
        if doc is None:
            return "—"
        cfg = get_config_for_process(obj)
        if cfg is None:
            return str(doc)
        return format_html(
            '<a href="{}">{}: {}</a>',
            cfg.get_admin_url(doc),
            cfg.label,
            cfg.get_title(doc),
        )

    @admin.display(description="Тип")
    def document_type_display(self, obj):
        cfg = get_config_for_process(obj)
        return cfg.label if cfg else "—"

    @admin.display(description="Документ РКД", ordering="rkd")
    def rkd_link(self, obj):
        return self.document_link(obj)

    @admin.display(description="ЭЦП")
    def eds_count(self, obj):
        signed = [t for t in obj.tasks.all() if _task_has_signature(t)]
        if not signed:
            return "—"
        url = reverse("admin:approvals_approvalprocess_change", args=[obj.pk])
        n = len(signed)
        word = "подпись" if n == 1 else ("подписи" if n < 5 else "подписей")
        return format_html('<a href="{}">{} {}</a>', url, n, word)

    @admin.display(description="Архив ЭЦП")
    def eds_signatures_block(self, obj):
        if obj is None:
            return "—"
        signed = [
            t for t in obj.tasks.select_related("department", "assigned_to").order_by("resolved_at", "pk")
            if _task_has_signature(t)
        ]
        if not signed:
            return format_html(
                '<p style="color:#888;margin:0;">Подписей ЭЦП по этому согласованию пока нет.</p>'
            )

        rows = []
        for t in signed:
            who = t.assigned_to or "—"
            dept = t.department or "—"
            cert = " · ".join(filter(None, [
                t.signer_cn or "",
                f"УЦ: {t.signer_cert_issuer}" if t.signer_cert_issuer else "",
                f"S/N: {t.signer_cert_serial}" if t.signer_cert_serial else "",
                f"до {t.signer_cert_valid_to}" if t.signer_cert_valid_to else "",
            ])) or "Данные сертификата не сохранены"
            when = t.resolved_at.strftime("%d.%m.%Y %H:%M") if t.resolved_at else "—"
            rows.append(format_html(
                "<tr>"
                "<td style='padding:8px;border:1px solid #ccc;'>{}</td>"
                "<td style='padding:8px;border:1px solid #ccc;'>{}</td>"
                "<td style='padding:8px;border:1px solid #ccc;'>{}</td>"
                "<td style='padding:8px;border:1px solid #ccc;font-size:12px;'>{}</td>"
                "<td style='padding:8px;border:1px solid #ccc;'>{}</td>"
                "</tr>",
                dept, who, when, cert, _eds_download_links(t),
            ))

        return format_html(
            "<table style='width:100%;border-collapse:collapse;margin-top:4px;'>"
            "<thead><tr style='background:#f0f0f0;'>"
            "<th style='padding:8px;border:1px solid #ccc;text-align:left;'>Роль</th>"
            "<th style='padding:8px;border:1px solid #ccc;text-align:left;'>Подписант</th>"
            "<th style='padding:8px;border:1px solid #ccc;text-align:left;'>Дата</th>"
            "<th style='padding:8px;border:1px solid #ccc;text-align:left;'>Сертификат</th>"
            "<th style='padding:8px;border:1px solid #ccc;text-align:left;'>Файлы</th>"
            "</tr></thead><tbody>{}</tbody></table>",
            format_html_join("", "{}", ((r,) for r in rows)),
        )

    @admin.display(description="Статус")
    def status_display(self, obj):
        colors = {
            ApprovalProcess.STATUS_IN_PROGRESS: "#2196F3",
            ApprovalProcess.STATUS_APPROVED: "#4CAF50",
            ApprovalProcess.STATUS_CANCELLED: "#9E9E9E",
        }
        color = colors.get(obj.status, "#777")
        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:6px;">'
            '<span style="width:10px;height:10px;border-radius:50%;background:{};'
            'display:inline-block;"></span>{}</span>',
            color, obj.get_status_display(),
        )

    @admin.action(description="Отменить согласование")
    def cancel_action(self, request, queryset):
        if not is_approval_admin(request.user):
            raise PermissionDenied
        done = 0
        for process in queryset:
            try:
                ApprovalEngine.cancel(process, request.user)
                done += 1
            except ValueError as e:
                self.message_user(request, str(e), level=messages.ERROR)
        if done:
            self.message_user(request, f"Отменено согласований: {done}.")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "start/",
                self.admin_site.admin_view(self.start_view),
                name="approvals_approvalprocess_start",
            ),
            path(
                "<int:process_pk>/task/<int:task_pk>/download-sig/",
                self.admin_site.admin_view(self.download_sig_view),
                name="approvals_approvalprocess_download_sig",
            ),
            path(
                "<int:process_pk>/task/<int:task_pk>/download-payload/",
                self.admin_site.admin_view(self.download_payload_view),
                name="approvals_approvalprocess_download_payload",
            ),
        ]
        return custom + urls

    def _get_signed_task(self, request, process_pk, task_pk):
        process = get_object_or_404(ApprovalProcess, pk=process_pk)
        if not is_approval_admin(request.user):
            if not user_can_view_process(request.user, process, is_admin=False):
                raise PermissionDenied
        task = get_object_or_404(ApprovalTask, pk=task_pk, process=process)
        if not task.signature_b64 and not task.signature_file:
            raise Http404("Подпись для этой задачи не найдена.")
        return task

    def download_sig_view(self, request, process_pk, task_pk):
        task = self._get_signed_task(request, process_pk, task_pk)
        if task.signature_file:
            return FileResponse(
                task.signature_file.open("rb"),
                as_attachment=True,
                filename=task.signature_file.name.rsplit("/", 1)[-1],
                content_type="application/pkcs7-signature",
            )
        raw = base64.b64decode(task.signature_b64)
        filename = f"signature_task_{task.pk}.sig"
        return HttpResponse(
            raw,
            content_type="application/pkcs7-signature",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def download_payload_view(self, request, process_pk, task_pk):
        from .sign_utils import SignDocumentError, get_signed_document_for_download, is_file_payload

        task = self._get_signed_task(request, process_pk, task_pk)
        if is_file_payload(task.signed_payload):
            try:
                data, filename, content_type = get_signed_document_for_download(task)
            except SignDocumentError as exc:
                raise Http404(str(exc))
            return HttpResponse(
                data,
                content_type=content_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        payload = task.signed_payload or ""
        document = get_document_from_process(task.process)
        cfg = get_config_for_document(document) if document else None
        name_part = "doc"
        if document and cfg:
            name_part = (cfg.get_center_line(document) or str(document.pk)).replace("/", "_")
        filename = f"signed_payload_{name_part}_task{task.pk}.txt"
        return HttpResponse(
            payload,
            content_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def start_view(self, request):
        mode = request.GET.get("mode") or request.POST.get("mode") or "approval"
        if mode not in ("approval", "ack"):
            mode = "approval"
        kind = ApprovalRoute.KIND_ACK if mode == "ack" else ApprovalRoute.KIND_APPROVAL
        action_label = "ознакомление" if mode == "ack" else "согласование"

        doc_type = (
            request.GET.get("doc_type")
            or request.POST.get("doc_type")
            or "rkd"
        )
        raw_ids = (
            request.GET.get("ids", "")
            or request.POST.get("ids", "")
            or request.GET.get("rkd_ids", "")
            or request.POST.get("rkd_ids", "")
        )
        ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]
        try:
            cfg = get_config_by_key(doc_type)
        except ValueError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return redirect("admin:approvals_approvalprocess_changelist")

        documents = resolve_documents(doc_type, ids)

        if request.method == "POST":
            form = StartApprovalForm(request.POST, kind=kind)
            if form.is_valid():
                route = form.cleaned_data["route"]
                comment = form.cleaned_data.get("comment", "")
                started, errors = 0, []
                for document in documents:
                    try:
                        ApprovalEngine.start(document, route, request.user, comment=comment)
                        started += 1
                    except ValueError as e:
                        errors.append(f"{document}: {e}")
                if started:
                    self.message_user(request, f"Запущено ({action_label}): {started}.")
                for err in errors:
                    self.message_user(request, err, level=messages.ERROR)
                return redirect("admin:approvals_approvalprocess_changelist")
        else:
            form = StartApprovalForm(kind=kind)

        routes_info = [
            {"route": r, "preview": _route_steps_preview(r)}
            for r in ApprovalRoute.objects.filter(is_active=True, kind=kind).order_by("name")
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": f"Отправить на {action_label} — {cfg.label}",
            "form": form,
            "documents": documents,
            "doc_type": doc_type,
            "doc_type_label": cfg.label,
            "ids": raw_ids,
            "mode": mode,
            "mode_label": action_label,
            "routes_info": routes_info,
            "opts": self.model._meta,
        }
        return render(request, "admin/approvals/start_approval.html", context)


@admin.register(ApprovalTask)
class ApprovalTaskAdmin(admin.ModelAdmin):
    list_display = (
        "document_link",
        "document_type_display",
        "kind_display",
        "department",
        "status_display",
        "recheck_flag",
        "created_at",
        "actions_column",
    )
    list_filter = ("status", "kind", "department")
    search_fields = ("process__rkd__name", "process__rkd__desig_document", "process__object_id")
    list_select_related = ("process", "process__rkd", "process__content_type", "department", "step")

    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return is_approval_admin(request.user)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_approval_admin(request.user):
            return qs
        return qs.filter(assigned_to=request.user)

    @admin.display(description="Документ")
    def document_link(self, obj):
        doc = get_document_from_process(obj.process)
        if doc is None:
            return "—"
        cfg = get_config_for_process(obj.process)
        if cfg is None:
            return str(doc)
        return format_html(
            '<a href="{}">{}: {}</a>',
            cfg.get_admin_url(doc),
            cfg.label,
            cfg.get_title(doc),
        )

    @admin.display(description="Тип")
    def document_type_display(self, obj):
        cfg = get_config_for_process(obj.process)
        return cfg.label if cfg else "—"

    @admin.display(description="Документ РКД")
    def rkd_link(self, obj):
        return self.document_link(obj)

    @admin.display(description="Тип")
    def kind_display(self, obj):
        return obj.get_kind_display()

    @admin.display(description="Статус")
    def status_display(self, obj):
        colors = {
            ApprovalTask.STATUS_PENDING: "#2196F3",
            ApprovalTask.STATUS_APPROVED: "#4CAF50",
            ApprovalTask.STATUS_REJECTED: "#E53935",
            ApprovalTask.STATUS_DONE: "#9C27B0",
            ApprovalTask.STATUS_CANCELLED: "#9E9E9E",
        }
        color = colors.get(obj.status, "#777")
        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:6px;">'
            '<span style="width:10px;height:10px;border-radius:50%;background:{};'
            'display:inline-block;"></span>{}</span>',
            color, obj.get_status_display(),
        )

    @admin.display(description="Повтор")
    def recheck_flag(self, obj):
        return "↻" if obj.is_recheck else "—"

    @admin.display(description="Действия")
    def actions_column(self, obj):
        can_act = is_approval_admin_or_assignee(self._request, obj)
        if not can_act or obj.status != ApprovalTask.STATUS_PENDING:
            if obj.comment:
                return format_html('<span title="{}">💬 замечание</span>', obj.comment)
            return "—"

        if obj.kind == ApprovalTask.KIND_REVIEW:
            sign_url = reverse("admin:approvals_task_sign", args=[obj.pk])
            is_ack = obj.step and obj.step.action_type == ApprovalRouteStep.ACTION_ACK
            if is_ack:
                return format_html(
                    '<a class="button" href="{}" '
                    'style="background:#9C27B0;color:#fff;padding:3px 10px;'
                    'border-radius:4px;text-decoration:none;">Ознакомление (ЭЦП)</a>',
                    sign_url,
                )
            reject_url = reverse("admin:approvals_task_reject", args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" '
                'style="background:#4CAF50;color:#fff;padding:3px 10px;'
                'border-radius:4px;text-decoration:none;margin-right:4px;">Подписать</a>'
                '<a class="button" href="{}" '
                'style="background:#E53935;color:#fff;padding:3px 10px;'
                'border-radius:4px;text-decoration:none;">Отклонить</a>',
                sign_url, reject_url,
            )
        if obj.kind == ApprovalTask.KIND_FIX:
            resubmit_url = reverse("admin:approvals_task_resubmit", args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" '
                'style="background:#2196F3;color:#fff;padding:3px 10px;'
                'border-radius:4px;text-decoration:none;">Отправить на доработку</a>',
                resubmit_url,
            )
        return "—"

    def changelist_view(self, request, extra_context=None):
        self._request = request
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "cabinet/",
                self.admin_site.admin_view(self.cabinet_view),
                name="approvals_cabinet",
            ),
            path(
                "cabinet/profile/save/",
                self.admin_site.admin_view(self.my_profile_save_view),
                name="approvals_my_profile_save",
            ),
            path(
                "cabinet/profile/<int:user_id>/",
                self.admin_site.admin_view(self.user_profile_view),
                name="approvals_user_profile",
            ),
            path(
                "cabinet/notifications/read-all/",
                self.admin_site.admin_view(self.notifications_read_all_view),
                name="approvals_notification_read_all",
            ),
            path(
                "cabinet/notifications/clear-all/",
                self.admin_site.admin_view(self.notifications_clear_all_view),
                name="approvals_notification_clear_all",
            ),
            path(
                "cabinet/notifications/<int:pk>/open/",
                self.admin_site.admin_view(self.notification_open_view),
                name="approvals_notification_open",
            ),
            path(
                "cabinet/subtask/<int:pk>/status/",
                self.admin_site.admin_view(self.subtask_status_view),
                name="approvals_subtask_status",
            ),
            path(
                "<int:pk>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="approvals_task_approve",
            ),
            path(
                "<int:pk>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="approvals_task_reject",
            ),
            path(
                "<int:pk>/resubmit/",
                self.admin_site.admin_view(self.resubmit_view),
                name="approvals_task_resubmit",
            ),
            path(
                "<int:pk>/sign/",
                self.admin_site.admin_view(self.sign_view),
                name="approvals_task_sign",
            ),
            path(
                "<int:pk>/sign/content/",
                self.admin_site.admin_view(self.sign_content_view),
                name="approvals_task_sign_content",
            ),
            path(
                "<int:pk>/sign/submit/",
                self.admin_site.admin_view(self.sign_submit_view),
                name="approvals_task_sign_submit",
            ),
        ]
        return custom + urls

    def cabinet_view(self, request):
        from django.db.models import Count

        from blog.models import WorkAssignment, WorkAssignmentSubtask
        from shared_repository.models import EmployeeProfile

        user = request.user
        my_profile, _ = EmployeeProfile.objects.get_or_create(user=user)
        my_profile_form = MyProfileForm(initial={
            "first_name": user.first_name,
            "last_name": user.last_name,
            "patronymic": my_profile.patronymic,
            "birth_date": my_profile.birth_date,
            "phone": my_profile.phone,
            "email": user.email,
            "avatar": my_profile.avatar,
        })
        pending = list(
            ApprovalTask.objects
            .filter(assigned_to=user, status=ApprovalTask.STATUS_PENDING)
            .select_related("process", "process__rkd", "process__content_type", "department", "step")
        )
        sign_tasks, ack_tasks, fix_tasks = [], [], []
        for t in pending:
            t.doc_ctx = task_doc_context(t)
            if t.kind == ApprovalTask.KIND_FIX:
                fix_tasks.append(t)
            elif t.step and t.step.action_type == ApprovalRouteStep.ACTION_ACK:
                ack_tasks.append(t)
            else:
                sign_tasks.append(t)

        active_filter = (
            Q(control_status__isnull=True)
            | Q(control_status__in=WorkAssignment.ACTIVE_STATUSES)
        )
        published_filter = Q(executor__isnull=False)

        my_work_active = list(
            WorkAssignment.objects
            .filter(executor=user)
            .filter(published_filter)
            .filter(active_filter)
            .select_related("post")
            .order_by("target_deadline")
        )
        my_work_done = list(
            WorkAssignment.objects
            .filter(executor=user, control_status__in=WorkAssignment.TERMINAL_STATUSES)
            .filter(published_filter)
            .select_related("post")
            .order_by("-control_date", "-date_of_change")[:30]
        )
        my_work = my_work_active + my_work_done
        my_work_groups = _group_work_by_status(my_work)
        my_work_active_count = len(my_work_active)

        assigned_ids = [
            wa.pk for wa in my_work
            if wa.control_status in (WorkAssignment.STATUS_ASSIGNED, WorkAssignment.STATUS_IN_PROGRESS)
        ]
        if assigned_ids:
            from django.contrib.contenttypes.models import ContentType
            from blog.models import Attachment

            ct = ContentType.objects.get_for_model(WorkAssignment)
            wa_attachments_by_wa = {}
            for a in Attachment.objects.filter(
                content_type=ct, object_id__in=assigned_ids
            ).exclude(kind="result"):
                wa_attachments_by_wa.setdefault(a.object_id, []).append(a)
            for wa in my_work:
                wa.wa_attachments = wa_attachments_by_wa.get(wa.pk, [])

        issued_base = (
            WorkAssignment.objects
            .filter(author=user)
            .filter(published_filter)
            .annotate(subtask_total=Count("subtasks"))
            .select_related("executor", "post")
        )
        issued_active = list(issued_base.filter(active_filter).order_by("target_deadline"))
        issued_done = list(
            issued_base
            .filter(control_status__in=WorkAssignment.TERMINAL_STATUSES)
            .order_by("-control_date", "-date_of_change")[:30]
        )
        issued_work = issued_active + issued_done
        issued_work_groups = _group_issued_work_by_lanes(issued_work)
        issued_work_active = len(issued_active)

        review_ids = [
            wa.pk for wa in issued_work if wa.control_status == WorkAssignment.STATUS_REVIEW
        ]
        if review_ids:
            from django.contrib.contenttypes.models import ContentType
            from blog.models import Attachment

            ct = ContentType.objects.get_for_model(WorkAssignment)
            attachments_by_wa = {}
            task_attachments_by_wa = {}
            for a in Attachment.objects.filter(content_type=ct, object_id__in=review_ids):
                if a.kind == "result":
                    attachments_by_wa.setdefault(a.object_id, []).append(a)
                else:
                    task_attachments_by_wa.setdefault(a.object_id, []).append(a)
            for wa in issued_work:
                wa.review_attachments = attachments_by_wa.get(wa.pk, [])
                wa.review_task_attachments = task_attachments_by_wa.get(wa.pk, [])

        subtasks_base = (
            WorkAssignmentSubtask.objects
            .filter(executor=user)
            .select_related("work_assignment", "work_assignment__post")
        )
        subtasks_active = list(
            subtasks_base
            .exclude(control_status__in=WorkAssignment.TERMINAL_STATUSES)
            .order_by("work_assignment_id", "subtask_number", "pk")
        )
        subtasks_done = list(
            subtasks_base
            .filter(control_status__in=WorkAssignment.TERMINAL_STATUSES)
            .order_by("-control_date", "-date_of_change")[:30]
        )
        my_subtasks = subtasks_active + subtasks_done
        my_subtasks_active_count = len(subtasks_active)
        my_subtasks_groups = _group_subtasks_by_status(my_subtasks)

        assigned_items = _collect_responsible_items(user)

        notifications = list(Notification.objects.filter(recipient=user)[:50])
        unread_count = sum(1 for n in notifications if not n.is_read)

        my_docs = list(
            ApprovalProcess.objects
            .filter(processes_for_user_q(user))
            .exclude(status=ApprovalProcess.STATUS_CANCELLED)
            .select_related("rkd", "route", "content_type")
            .distinct()[:50]
        )
        for p in my_docs:
            doc = get_document_from_process(p)
            cfg = get_config_for_process(p)
            p.doc_ctx = {
                "type_label": cfg.label if cfg else "Документ",
                "title": cfg.get_title(doc) if cfg and doc else str(p),
                "admin_url": cfg.get_admin_url(doc) if cfg and doc else "",
            }

        context = {
            **self.admin_site.each_context(request),
            "title": 'Личный кабинет сотрудника ООО "Система"',
            "sign_tasks": sign_tasks,
            "ack_tasks": ack_tasks,
            "fix_tasks": fix_tasks,
            "my_work": my_work,
            "my_work_groups": my_work_groups,
            "my_work_active_count": my_work_active_count,
            "my_subtasks": my_subtasks,
            "my_subtasks_groups": my_subtasks_groups,
            "my_subtasks_active_count": my_subtasks_active_count,
            "assigned_items": assigned_items,
            "issued_work": issued_work,
            "issued_work_groups": issued_work_groups,
            "issued_work_active": issued_work_active,
            "my_docs": my_docs,
            "notifications": notifications,
            "unread_count": unread_count,
            "today": timezone.localdate(),
            "opts": self.model._meta,
            "my_profile": my_profile,
            "my_profile_form": my_profile_form,
        }
        return render(request, "admin/approvals/cabinet.html", context)

    def subtask_status_view(self, request, pk):
        """Перенос карточки подзадачи между статусами: рабочие статусы двигает
        исполнитель, закрыть в "Выполнено" может только автор."""
        from blog.models import WorkAssignment, WorkAssignmentSubtask

        if request.method != "POST":
            return HttpResponse(status=405)

        subtask = get_object_or_404(WorkAssignmentSubtask, pk=pk)
        new_status = request.POST.get("status")
        active = (
            WorkAssignment.STATUS_ASSIGNED,
            WorkAssignment.STATUS_IN_PROGRESS,
            WorkAssignment.STATUS_RESCHEDULE_PENDING,
            WorkAssignment.STATUS_REVIEW,
        )
        if subtask.control_status not in active:
            return JsonResponse({"ok": False, "error": "Недопустимый статус"}, status=400)

        if new_status == "done":
            if request.user.id != subtask.author_id:
                return JsonResponse(
                    {"ok": False, "error": "Закрыть подзадачу может только её автор."},
                    status=403,
                )
            result_status = "rescheduled" if subtask.reschedule_count else "on_time"
            subtask.control_status = result_status
            subtask.result = (
                "Выполнено с переносом сроков" if subtask.reschedule_count else "Выполнено в срок"
            )
            subtask.save(update_fields=["control_status", "control_date", "result"])
            return JsonResponse({"ok": True})

        if request.user.id != subtask.executor_id:
            return JsonResponse(
                {"ok": False, "error": "Перенести подзадачу может только её исполнитель."},
                status=403,
            )
        if new_status not in active:
            return JsonResponse({"ok": False, "error": "Недопустимый статус"}, status=400)

        subtask.control_status = new_status
        subtask.save(update_fields=["control_status", "control_date"])
        return JsonResponse({"ok": True})

    def my_profile_save_view(self, request):
        from shared_repository.models import EmployeeProfile

        if request.method != "POST":
            return redirect(f"{reverse('admin:approvals_cabinet')}?tab=profile")

        user = request.user
        profile, _ = EmployeeProfile.objects.get_or_create(user=user)
        form = MyProfileForm(request.POST, request.FILES, initial={"avatar": profile.avatar})
        if form.is_valid():
            user.first_name = form.cleaned_data["first_name"]
            user.last_name = form.cleaned_data["last_name"]
            user.email = form.cleaned_data["email"]
            user.save(update_fields=["first_name", "last_name", "email"])

            profile.patronymic = form.cleaned_data["patronymic"]
            profile.birth_date = form.cleaned_data["birth_date"]
            profile.phone = form.cleaned_data["phone"]
            avatar = form.cleaned_data.get("avatar")
            if avatar is False:
                profile.avatar = None
            elif avatar:
                profile.avatar = avatar
            profile.save()
            messages.success(request, "Профиль обновлён.")
        else:
            messages.error(request, "Не удалось сохранить профиль: проверьте поля формы.")
        return redirect(f"{reverse('admin:approvals_cabinet')}?tab=profile")

    def user_profile_view(self, request, user_id):
        from django.contrib.auth import get_user_model
        from shared_repository.models import EmployeeProfile

        profile_user = get_object_or_404(get_user_model(), pk=user_id)
        profile, _ = EmployeeProfile.objects.get_or_create(user=profile_user)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Карточка сотрудника — {profile_user.get_full_name() or profile_user.username}",
            "profile_user": profile_user,
            "viewed_profile": profile,
            "is_own_profile": profile_user.pk == request.user.pk,
            "opts": self.model._meta,
        }
        return render(request, "admin/approvals/cabinet.html", context)

    def notification_open_view(self, request, pk):
        n = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if not n.is_read:
            n.is_read = True
            n.save(update_fields=["is_read"])
        return redirect(n.url or reverse("admin:approvals_cabinet"))

    def notifications_read_all_view(self, request):
        if request.method == "POST":
            Notification.objects.filter(
                recipient=request.user, is_read=False
            ).update(is_read=True)
        return redirect(reverse("admin:approvals_cabinet"))

    def notifications_clear_all_view(self, request):
        if request.method == "POST":
            deleted, _ = Notification.objects.filter(recipient=request.user).delete()
            if deleted:
                self.message_user(request, f"Удалено уведомлений: {deleted}.")
        return redirect(reverse("admin:approvals_cabinet"))

    def _get_task_guarded(self, request, pk):
        task = get_object_or_404(ApprovalTask, pk=pk)
        if not is_approval_admin_or_assignee(request, task):
            raise PermissionDenied
        return task

    def _back_url(self):
        return reverse("admin:approvals_approvaltask_changelist")

    def approve_view(self, request, pk):
        task = self._get_task_guarded(request, pk)
        if (
            task.kind == ApprovalTask.KIND_REVIEW
            and task.status == ApprovalTask.STATUS_PENDING
        ):
            return redirect(reverse("admin:approvals_task_sign", args=[pk]))
        return redirect(self._back_url())

    def resubmit_view(self, request, pk):
        task = self._get_task_guarded(request, pk)
        if request.method == "POST":
            try:
                ApprovalEngine.resubmit(task, request.user)
                self.message_user(request, "Документ отправлен на повторную проверку.")
            except ValueError as e:
                self.message_user(request, str(e), level=messages.ERROR)
            return redirect(self._back_url())
        context = {
            **self.admin_site.each_context(request),
            "title": "Отправить на доработку",
            "message": f"Отправить исправленный документ «{task_doc_context(task)['title']}» "
                       f"на повторную проверку в роль «{task.department}»?",
            "action_url": request.path,
            "back_url": self._back_url(),
            "opts": self.model._meta,
        }
        return render(request, "admin/approvals/confirm_action.html", context)

    def reject_view(self, request, pk):
        task = self._get_task_guarded(request, pk)
        if request.method == "POST":
            form = RejectTaskForm(request.POST)
            if form.is_valid():
                try:
                    ApprovalEngine.reject(task, request.user, form.cleaned_data["comment"])
                    self.message_user(request, "Задача отклонена, автор получил замечание.")
                except ValueError as e:
                    self.message_user(request, str(e), level=messages.ERROR)
                return redirect(self._back_url())
        else:
            form = RejectTaskForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Отклонить с замечанием",
            "form": form,
            "task": task,
            "doc_ctx": task_doc_context(task),
            "back_url": self._back_url(),
            "opts": self.model._meta,
        }
        return render(request, "admin/approvals/reject_task.html", context)

    def sign_view(self, request, pk):
        from .sign_utils import SignDocumentError, get_main_document

        task = self._get_task_guarded(request, pk)

        if task.status != ApprovalTask.STATUS_PENDING:
            self.message_user(request, "Задача уже обработана.", level=messages.WARNING)
            return redirect(reverse("admin:approvals_cabinet"))

        is_ack = task.step and task.step.action_type == ApprovalRouteStep.ACTION_ACK

        try:
            document, doc_cfg, main_doc = get_main_document(task.process)
            sign_filename = main_doc.name.rsplit("/", 1)[-1]
        except SignDocumentError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return redirect(reverse("admin:approvals_cabinet"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Ознакомление с документом (ЭЦП)" if is_ack else "Подписание документа (ЭЦП)",
            "task": task,
            "document": document,
            "doc_type_label": doc_cfg.label,
            "doc_title": doc_cfg.get_title(document),
            "doc_subtitle": doc_cfg.get_subtitle(document),
            "doc_file_url": doc_cfg.get_file_url(document),
            "doc_admin_url": doc_cfg.get_admin_url(document),
            "is_ack": is_ack,
            "content_url": reverse("admin:approvals_task_sign_content", args=[pk]),
            "submit_url": reverse("admin:approvals_task_sign_submit", args=[pk]),
            "back_url": reverse("admin:approvals_cabinet"),
            "reject_url": reverse("admin:approvals_task_reject", args=[pk]),
            "sign_filename": sign_filename,
            "opts": self.model._meta,
        }
        return render(request, "admin/approvals/sign_document.html", context)

    def sign_content_view(self, request, pk):
        from .sign_utils import SignDocumentError, get_main_document, read_sign_document_bytes

        task = self._get_task_guarded(request, pk)
        try:
            data = read_sign_document_bytes(task)
        except SignDocumentError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        _, doc_cfg, doc = get_main_document(task.process)
        filename = doc.name.rsplit("/", 1)[-1]
        content_b64 = base64.b64encode(data).decode("ascii")
        return JsonResponse({
            "content_b64": content_b64,
            "description": f"{doc_cfg.label}: {doc_cfg.get_title(task.process.get_document())}",
            "filename": filename,
            "size": len(data),
        })

    def sign_submit_view(self, request, pk):
        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "Метод не поддерживается."}, status=405)

        task = self._get_task_guarded(request, pk)

        if task.status != ApprovalTask.STATUS_PENDING:
            return JsonResponse({"ok": False, "error": "Задача уже обработана."}, status=400)

        is_ack = task.step and task.step.action_type == ApprovalRouteStep.ACTION_ACK

        sig_b64 = (request.POST.get("signature") or "").strip()
        if not sig_b64:
            return JsonResponse({"ok": False, "error": "Подпись не передана."}, status=400)

        try:
            from .sign_utils import SignDocumentError, read_sign_document_bytes
            read_sign_document_bytes(task)
        except SignDocumentError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        try:
            from .sign_utils import parse_cms_signature
            cert_info = parse_cms_signature(sig_b64)
        except (ValueError, ImportError) as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        from .sign_utils import save_task_signature

        save_task_signature(task, sig_b64, cert_info=cert_info)

        try:
            ApprovalEngine.approve(task, request.user, cert_info=cert_info)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        return JsonResponse({
            "ok": True,
            "message": (
                f"Ознакомление подтверждено ЭЦП. Сертификат: {cert_info.get('cn', '')}"
                if is_ack
                else f"Документ подписан ЭЦП. Сертификат: {cert_info.get('cn', '')}"
            ),
            "redirect": reverse("admin:approvals_cabinet"),
        })


def is_approval_admin_or_assignee(request, task):
    return is_approval_admin(request.user) or task.assigned_to_id == request.user.id
