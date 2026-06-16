import base64

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .admin_forms import RejectTaskForm, StartApprovalForm
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
    ApprovalRouteStep,
    ApprovalProcess,
    ApprovalTask,
    Notification,
)
from .services import ApprovalEngine


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


class _AdminOnlyMixin:
    def has_module_permission(self, request):
        return is_approval_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_approval_admin(request.user)

    def has_add_permission(self, request):
        return is_approval_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_approval_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_approval_admin(request.user)


class DepartmentMemberInline(admin.TabularInline):
    model = DepartmentMember
    extra = 1
    autocomplete_fields = ("user",)
    verbose_name = "Сотрудник отдела"
    verbose_name_plural = "Сотрудники (главный + заместители по очереди)"


@admin.register(Department)
class DepartmentAdmin(_AdminOnlyMixin, admin.ModelAdmin):
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
class VacationAdmin(_AdminOnlyMixin, admin.ModelAdmin):
    list_display = ("user", "start_date", "end_date", "reason")
    list_filter = ("start_date", "end_date")
    search_fields = ("user__username", "user__last_name", "reason")
    autocomplete_fields = ("user",)


class ApprovalRouteStepInline(admin.TabularInline):
    model = ApprovalRouteStep
    extra = 1
    verbose_name = "Шаг маршрута"
    verbose_name_plural = "Шаги маршрута (по порядку)"


@admin.register(ApprovalRoute)
class ApprovalRouteAdmin(_AdminOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "steps_preview", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    inlines = [ApprovalRouteStepInline]

    @admin.display(description="Маршрут")
    def steps_preview(self, obj):
        steps = obj.steps.select_related("department").order_by("order")
        if not steps:
            return "—"
        return " → ".join(str(s.department) for s in steps)


class ApprovalTaskInline(admin.TabularInline):
    model = ApprovalTask
    extra = 0
    can_delete = False
    fields = (
        "kind", "department", "assigned_to", "status", "is_recheck",
        "eds_info", "eds_download", "comment", "created_at", "resolved_at",
    )
    readonly_fields = fields
    verbose_name = "Задача"
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
            "<th style='padding:8px;border:1px solid #ccc;text-align:left;'>Отдел</th>"
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
            form = StartApprovalForm(request.POST)
            if form.is_valid():
                route = form.cleaned_data["route"]
                started, errors = 0, []
                for document in documents:
                    try:
                        ApprovalEngine.start(document, route, request.user)
                        started += 1
                    except ValueError as e:
                        errors.append(f"{document}: {e}")
                if started:
                    self.message_user(request, f"Запущено согласований: {started}.")
                for err in errors:
                    self.message_user(request, err, level=messages.ERROR)
                return redirect("admin:approvals_approvalprocess_changelist")
        else:
            form = StartApprovalForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Отправить на согласование — {cfg.label}",
            "form": form,
            "documents": documents,
            "doc_type": doc_type,
            "doc_type_label": cfg.label,
            "ids": raw_ids,
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

        from blog.models import WorkAssignment

        user = request.user
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

        my_work = list(
            WorkAssignment.objects
            .filter(executor=user)
            .filter(Q(control_status__isnull=True) | Q(control_status="in_progress"))
            .select_related("post")
            .order_by("target_deadline")
        )

        issued_work_qs = (
            WorkAssignment.objects
            .filter(author=user)
            .annotate(subtask_total=Count("subtasks"))
            .select_related("executor", "post", "current_responsible")
            .order_by("-date_of_creation")
        )
        issued_work = list(issued_work_qs[:50])
        issued_work_active = issued_work_qs.filter(
            Q(control_status__isnull=True) | Q(control_status="in_progress")
        ).count()

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
            "title": "Личный кабинет",
            "sign_tasks": sign_tasks,
            "ack_tasks": ack_tasks,
            "fix_tasks": fix_tasks,
            "my_work": my_work,
            "issued_work": issued_work,
            "issued_work_active": issued_work_active,
            "my_docs": my_docs,
            "notifications": notifications,
            "unread_count": unread_count,
            "today": timezone.localdate(),
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
                       f"на повторную проверку в отдел «{task.department}»?",
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
