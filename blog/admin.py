from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper, AdminDateWidget
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from datetime import timedelta
from django.utils.html import escape, format_html
from django.template.defaultfilters import linebreaksbr
from django.utils.safestring import mark_safe
import re
from django.db.models import Q, F, Value , TextField, DateField, BooleanField, Case, When, IntegerField
from django.db.models.functions import Cast
from functools import reduce
from operator import and_, or_
from django.forms.models import BaseInlineFormSet
from django.forms import ValidationError
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.contenttypes.forms import BaseGenericInlineFormSet
from crm.models import (
    Notifications,
    Customer,
    Decision_maker,
    Deal,
    Product,
    Deal_stage,
    Call,
    Company_branch,
    Meeting,
    MeetingFile,
    SupportTicket,
    TicketComment,
    IncomingLetter,
    OutgoingLetter,
)
from crm.forms import TicketCommentForm, SupportTicketForm
from enterprise_asset_management.models import (
    WorkEquipment,
    WorkEquipmentFile,
    WorkEquipmentRepair,
    WorkEquipmentRepairFile,
    TransportVehicle,
    ProductionArea,
    ProductionAreaFile,
    TransportVehicleFile,
    TransportRepair,
    TransportRepairFile,
    ProductionAreaLocation,
)
from shared_repository.models import (SharedRepository, IndependentDocumentAcceptSignature,
KnowledgeBase, KnowledgeBaseFile, QMSDocument,QMSDocumentAcceptSignature, AdministrativeOrder,
AdministrativeOrderAcceptSignature, DocumentTemplate, DocumentTemplateAcceptSignature)

from .models import (PSIDocument, GeneratedDocument, DocumentHistory, PAKDocument, PAKGeneratedDocument, PAKDocumentHistory)

from .admin_forms import (
    RescheduleAdminForm,
    WorkAssignmentAdminForm,
    WorkAssignmentCloseForm,
    WorkAssignmentRescheduleRequestForm,
    WorkAssignmentReturnForm,
    WorkAssignmentSubmitReviewForm,
)
from .forms import WorkAssignmentForm, UniversalRKDForm, TechnicalProposalForm
from .helpers import (
    first_incomplete_step_code,
    next_step_code_after,
    PROCESS_FIELD_MAP,
    wf_step_is_signed,
    wf_step_responsible,
    wf_step_set_comment,
    RKD_CATEGORY_BY_SECTION,
)
from .models import (
    AddReportTechnicalProposal,
    ApprovalDocumentWorkflow,
    CheckDocumentWorkflow,
    DrawingPartProduct,
    DrawingPartUnit,
    ElectronicModelPartProduct,
    ElectronicModelPartUnit,
    ElectronicModelProduct,
    ElectronicModelUnit,
    GeneralDrawingProduct,
    GeneralDrawingUnit,
    GeneralElectricalDiagram,
    ListTechnicalProposal,
    Post,
    Process,
    ProductGroup,
    ProductGroupDocument,
    ProtocolTechnicalProposal,
    ReportTechnicalProposal,
    Route,
    RouteProcess,
    SoftwareProduct,
    TechnicalProposalDocument,
    TaskForDesignWork,
    RevisionTask,
    WorkAssignment,
    WorkAssignmentSubtask,
    WorkAssignmentDeadlineChange,
    Attachment,
    UniversalRKD,
    UniversalRKDSignature,
    RKDDeveloper,
    RKDDeveloperAdditionalFile,
    Shipment,
    ShipmentAdditionalFile,
)
from .services import WorkAssignmentService

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import User
from shared_repository.models import Department, EmployeeProfile


def _inject_rkd_category_json(extra_context):
    extra_context = extra_context or {}
    extra_context["rkd_category_by_section_dict"] = {
        k: list(v) for k, v in RKD_CATEGORY_BY_SECTION.items()
    }
    return extra_context


def _admin_warning_triangle_html(*, title: str, color: str = "#f0ad4e") -> str:
    t = escape(title)
    return (
        f'<span title="{t}" style="display:inline-flex;align-items:center;">'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        f'viewBox="0 0 24 24" aria-hidden="true" focusable="false" style="vertical-align: -2px;">'
        f'<path d="M1 21h22L12 2 1 21z" fill="{color}"></path>'
        f'<rect x="11" y="9" width="2" height="6" fill="#111"></rect>'
        f'<rect x="11" y="17" width="2" height="2" fill="#111"></rect>'
        f"</svg>"
        f"</span>"
    )


def _admin_lu_lo_sheets_column_html(obj) -> str:
    """Ссылки на сгенерированные листы утверждения и ознакомления."""
    parts = []
    approval = getattr(obj, "approval_document", None)
    if approval:
        parts.append(
            format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">Лист утверждения</a>',
                approval.url,
            )
        )
    acquaintance = getattr(obj, "acquaintance_document", None)
    if acquaintance:
        parts.append(
            format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">Лист ознакомления</a>',
                acquaintance.url,
            )
        )
    if not parts:
        return "—"
    return mark_safe("<br>".join(str(p) for p in parts))


def _universal_rkd_planned_review_show_warning(validity_date, *, days: int) -> bool:
    if not validity_date:
        return False
    d = int(days or 0)
    if d < 0:
        d = 0
    today = timezone.now().date()
    return (validity_date - today).days <= d


def _file_link_marker(file_field) -> str:
    """Сериализует FileField в маркер для последующего рендера ссылкой.

    Формат: [имя_файла](url) — парсится в `_render_version_diff`.
    Если файла нет, возвращает «—».
    """
    if not file_field:
        return "—"
    try:
        url = file_field.url
    except Exception:
        return "—"
    name = file_field.name.rsplit("/", 1)[-1] if file_field.name else "файл"
    return f"[{name}]({url})"


def _build_version_diff_block(*, old_obj, new_obj, model_cls, skip_fields,
                              user, version_to: str) -> str:
    """Строит блок изменений между `old_obj` и `new_obj` по полям модели.

    Возвращает текст блока вида:
        ─── Версия N (DD.MM.YYYY HH:MM, ФИО) ───
        - Поле: «старое» → «новое»
        - Файл: предыдущий [name.pdf](url) → [new.pdf](url)
    Если изменений нет — возвращает пустую строку.
    """
    diff_parts = []
    for field in model_cls._meta.concrete_fields:
        if field.name in skip_fields:
            continue
        if field.is_relation:
            old_pk = getattr(old_obj, field.attname, None)
            new_pk = getattr(new_obj, field.attname, None)
            if old_pk == new_pk:
                continue
            try:
                old_disp = str(field.related_model.objects.get(pk=old_pk)) if old_pk else "—"
            except Exception:
                old_disp = str(old_pk) if old_pk else "—"
            try:
                new_disp = str(field.related_model.objects.get(pk=new_pk)) if new_pk else "—"
            except Exception:
                new_disp = str(new_pk) if new_pk else "—"
            diff_parts.append(f"- {field.verbose_name}: «{old_disp}» → «{new_disp}»")
            continue
        if getattr(field, "upload_to", None) is not None:
            old_file = getattr(old_obj, field.name, None)
            new_file = getattr(new_obj, field.name, None)
            old_name = old_file.name if old_file else ""
            new_name = new_file.name if new_file else ""
            if old_name == new_name:
                continue
            diff_parts.append(
                f"- {field.verbose_name}: предыдущий {_file_link_marker(old_file)} "
                f"→ {_file_link_marker(new_file)}"
            )
            continue
        old_val = getattr(old_obj, field.name, None)
        new_val = getattr(new_obj, field.name, None)
        if str(old_val) != str(new_val):
            old_disp = old_val if old_val not in (None, "") else "—"
            new_disp = new_val if new_val not in (None, "") else "—"
            if field.choices:
                choices_map = dict(field.choices)
                old_disp = choices_map.get(old_val, old_disp)
                new_disp = choices_map.get(new_val, new_disp)
            diff_parts.append(f"- {field.verbose_name}: «{old_disp}» → «{new_disp}»")

    if not diff_parts:
        return ""

    user_name = ""
    if user is not None:
        user_name = user.get_full_name() or user.get_username() or ""
    ts = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")
    header_parts = [f"Версия {version_to}", ts]
    if user_name:
        header_parts.append(user_name)
    header = f"─── {' · '.join(header_parts)} ───"
    return header + "\n" + "\n".join(diff_parts)


_FILE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _render_version_diff(text: str) -> str:
    """Преобразует сохранённый текст истории версий в HTML."""
    if not text:
        return "—"
    escaped = escape(text)
    escaped = _FILE_LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>',
        escaped,
    )
    return escaped.replace("\n", "<br>")


_WA_STATUS_CIRCLE = {
    'assigned':    ('#FFA000', None,      'Ожидает принятия'),
    'in_progress': ('#2196F3', None,      'В работе'),
    'review':      ('#00BCD4', None,      'На проверке'),
    'on_time':     ('#4CAF50', None,      'Выполнено в срок'),
    'rescheduled': ('#4CAF50', '#FF9800', 'Выполнено с переносом сроков'),
    'partial':     ('#9C27B0', None,      'Выполнено частично'),
    'not_done':    ('#9E9E9E', None,      'Не выполнено (Отменено)'),
}


def _render_status_circle(status):
    if not status:
        return "—"
    color1, color2, label = _WA_STATUS_CIRCLE.get(status, ('#cccccc', None, status))
    bg = f"conic-gradient({color1} 50%, {color2} 50%)" if color2 else color1
    return format_html(
        '<span style="display:inline-flex;align-items:center;gap:6px;">'
        '<span style="width:10px;height:10px;border-radius:50%;'
        'background:{};flex-shrink:0;display:inline-block;"></span>'
        '{}</span>',
        bg, label,
    )


_WA_RESULT_TEXT = {
    "on_time": "Выполнено в срок",
    "rescheduled": "Выполнено с переносом сроков",
    "partial": "Выполнено частично",
    "not_done": "Не выполнено",
}


class RequiredFileGenericFormSet(BaseGenericInlineFormSet):
    parent_status_field = "status"
    required_status_labels = ("Зарегистрирован",)
    attachment_file_field = "file"

    def _required_values(self):
        field = self.instance._meta.get_field(self.parent_status_field)
        choices = getattr(field, "choices", ()) or ()
        labels = {s.strip().lower() for s in self.required_status_labels}
        return {v for v, lbl in choices if str(lbl).strip().lower() in labels}

    def clean(self):
        super().clean()
        status = getattr(self.instance, self.parent_status_field, None) or self.data.get(self.parent_status_field)
        need = False
        if status is not None:
            need = status in self._required_values() or str(status).strip().lower() in {
                s.strip().lower() for s in self.required_status_labels
            }
        if not need:
            return
        ffield = self.attachment_file_field
        for form in self.forms:
            if getattr(form, "cleaned_data", None) and not form.cleaned_data.get("DELETE"):
                f = form.cleaned_data.get(ffield) or getattr(form.instance, ffield, None)
                if f:
                    return
        raise ValidationError("При статусе «Зарегистрирован» добавьте хотя бы один файл.")

class AttachmentInline(GenericTabularInline):
    model = Attachment
    formset = RequiredFileGenericFormSet
    extra = 1
    fields = ("file",)


class WorkAssignmentAttachmentInline(AttachmentInline):
    verbose_name = "файл"
    verbose_name_plural = "Вложения"

    def _wa_locked(self, obj):
        return obj is not None and obj.control_status in WorkAssignment.TERMINAL_STATUSES

    def has_add_permission(self, request, obj=None):
        if self._wa_locked(obj):
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if self._wa_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._wa_locked(obj):
            return False
        return super().has_delete_permission(request, obj)


def _tp_docs_section_header(title: str):
    return mark_safe(
        '<div style="'
        "margin: 0 0 10px 0;"
        "padding: 10px 14px;"
        "font-weight: 700;"
        "font-size: 13px;"
        "letter-spacing: 0.4px;"
        "text-transform: uppercase;"
        "border-left: 4px solid var(--primary, #79aec8);"
        "background: var(--darkened-bg, rgba(121,174,200,0.12));"
        "color: var(--body-fg, inherit);"
        "border-radius: 3px;"
        f'">{escape(title)}</div>'
    )


@admin.register(TechnicalProposalDocument)
class TechnicalProposalDocumentAdmin(admin.ModelAdmin):
    change_form_template = "admin/blog/technicalproposaldocument/change_form.html"
    change_list_template = "admin/blog/technicalproposaldocument/change_list.html"
    form = TechnicalProposalForm

    list_display = (
        "tp_post_column",
        "tp_document_kind",
        "category",
        "desig_document",
        "name",
        "tp_documents_column",
        "status",
    )
    list_display_links = ("name",)
    list_filter = ("document_kind", "status", "post")
    search_fields = ("name", "desig_document", "category", "post__name")

    @admin.display(description="Разработка (модификация)", ordering="post")
    def tp_post_column(self, obj):
        return obj.post or "—"

    @admin.display(description="Вид документа ПТ", ordering="document_kind")
    def tp_document_kind(self, obj):
        return obj.get_document_kind_display() or "—"

    @admin.display(description="Документ")
    def tp_documents_column(self, obj):
        parts = []
        if obj.document_uploaded_file:
            parts.append(
                format_html(
                    '<a href="{}" target="_blank" rel="noopener noreferrer">Документ</a>',
                    obj.document_uploaded_file.url,
                )
            )
        if obj.approval_document:
            parts.append(
                format_html(
                    '<a href="{}" target="_blank" rel="noopener noreferrer">Лист утверждения</a>',
                    obj.approval_document.url,
                )
            )
        if obj.attestation_document:
            parts.append(
                format_html(
                    '<a href="{}" target="_blank" rel="noopener noreferrer">Удостоверяющий лист</a>',
                    obj.attestation_document.url,
                )
            )
        if not parts:
            return "—"
        return mark_safe("<br>".join(str(p) for p in parts))

    autocomplete_fields = (
        "post",
        "author",
        "last_editor",
        "current_responsible",
        "checked_by",
        "approved_by",
        "develop_org",
    )
    readonly_fields = (
        "date_of_creation",
        "date_of_change",
        "tp_display_files_list",
    )

    fieldsets = (
        (
            "Разработка и классификация",
            {
                "fields": (
                    "post",
                    "document_kind",
                    "category",
                    "name",
                    "desig_document",
                    "litera",
                    "trl",
                )
            },
        ),
        (
            "Содержание и статус",
            {
                "fields": (
                    "info_format",
                    "status",
                    "related_documents",
                    "develop_org",
                )
            },
        ),
        (
            None,
            {
                "description": _tp_docs_section_header("Основной документ"),
                "fields": (
                    "document_uploaded_file",
                    "document_source",
                ),
            },
        ),
        (
            None,
            {
                "description": _tp_docs_section_header("Лист утверждения"),
                "fields": (
                    "approval_document",
                    "approval_source",
                ),
            },
        ),
        (
            None,
            {
                "description": _tp_docs_section_header("Удостоверяющий лист"),
                "fields": (
                    "attestation_document",
                    "attestation_source",
                ),
            },
        ),
        (
            "Согласование",
            {
                "fields": (
                    "checked_by",
                    "signature_checked",
                    "approved_by",
                    "signature_approved",
                )
            },
        ),
        (
            "Дополнительно",
            {
                "fields": (
                    "comment",
                )
            },
        ),
        (
            "Ответственные",
            {
                "fields": (
                    "author",
                    "current_responsible",
                    "last_editor",
                    "version",
                    "date_of_creation",
                    "date_of_change",
                )
            },
        ),
        (
            "Файлы документа",
            {
                "fields": ("tp_display_files_list",),
            },
        ),
    )

    @admin.display(description="Файлы документа")
    def tp_display_files_list(self, obj):
        card_style = (
            "border: 1px solid var(--hairline-color, #e1e4e8);"
            "border-radius: 6px;"
            "background: var(--body-bg, #fff);"
            "padding: 14px 16px;"
            "max-width: 920px;"
        )
        section_title = (
            "margin: 16px 0 8px 0;"
            "font-size: 12px;"
            "font-weight: 600;"
            "letter-spacing: 0.02em;"
            "text-transform: uppercase;"
            "color: var(--body-quiet-color, #6b7280);"
        )
        row_base = "display:flex; gap:12px; align-items:flex-start; padding:8px 0;"
        row_sep = "border-bottom: 1px solid var(--hairline-color, #eef0f3);"
        label_style = "width: 260px; flex: 0 0 260px; color: var(--body-fg, #111); font-weight: 500;"
        value_style = "flex: 1; min-width: 0; word-break: break-word;"
        muted = "color: var(--body-quiet-color, #6b7280);"
        link_style = "color: var(--link-fg, #417690); text-decoration: none;"

        if not obj or not getattr(obj, "pk", None):
            return format_html(
                '<div style="{}">'
                '<div style="{}">Сводка по файлам</div>'
                '<div style="{}">После первого сохранения записи здесь появятся ссылки на загруженные файлы.</div>'
                "</div>",
                card_style,
                section_title,
                muted,
            )

        def _basename(f):
            name = getattr(f, "name", "") or ""
            return name.rsplit("/", 1)[-1] or name

        def _row(label, f, *, with_sep, uploaded_by=None, uploaded_at=None):
            row_style = row_base + (row_sep if with_sep else "")
            label_html = f'<div style="{label_style}">{escape(label)}</div>'
            if not f:
                return f'<div style="{row_style}">{label_html}<div style="{value_style} {muted}">не загружен</div></div>'
            url = getattr(f, "url", "") or ""
            filename = escape(_basename(f))
            if url:
                value = f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer" style="{link_style}">{filename}</a>'
            else:
                value = f'<span style="{muted}">{filename}</span>'
            if uploaded_by and uploaded_at:
                value += (
                    f'<div style="margin-top:6px;font-size:12px;{muted}">'
                    f"изменил: {escape(uploaded_by.get_username())} · "
                    f"{escape(uploaded_at.strftime('%d.%m.%Y %H:%M'))}"
                    f"</div>"
                )
            elif uploaded_by:
                value += (
                    f'<div style="margin-top:6px;font-size:12px;{muted}">'
                    f"изменил: {escape(uploaded_by.get_username())}"
                    f"</div>"
                )
            return f'<div style="{row_style}">{label_html}<div style="{value_style}">{value}</div></div>'

        last_editor = getattr(obj, "last_editor", None) or getattr(obj, "author", None)
        changed_at = getattr(obj, "date_of_change", None)

        html = f'<div style="{card_style}">'
        html += f'<div style="{section_title}">Документы</div>'
        html += _row("Документ — итоговый", getattr(obj, "document_uploaded_file", None), with_sep=True, uploaded_by=last_editor, uploaded_at=changed_at)
        html += _row("Документ — исходник", getattr(obj, "document_source", None), with_sep=True, uploaded_by=last_editor, uploaded_at=changed_at)
        html += _row("Лист утверждения — итоговый (PDF)", getattr(obj, "approval_document", None), with_sep=True, uploaded_by=last_editor, uploaded_at=changed_at)
        html += _row("Лист утверждения — исходник (DOCX)", getattr(obj, "approval_source", None), with_sep=True, uploaded_by=last_editor, uploaded_at=changed_at)
        html += _row("Удостоверяющий лист — итоговый (PDF)", getattr(obj, "attestation_document", None), with_sep=True, uploaded_by=last_editor, uploaded_at=changed_at)
        html += _row("Удостоверяющий лист — исходник (DOCX)", getattr(obj, "attestation_source", None), with_sep=False, uploaded_by=last_editor, uploaded_at=changed_at)
        html += f'<div style="{section_title}">Подписи</div>'
        html += _row("Подпись проверки", getattr(obj, "signature_checked", None), with_sep=True, uploaded_by=last_editor, uploaded_at=changed_at)
        html += _row("Подпись утверждения", getattr(obj, "signature_approved", None), with_sep=False, uploaded_by=last_editor, uploaded_at=changed_at)
        html += "</div>"
        return mark_safe(html)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "post",
            "develop_org",
            "author",
            "last_editor",
            "current_responsible",
            "checked_by",
            "approved_by",
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        post_id = request.GET.get("post__id__exact")
        if post_id:
            extra_context["tp_breadcrumb_post"] = Post.objects.filter(pk=post_id).first()
        return super().changelist_view(request, extra_context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = dict(extra_context or {})
        if object_id:
            obj = self.get_object(request, unquote(object_id))
            if obj is not None:
                if obj.post_id:
                    extra_context["tp_breadcrumb_post"] = obj.post
                extra_context["tp_breadcrumb_record_title"] = str(obj)
        else:
            post_q = request.GET.get("post")
            if post_q:
                extra_context["tp_breadcrumb_post"] = Post.objects.filter(pk=post_q).first()
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

    _PDF_FILE_FIELDS = {
        "approval_document",
        "attestation_document",
    }
    _DOCX_FILE_FIELDS = {
        "approval_source",
        "attestation_source",
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is None:
            return formfield
        name = db_field.name
        if name in self._PDF_FILE_FIELDS:
            formfield.widget.attrs.setdefault("accept", ".pdf,application/pdf")
        elif name in self._DOCX_FILE_FIELDS:
            formfield.widget.attrs.setdefault(
                "accept",
                ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        return formfield

class ListTechnicalProposalInline(admin.TabularInline):
    model = ListTechnicalProposal
    extra = 1
    can_delete = True

    def has_add_permission(self, request, obj=None):
        if obj and ListTechnicalProposal.objects.filter(post=obj).count() >= 1:
            return False
        return True


class TaskForDesignWorkInline(admin.TabularInline):
    model = TaskForDesignWork
    extra = 1

class RevisionTaskInline(admin.TabularInline):
    model = RevisionTask
    extra = 1

class WorkAssignmentInline(admin.TabularInline):
    model = WorkAssignment
    extra = 0
    readonly_fields = ("wa_code_inline",)
    fields = (
        "wa_code_inline",
        "name",
        "category",
        "executor",
        "author",
        "date_of_creation",
        "last_editor",
        "current_responsible",
        "version",
        "task",
        "target_deadline",
    )
    show_change_link = True

    @admin.display(description="Код")
    def wa_code_inline(self, obj):
        return obj.wa_full_code or "—"

    def get_extra_buttons(self, obj):
        if obj and obj.id:
            url = reverse("admin:blog_workassignment_add") + f"?post={obj.id}"
            return format_html(
                '<a class="button" href="{}">➕ Добавить рабочее задание</a>', url
            )
        return ""

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj and obj.id:
            return [
                (
                    f"Рабочие задания {self.get_extra_buttons(obj)}",
                    {"fields": self.fields},
                )
            ]
        return fieldsets


class UniversalRKDInline(admin.TabularInline):
    model = UniversalRKD
    form = UniversalRKDForm
    extra = 0
    show_change_link = True
    fields = (
        "specification_section",
        "position",
        "category",
        "desig_document",
        "name",
        "status",
    )


class ShipmentAdditionalFileInline(admin.TabularInline):
    model = ShipmentAdditionalFile
    extra = 1
    fields = ("file",)


class ShipmentInline(admin.TabularInline):
    model = Shipment
    extra = 0
    show_change_link = True
    fields = (
        "serial_number",
        "manufacture_date",
        "manufacturer_org",
        "supplier_org",
        "product_passport",
        "shipment_date",
        "buyer",
        "recipient",
        "note",
    )
    autocomplete_fields = ("buyer", "recipient", "manufacturer_org", "supplier_org")


class ProductGroupDocumentInline(admin.TabularInline):
    model = ProductGroupDocument
    extra = 0
    fields = ("title", "kind", "file", "note")
    verbose_name_plural = "Документы группы"


@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    change_list_template = "admin/blog/productgroup/change_list.html"
    list_display = (
        "name",
        "designation",
        "main_purpose",
        "main_documents_column",
    )
    list_display_links = ("name",)
    search_fields = ("name", "designation", "main_purpose")
    readonly_fields = (
        "author",
        "last_editor",
        "date_of_creation",
        "date_of_change",
    )
    fieldsets = (
        (None, {
            "fields": (
                "name",
                "designation",
                "main_purpose",
            ),
        }),
        ("Сведения о записи", {
            "fields": (
                "author",
                "last_editor",
                "date_of_creation",
                "date_of_change",
            ),
        }),
    )
    inlines = (ProductGroupDocumentInline,)

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .prefetch_related("documents")
        )
        raw = request.GET.get("id__exact") or request.GET.get("pk")
        if raw is not None and str(raw).strip().isdigit():
            qs = qs.filter(pk=int(raw))
        return qs

    @admin.display(description="Общие документы (PDF)")
    def main_documents_column(self, obj):
        if not obj.pk:
            return "—"
        docs = [
            d
            for d in obj.documents.all()
            if d.kind == ProductGroupDocument.KIND_MAIN and d.file and d.file.name
        ]
        docs.sort(key=lambda x: x.pk)
        if not docs:
            return "—"
        parts = []
        for d in docs:
            parts.append(
                format_html(
                    '<div style="margin:0 0 6px 0;line-height:1.35;">'
                    '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>'
                    "</div>",
                    d.file.url,
                    escape(d.title),
                )
            )
        return mark_safe("".join(str(p) for p in parts))

    def save_model(self, request, obj, form, change):
        if request.user.is_authenticated:
            if not change or obj.author_id is None:
                obj.author = request.user
            obj.last_editor = request.user
        super().save_model(request, obj, form, change)


class PostAdminForm(forms.ModelForm):
    shipments_selector = forms.ModelMultipleChoiceField(
        queryset=Shipment.objects.none(),
        required=False,
        label="Изделия к отгрузке",
    )

    class Meta:
        model = Post
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        current_post_id = instance.pk if instance and instance.pk else None

        qs = Shipment.objects.select_related("post").order_by("-date_of_creation", "-id")
        if current_post_id:
            # Показываем только уже привязанные к этой разработке отгрузки.
            qs = qs.filter(post_id=current_post_id)
            self.initial["shipments_selector"] = list(
                Shipment.objects.filter(post_id=current_post_id).values_list("pk", flat=True)
            )
            self.fields["shipments_selector"].help_text = (
                "Здесь отображаются отгрузки, уже привязанные к этой разработке."
            )
        else:
            qs = qs.none()
            self.fields["shipments_selector"].help_text = (
                "После создания разработки здесь будут появляться отгрузки, "
                "добавленные в сущности «Изделия к отгрузке» и привязанные к этой разработке."
            )
        self.fields["shipments_selector"].queryset = qs


class InProductionMonthFilter(admin.SimpleListFilter):
    title = "Постановка на производство"
    parameter_name = "prod_month"

    def lookups(self, request, model_admin):
        from django.db.models.functions import TruncMonth

        months = (
            model_admin.get_queryset(request)
            .filter(in_production=True, in_production_date__isnull=False)
            .annotate(month=TruncMonth("in_production_date"))
            .values_list("month", flat=True)
            .distinct()
            .order_by("-month")
        )
        return [("all", "Все поставленные на производство")] + [
            (d.strftime("%Y-%m"), d.strftime("%m.%Y")) for d in months
        ]

    def queryset(self, request, queryset):
        import calendar
        from datetime import date as _date

        val = self.value()
        if not val:
            return queryset
        if val == "all":
            return queryset.filter(in_production=True)
        try:
            year, month = map(int, val.split("-"))
            first = _date(year, month, 1)
            last = _date(year, month, calendar.monthrange(year, month)[1])
            return queryset.filter(
                in_production=True,
                in_production_date__gte=first,
                in_production_date__lte=last,
            )
        except (ValueError, AttributeError):
            return queryset


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    form = PostAdminForm
    change_form_template = "admin/blog/universal_rkd_category_change_form.html"
    list_display = (
        'wa_code_column',
        'name',
        'name_full',
        'desig_document_post',
        'group_modification_features_short',
        'product_group_link',
        'in_production_column',
        'author',
        'date_of_creation',
        'date_of_change',
    )
    list_display_links = ('wa_code_column', 'name')
    list_filter = ('product_group', InProductionMonthFilter)
    search_fields = ('name', 'name_full', 'desig_document_post', 'wa_code')
    autocomplete_fields = ('product_group',)
    readonly_fields = (
        'author',
        'last_editor',
        'date_of_creation',
        'date_of_change',
        'group_name_display',
        'group_designation_display',
        'group_main_purpose_display',
        'version',
        'version_diff_display',
    )
    fieldsets = (
        ("Идентификация изделия (продукта)", {
            "fields": (
                "name",
                "name_full",
                "desig_document_post",
            ),
        }),
        ("Принадлежность к группе", {
            "fields": (
                "is_group_modification",
                "product_group",
                "group_name_display",
                "group_designation_display",
                "group_main_purpose_display",
            ),
        }),
        ("Описание изделия (продукта)", {
            "fields": (
                "main_purpose_own",
                "group_modification_features",
                "order_article",
                "note",
                "group_documents",
            ),
        }),
        ("Уровень технической зрелости", {
            "fields": ("litera", "trl"),
        }),
        ("Версионирование", {
            "classes": ("collapse",),
            "fields": ("version", "version_diff_display"),
        }),
        ("Системные сведения", {
            "fields": (
                "author",
                "date_of_creation",
                "last_editor",
                "date_of_change",
                "current_responsible",
            ),
        }),
        ("Изделия к отгрузке", {
            "fields": ("shipments_selector",),
        }),
        ("Дополнительные сведения", {
            "classes": ("collapse",),
            "fields": (
                "in_production",
                "in_production_date",
                "develop_org",
                "manufacturer_org_post",
            ),
        }),
    )
    inlines = [
        TaskForDesignWorkInline,
        RevisionTaskInline,
        WorkAssignmentInline,
        UniversalRKDInline,
    ]

    @admin.display(description="Наименование группы разработок")
    def group_name_display(self, obj):
        value = (obj.product_group.name if obj and obj.product_group_id else "") or ""
        return format_html('<span id="pg_val_name">{}</span>', value or "—")

    @admin.display(description="Обозначение группы разработок")
    def group_designation_display(self, obj):
        value = (obj.product_group.designation if obj and obj.product_group_id else "") or ""
        return format_html('<span id="pg_val_designation">{}</span>', value or "—")

    @admin.display(description="Основное назначение группы разработок")
    def group_main_purpose_display(self, obj):
        value = (obj.product_group.main_purpose if obj and obj.product_group_id else "") or ""
        return format_html('<span id="pg_val_main_purpose">{}</span>', value or "—")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "product-group-data/<int:pk>/",
                self.admin_site.admin_view(self.product_group_data_view),
                name="blog_post_product_group_data",
            ),
        ]
        return custom + urls

    def product_group_data_view(self, request, pk):
        from django.http import JsonResponse
        try:
            group = ProductGroup.objects.get(pk=pk)
        except ProductGroup.DoesNotExist:
            return JsonResponse({"ok": False}, status=404)
        return JsonResponse({
            "ok": True,
            "name": group.name or "",
            "designation": group.designation or "",
            "main_purpose": group.main_purpose or "",
        })

    def get_form(self, request, obj=None, change=False, **kwargs):
        FormClass = super().get_form(request, obj, change=change, **kwargs)

        class _PostForm(FormClass):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, **form_kwargs)
                for optional_name in (
                    "name_full",
                    "desig_document_post",
                    "product_group",
                ):
                    f = self.fields.get(optional_name)
                    if f is not None:
                        f.required = False

                if not self.is_bound:
                    cr_field = self.fields.get("current_responsible")
                    if cr_field is not None:
                        current_val = self.initial.get("current_responsible") or getattr(
                            self.instance, "current_responsible_id", None
                        )
                        if not current_val:
                            self.initial["current_responsible"] = request.user.pk

                for org_field_name in ("develop_org", "manufacturer_org_post"):
                    field = self.fields.get(org_field_name)
                    if field and not self.is_bound:
                        current_name = (getattr(self.instance, org_field_name, "") or "").strip()
                        if current_name:
                            org = RKDDeveloper.objects.filter(name=current_name).only("pk").first()
                            if org:
                                self.initial[org_field_name] = str(org.pk)

        return _PostForm

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is None:
            return formfield

        if db_field.name == "order_article":
            formfield.widget.attrs.update({"style": "width: 600px;"})
            return formfield

        if db_field.name in ("develop_org", "manufacturer_org_post"):
            org_items = list(
                RKDDeveloper.objects.order_by("name").values_list("pk", "name")
            )
            choices = [("", "---------")] + [(str(pk), name) for pk, name in org_items if name]
            formfield.widget = forms.Select(choices=choices)
            formfield.choices = choices
            rel = Shipment._meta.get_field("manufacturer_org").remote_field
            formfield.widget = RelatedFieldWidgetWrapper(
                formfield.widget,
                rel,
                self.admin_site,
                can_add_related=True,
                can_change_related=True,
                can_delete_related=True,
                can_view_related=True,
            )
            formfield.help_text = ""
            return formfield

        return formfield

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = _inject_rkd_category_json(extra_context)
        extra_context = extra_context or {}
        extra_context["product_group_data_url_template"] = reverse(
            "admin:blog_post_product_group_data", args=[0]
        )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("product_group")

    @admin.display(description="Группа разработок", ordering="product_group__name")
    def product_group_link(self, obj):
        if not obj or not obj.product_group_id:
            return "—"
        url = reverse("admin:blog_productgroup_changelist") + f"?id__exact={obj.product_group_id}"
        return format_html(
            '<a href="{}">{}</a>',
            url,
            escape(obj.product_group.name),
        )

    @admin.display(description="Код", ordering="wa_code")
    def wa_code_column(self, obj):
        return obj.wa_code or "—"

    @admin.display(description="Характерные особенности", ordering="group_modification_features")
    def group_modification_features_short(self, obj):
        v = obj.group_modification_features or ""
        return (v[:80] + "…") if len(v) > 80 else (v or "—")

    @admin.display(description="На производстве", ordering="in_production_date")
    def in_production_column(self, obj):
        if not obj.in_production:
            return "—"
        if obj.in_production_date:
            return obj.in_production_date.strftime("%m.%Y")
        return "✓"

    _VERSION_SKIP_FIELDS = frozenset({
        "id", "version", "version_diff", "wa_code",
        "author", "last_editor",
        "date_of_creation", "date_of_change",
    })

    def save_model(self, request, obj, form, change):
        raw_value = form.cleaned_data.get("develop_org")
        if raw_value:
            org = RKDDeveloper.objects.filter(pk=raw_value).only("name").first()
            obj.develop_org = org.name if org else ""
        else:
            obj.develop_org = ""

        raw_manufacturer = form.cleaned_data.get("manufacturer_org_post")
        if raw_manufacturer:
            org = RKDDeveloper.objects.filter(pk=raw_manufacturer).only("name").first()
            obj.manufacturer_org_post = org.name if org else ""
        else:
            obj.manufacturer_org_post = ""

        if not obj.is_group_modification:
            obj.product_group = None

        if request.user.is_authenticated:
            if not change or obj.author_id is None:
                obj.author = request.user
            obj.last_editor = request.user
            if not obj.current_responsible_id:
                obj.current_responsible = request.user

        if not change:
            obj.version = "1"
            obj.version_diff = "Стартовая версия"
        else:
            old = Post.objects.get(pk=obj.pk)
            try:
                new_version = str(int(old.version) + 1)
            except (ValueError, TypeError):
                new_version = old.version
            block = _build_version_diff_block(
                old_obj=old,
                new_obj=obj,
                model_cls=Post,
                skip_fields=self._VERSION_SKIP_FIELDS,
                user=request.user if request.user.is_authenticated else None,
                version_to=new_version,
            )
            if block:
                obj.version = new_version
                obj.version_diff = ((old.version_diff or "").rstrip() + "\n\n" + block).strip()

        super().save_model(request, obj, form, change)

        if not obj.wa_code:
            from .helpers import assign_wa_code_to_post
            assign_wa_code_to_post(obj)

    @admin.display(description="Сравнение версий")
    def version_diff_display(self, obj):
        if not obj:
            return "—"
        return mark_safe(_render_version_diff(obj.version_diff or ""))

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        post = form.instance
        selected_ids = set(
            (form.cleaned_data.get("shipments_selector") or Shipment.objects.none())
            .values_list("pk", flat=True)
        )
        # Привязываем выбранные отгрузки к этой разработке (переназначаем при необходимости).
        if selected_ids:
            Shipment.objects.filter(pk__in=selected_ids).update(post=post)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            instance.post = form.instance

            # Только для сущностей с полем name (журнал РКД и др.)
            if hasattr(instance, "name"):
                if not instance.name or not instance.name.strip():
                    instance.name = instance.post.name

            if isinstance(instance, Shipment):
                user = request.user
                if instance.pk is None:
                    instance.author = user
                instance.last_editor = user
                if not instance.current_responsible_id:
                    instance.current_responsible = user

            if isinstance(instance, WorkAssignment):
                if instance.pk is None and request.user.is_authenticated:
                    instance.author = request.user
                    instance.last_editor = request.user
                if instance.post_id:
                    from .helpers import assign_wa_code_to_post, next_wa_number_for_post
                    assign_wa_code_to_post(instance.post)
                    if not instance.wa_number:
                        instance.wa_number = next_wa_number_for_post(
                            instance.post, exclude_pk=instance.pk
                        )

            instance.save()
        formset.save_m2m()
    def technical_assignments_count(self, obj):
        return obj.technical_assignments.count()
    technical_assignments_count.short_description = 'ТЗ (шт.)'

    def open_tech_assignments_link(self, obj):
        url = reverse('admin:blog_technicalassignment_changelist') + f'?post__id__exact={obj.pk}'
        return format_html('<a class="button" href="{}">📂 Открыть ТЗ</a>', url)
    open_tech_assignments_link.short_description = 'Тех. задания'

    def add_tech_assignment_link(self, obj):
        url = reverse('admin:blog_technicalassignment_add') + f'?post={obj.pk}'
        return format_html('<a class="button" href="{}">➕ Новое ТЗ</a>', url)
    add_tech_assignment_link.short_description = 'Создать ТЗ'

try:
    admin.site.unregister(Post)
except admin.sites.NotRegistered:
    pass
admin.site.register(Post, PostAdmin)


class RKDDeveloperAdditionalFileInline(admin.TabularInline):
    model = RKDDeveloperAdditionalFile
    extra = 1
    fields = ("file",)


@admin.register(RKDDeveloper)
class RKDDeveloperAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "inn",
        "charter_link",
        "requisites_link",
        "additional_files_links",
    )
    list_display_links = ("name",)
    search_fields = ("name", "inn")
    inlines = (RKDDeveloperAdditionalFileInline,)
    fields = (
        "name",
        "inn",
        "charter",
        "requisites",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("additional_files")

    @admin.display(description="Устав")
    def charter_link(self, obj):
        if obj.charter:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">Открыть файл</a>',
                obj.charter.url,
            )
        return "—"

    @admin.display(description="Реквизиты")
    def requisites_link(self, obj):
        if obj.requisites:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">Открыть файл</a>',
                obj.requisites.url,
            )
        return "—"

    @admin.display(description="Дополнительные данные")
    def additional_files_links(self, obj):
        rows = list(obj.additional_files.all())
        if not rows:
            return "—"
        parts = []
        for af in rows:
            f = getattr(af, "file", None)
            if f and getattr(f, "name", None):
                name = f.name.rsplit("/", 1)[-1]
                parts.append(
                    format_html(
                        '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
                        f.url,
                        escape(name),
                    )
                )
        if not parts:
            return "—"
        return mark_safe("<br>".join(str(p) for p in parts))


def _rkd_docs_section_header(title: str):
    return mark_safe(
        '<div style="'
        "margin: 0 0 10px 0;"
        "padding: 10px 14px;"
        "font-weight: 700;"
        "font-size: 13px;"
        "letter-spacing: 0.4px;"
        "text-transform: uppercase;"
        "border-left: 4px solid var(--primary, #79aec8);"
        "background: var(--darkened-bg, rgba(121,174,200,0.12));"
        "color: var(--body-fg, inherit);"
        "border-radius: 3px;"
        f'">{escape(title)}</div>'
    )


class UniversalRKDSignatureInline(admin.TabularInline):
    model = UniversalRKDSignature
    extra = 0
    fields = ("role", "signed_by", "signature_file", "signed_at")
    autocomplete_fields = ("signed_by",)
    verbose_name = "Подпись"
    verbose_name_plural = "Подписание документа"


@admin.register(UniversalRKD)
class UniversalRKDAdmin(admin.ModelAdmin):
    change_form_template = "admin/blog/universal_rkd_category_change_form.html"
    change_list_template = "admin/blog/universalrkd/change_list.html"
    form = UniversalRKDForm
    actions = ["send_to_approval_action", "send_to_acknowledgment_action"]

    @admin.action(description="Отправить на согласование")
    def send_to_approval_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=rkd&mode=approval&ids={ids}"
        return redirect(url)

    @admin.action(description="Отправить на ознакомление")
    def send_to_acknowledgment_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=rkd&mode=ack&ids={ids}"
        return redirect(url)

    list_display = (
        "rkd_post_column",
        "rkd_specification_section",
        "rkd_sheet_format",
        "position",
        "desig_document",
        "name",
        "rkd_documents_column",
        "display_lu_lo_sheets",
        "quantity",
        "note",
        "rkd_planned_review_date",
        "rkd_planned_review_warning",
    )
    list_display_links = ("name",)
    list_filter = ("specification_section", "status", "post")
    search_fields = ("name", "desig_document", "category", "post__name")

    @admin.display(description="Разработка (модификация)", ordering="post")
    def rkd_post_column(self, obj):
        return obj.post or "—"

    @admin.display(description="Раздел спецификации", ordering="section_sort_index")
    def rkd_specification_section(self, obj):
        return obj.get_specification_section_display()

    @admin.display(description="Формат (листа)", ordering="sheet_size")
    def rkd_sheet_format(self, obj):
        return obj.get_sheet_size_display()

    @admin.display(description="Документ")
    def rkd_documents_column(self, obj):
        parts = []
        if obj.document_uploaded_file:
            parts.append(
                format_html(
                    '<a href="{}" target="_blank" rel="noopener noreferrer">Документ</a>',
                    obj.document_uploaded_file.url,
                )
            )
        if obj.attestation_document:
            parts.append(
                format_html(
                    '<a href="{}" target="_blank" rel="noopener noreferrer">Удостоверяющий лист</a>',
                    obj.attestation_document.url,
                )
            )
        if not parts:
            return "—"
        return mark_safe("<br>".join(str(p) for p in parts))

    @admin.display(description="ЛУ/ЛО")
    def display_lu_lo_sheets(self, obj):
        return _admin_lu_lo_sheets_column_html(obj)

    @admin.display(
        description="Дата планового пересмотра",
        ordering="validity_date",
    )
    def rkd_planned_review_date(self, obj):
        if not obj.validity_date:
            return "—"
        return obj.validity_date.strftime("%d.%m.%Y")

    @admin.display(
        description="Срок пересмотра истекает",
        ordering="validity_date",
    )
    def rkd_planned_review_warning(self, obj):
        days = getattr(obj, "review_reminder_days", 60)
        if not _universal_rkd_planned_review_show_warning(
            getattr(obj, "validity_date", None),
            days=days,
        ):
            return "—"
        return mark_safe(
            _admin_warning_triangle_html(
                title=f"Плановый пересмотр: осталось не более {days} дн. или срок прошёл",
            )
        )

    autocomplete_fields = (
        "post",
        "current_responsible",
        "checked_by",
        "approved_by",
        "develop_org",
        "internal_recipients",
        "external_recipients",
    )
    inlines = [UniversalRKDSignatureInline]
    readonly_fields = (
        "author",
        "last_editor",
        "date_of_creation",
        "date_of_change",
        "version",
        "version_diff_display",
        "display_files_list",
    )

    fieldsets = (
        (
            "Разработка и классификация",
            {
                "fields": (
                    "post",
                    "specification_section",
                    "category",
                    "name",
                    "desig_document",
                    "primary_use",
                    "change_number",
                    "litera",
                    "trl",
                )
            },
        ),
        (
            "Содержание и статус",
            {
                "fields": (
                    "sheet_size",
                    "position",
                    "info_format",
                    ("validity_date", "revision_criteria"),
                    "review_reminder_days",
                    "language",
                    "internal_recipients",
                    "external_recipients",
                    "status",
                    "related_documents",
                    "develop_org",
                    "comment",
                )
            },
        ),
        (
            None,
            {
                "description": _rkd_docs_section_header("Основной документ"),
                "fields": (
                    "document_uploaded_file",
                    "document_source",
                ),
            },
        ),
        (
            None,
            {
                "description": _rkd_docs_section_header("Лист утверждения"),
                "fields": (
                    "approval_document",
                    "approval_source",
                ),
            },
        ),
        (
            None,
            {
                "description": _rkd_docs_section_header("Лист ознакомления"),
                "fields": (
                    "acquaintance_document",
                ),
            },
        ),
        (
            None,
            {
                "description": _rkd_docs_section_header("Удостоверяющий лист"),
                "fields": (
                    "attestation_document",
                    "attestation_source",
                ),
            },
        ),
        (
            "Данные для спецификации",
            {
                "fields": (
                    "quantity",
                    "note",
                    "weight",
                )
            },
        ),
        (
            "Системные данные",
            {
                "fields": (
                    "author",
                    "current_responsible",
                    "last_editor",
                    "version",
                    "version_diff_display",
                    "date_of_creation",
                    "date_of_change",
                )
            },
        ),
        (
            "Файлы документа",
            {
                "fields": ("display_files_list",),
            },
        ),
    )

    @admin.display(description="Файлы документа")
    def display_files_list(self, obj):
        card_style = (
            "border: 1px solid var(--hairline-color, #e1e4e8);"
            "border-radius: 6px;"
            "background: var(--body-bg, #fff);"
            "padding: 14px 16px;"
            "max-width: 920px;"
        )
        section_title = (
            "margin: 16px 0 8px 0;"
            "font-size: 12px;"
            "font-weight: 600;"
            "letter-spacing: 0.02em;"
            "text-transform: uppercase;"
            "color: var(--body-quiet-color, #6b7280);"
        )
        row_base = "display:flex; gap:12px; align-items:flex-start; padding:8px 0;"
        row_sep = "border-bottom: 1px solid var(--hairline-color, #eef0f3);"
        label_style = "width: 220px; flex: 0 0 220px; color: var(--body-fg, #111); font-weight: 500;"
        value_style = "flex: 1; min-width: 0; word-break: break-word;"
        muted = "color: var(--body-quiet-color, #6b7280);"
        link_style = "color: var(--link-fg, #417690); text-decoration: none;"

        if not obj or not getattr(obj, "pk", None):
            return format_html(
                '<div style="{}">'
                '<div style="{}">Сводка по файлам</div>'
                '<div style="{}">После первого сохранения записи здесь появятся ссылки на загруженные файлы.</div>'
                "</div>",
                card_style,
                section_title,
                muted,
            )

        def _basename(f):
            name = getattr(f, "name", "") or ""
            return name.rsplit("/", 1)[-1] or name

        def _row(
            label: str,
            f,
            *,
            with_sep: bool,
            uploaded_by=None,
            uploaded_at=None,
            action_label: str = "загрузил",
        ):
            row_style = row_base + (row_sep if with_sep else "")
            label_html = f'<div style="{label_style}">{escape(label)}</div>'
            if not f:
                return f'<div style="{row_style}">{label_html}<div style="{value_style} {muted}">не загружен</div></div>'
            url = getattr(f, "url", "") or ""
            filename = escape(_basename(f))
            if url:
                value = (
                    f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer" style="{link_style}">{filename}</a>'
                )
            else:
                value = f'<span style="{muted}">{filename}</span>'
            if uploaded_by and uploaded_at:
                value += (
                    f'<div style="margin-top:6px;font-size:12px;{muted}">'
                    f"{escape(action_label)}: {escape(uploaded_by.get_username())} · "
                    f"{escape(uploaded_at.strftime('%d.%m.%Y %H:%M'))}"
                    f"</div>"
                )
            elif uploaded_by:
                value += (
                    f'<div style="margin-top:6px;font-size:12px;{muted}">'
                    f"{escape(action_label)}: {escape(uploaded_by.get_username())}"
                    f"</div>"
                )
            return f'<div style="{row_style}">{label_html}<div style="{value_style}">{value}</div></div>'

        html = f'<div style="{card_style}">'
        html += f'<div style="{section_title}">Документы</div>'
        last_editor = getattr(obj, "last_editor", None) or getattr(obj, "author", None)
        changed_at = getattr(obj, "date_of_change", None)
        html += _row(
            "Документ — итоговый",
            getattr(obj, "document_uploaded_file", None),
            with_sep=True,
            uploaded_by=last_editor,
            uploaded_at=changed_at,
            action_label="изменил",
        )
        html += _row(
            "Документ — исходник",
            getattr(obj, "document_source", None),
            with_sep=True,
            uploaded_by=last_editor,
            uploaded_at=changed_at,
            action_label="изменил",
        )
        html += _row(
            "Лист утверждения — итоговый (PDF)",
            getattr(obj, "approval_document", None),
            with_sep=True,
            uploaded_by=last_editor,
            uploaded_at=changed_at,
            action_label="изменил",
        )
        html += _row(
            "Лист утверждения — исходник (DOCX)",
            getattr(obj, "approval_source", None),
            with_sep=True,
            uploaded_by=last_editor,
            uploaded_at=changed_at,
            action_label="изменил",
        )
        html += _row(
            "Лист ознакомления (PDF)",
            getattr(obj, "acquaintance_document", None),
            with_sep=True,
            uploaded_by=last_editor,
            uploaded_at=changed_at,
            action_label="изменил",
        )
        html += _row(
            "Удостоверяющий лист — итоговый (PDF)",
            getattr(obj, "attestation_document", None),
            with_sep=True,
            uploaded_by=last_editor,
            uploaded_at=changed_at,
            action_label="изменил",
        )
        html += _row(
            "Удостоверяющий лист — исходник (DOCX)",
            getattr(obj, "attestation_source", None),
            with_sep=False,
            uploaded_by=last_editor,
            uploaded_at=changed_at,
            action_label="изменил",
        )

        sigs = list(obj.signatures.select_related("signed_by").order_by("role")) if obj.pk else []
        if sigs:
            html += f'<div style="{section_title}">Подписи</div>'
            for i, sig in enumerate(sigs):
                label = sig.get_role_display()
                if sig.signed_by:
                    label += f" ({escape(sig.signed_by.get_username())})"
                html += _row(
                    label,
                    sig.signature_file if sig.signature_file else None,
                    with_sep=(i < len(sigs) - 1),
                    uploaded_by=sig.signed_by,
                    action_label="подписал",
                )

        html += "</div>"
        return mark_safe(html)

    def get_ordering(self, request):
        position_asc = F("_position_num").asc(nulls_last=True)
        if request.GET.get("post__id__exact"):
            return ("section_sort_index", position_asc, "order_in_section", "pk")
        return (
            "post_id",
            "section_sort_index",
            position_asc,
            "order_in_section",
            "pk",
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        post_id = request.GET.get("post__id__exact")
        if post_id:
            extra_context["rkd_breadcrumb_post"] = Post.objects.filter(pk=post_id).first()
        return super().changelist_view(request, extra_context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = dict(extra_context or {})
        extra_context = _inject_rkd_category_json(extra_context)
        if object_id:
            obj = self.get_object(request, unquote(object_id))
            if obj is not None:
                if obj.post_id:
                    extra_context["rkd_breadcrumb_post"] = obj.post
                extra_context["rkd_breadcrumb_record_title"] = str(obj)
        else:
            post_q = request.GET.get("post")
            if post_q:
                extra_context["rkd_breadcrumb_post"] = Post.objects.filter(pk=post_q).first()
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_changeform_initial_data(self, request):
        return super().get_changeform_initial_data(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            _position_num=Case(
                When(
                    position__regex=r"^[0-9]+$",
                    then=Cast("position", output_field=IntegerField()),
                ),
                default=Value(None),
                output_field=IntegerField(),
            )
        )
        return qs.select_related(
            "post",
            "develop_org",
            "author",
            "last_editor",
            "current_responsible",
            "checked_by",
            "approved_by",
        )

    _VERSION_SKIP_FIELDS = frozenset({
        "id", "version", "version_diff",
        "author", "last_editor",
        "date_of_creation", "date_of_change",
        "order_in_section", "section_sort_index",
    })

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
            obj.version = "1"
            obj.version_diff = "Стартовая версия"
        else:
            old = UniversalRKD.objects.get(pk=obj.pk)
            try:
                new_version = str(int(old.version) + 1)[:3]
            except (ValueError, TypeError):
                new_version = old.version
            block = _build_version_diff_block(
                old_obj=old,
                new_obj=obj,
                model_cls=UniversalRKD,
                skip_fields=self._VERSION_SKIP_FIELDS,
                user=request.user if request.user.is_authenticated else None,
                version_to=new_version,
            )
            if block:
                obj.version = new_version
                obj.version_diff = ((old.version_diff or "").rstrip() + "\n\n" + block).strip()

        obj.last_editor = request.user
        if not obj.current_responsible_id:
            obj.current_responsible = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if not obj.pk:
            return
        if obj.attestation_document or obj.attestation_source:
            return
        if not obj.signatures.exists():
            return
        try:
            from blog.services import UniversalRKDService
            UniversalRKDService.generate_approval_sheet(obj, request.user)
        except Exception as e:
            messages.warning(
                request,
                f"Лист утверждения не обновлён: {e}",
            )

    @admin.display(description="Сравнение версий")
    def version_diff_display(self, obj):
        if not obj:
            return "—"
        return mark_safe(_render_version_diff(obj.version_diff or ""))

    def get_form(self, request, obj=None, change=False, **kwargs):
        FormClass = super().get_form(request, obj, change=change, **kwargs)

        class _RKDForm(FormClass):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, **form_kwargs)
                if not self.is_bound:
                    cr_field = self.fields.get("current_responsible")
                    if cr_field is not None:
                        current_val = self.initial.get("current_responsible") or getattr(
                            self.instance, "current_responsible_id", None
                        )
                        if not current_val:
                            self.initial["current_responsible"] = request.user.pk

        return _RKDForm

    _PDF_FILE_FIELDS = {
        "approval_document",
        "acquaintance_document",
        "attestation_document",
    }
    _DOCX_FILE_FIELDS = {
        "approval_source",
        "attestation_source",
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is None:
            return formfield
        name = db_field.name
        if name in self._PDF_FILE_FIELDS:
            formfield.widget.attrs.setdefault("accept", ".pdf,application/pdf")
        elif name in self._DOCX_FILE_FIELDS:
            formfield.widget.attrs.setdefault(
                "accept",
                ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        return formfield


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    """Журнал: колонки по ТЗ — разработка первой, как в РКД; без служебного id в списке."""

    change_list_template = "admin/blog/shipment/change_list.html"
    inlines = (ShipmentAdditionalFileInline,)
    list_display = (
        "shipment_post_column",
        "serial_number",
        "manufacture_date",
        "psi_conclusion_status",
        "passport_link",
        "additional_files_links",
        "shipment_date",
        "manufacturer_column",
        "supplier_column",
        "buyer_column",
        "recipient_column",
        "completeness",
        "note",
    )
    list_display_links = ("serial_number",)
    list_filter = ("post",)
    search_fields = (
        "serial_number",
        "post__name",
        "note",
        "completeness",
        "manufacturer_org__name",
        "supplier_org__name",
    )
    ordering = ("post", "manufacture_date", "serial_number", "pk")
    autocomplete_fields = (
        "post",
        "buyer",
        "recipient",
        "manufacturer_org",
        "supplier_org",
        "author",
        "last_editor",
        "current_responsible",
    )
    fieldsets = (
        (
            "Разработка",
            {"fields": ("post",)},
        ),
        (
            "Данные отгрузки",
            {
                "fields": (
                    "serial_number",
                    "manufacture_date",
                    "manufacturer_org",
                    "supplier_org",
                    "product_passport",
                    "shipment_date",
                    "buyer",
                    "recipient",
                    "completeness",
                    "note",
                )
            },
        ),
        (
            "Ответственные",
            {
                "fields": (
                    "author",
                    "last_editor",
                    "current_responsible",
                    "date_of_creation",
                    "date_of_change",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("post", "buyer", "recipient", "manufacturer_org", "supplier_org")
            .prefetch_related("additional_files")
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        post_id = request.GET.get("post__id__exact")
        if post_id:
            extra_context["shipment_breadcrumb_post"] = Post.objects.filter(pk=post_id).first()
        return super().changelist_view(request, extra_context)

    @admin.display(description="Изготовитель", ordering="manufacturer_org__name")
    def manufacturer_column(self, obj):
        return obj.manufacturer_org or "—"

    @admin.display(description="Поставщик", ordering="supplier_org__name")
    def supplier_column(self, obj):
        return obj.supplier_org or "—"

    @admin.display(description="Покупатель", ordering="buyer__name_of_company")
    def buyer_column(self, obj):
        if not obj.buyer:
            return "—"
        return format_html(
            '<span style="white-space: normal; word-break: break-word; display: inline-block; max-width: 220px;">{}</span>',
            str(obj.buyer),
        )

    @admin.display(description="Грузополучатель", ordering="recipient")
    def recipient_column(self, obj):
        if not obj.recipient:
            return "—"
        return format_html(
            '<span style="white-space: normal; word-break: break-word; '
            'display: inline-block; max-width: 220px;">{}</span>',
            str(obj.recipient),
        )

    def get_readonly_fields(self, request, obj=None):
        """Создатель фиксируется при первом сохранении; в уже созданной записи только просмотр."""
        fields = ["date_of_creation", "date_of_change"]
        if obj is not None:
            fields.append("author")
        return fields

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial = dict(initial or {})
        initial["author"] = request.user.pk
        initial["last_editor"] = request.user.pk
        initial["current_responsible"] = request.user.pk
        return initial

    @admin.display(description="Разработка (модификация)", ordering="post")
    def shipment_post_column(self, obj):
        return obj.post or "—"

    @admin.display(description="Заключение")
    def psi_conclusion_status(self, obj):
        """Итоговое заключение по протоколу ПСИ для этого изделия.
        готов / не готов — по заключению протокола (у которого есть готовый PDF);
        — (прочерк) — если PDF на изделие ещё не сформирован."""
        doc = (
                PSIDocument.objects.filter(shipment=obj, pdfs__isnull=False).distinct().first()
                or PAKDocument.objects.filter(shipment=obj, pdfs__isnull=False).distinct().first()
        )
        if not doc:
            return "—"
        if doc.conclusion == 'готов к отгрузке':
            return format_html('<b style="color:#28a745;">готов</b>')
        if doc.conclusion == 'не готов':
            return format_html('<b style="color:#dc3545;">не готов</b>')
        return "—"


    @admin.display(description="Паспорт/Формуляр", ordering="product_passport")
    def passport_link(self, obj):
        if obj.product_passport:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">Открыть файл</a>',
                obj.product_passport.url,
            )
        return "—"

    @admin.display(description="Дополнительные данные (загружаемый файл)")
    def additional_files_links(self, obj):
        rows = list(obj.additional_files.all())
        if not rows:
            return "—"
        parts = []
        for af in rows:
            f = getattr(af, "file", None)
            if f and getattr(f, "name", None):
                name = f.name.rsplit("/", 1)[-1]
                parts.append(
                    format_html(
                        '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
                        f.url,
                        escape(name),
                    )
                )
        if not parts:
            return "—"
        return mark_safe("<br>".join(str(p) for p in parts))

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        if not obj.current_responsible_id:
            obj.current_responsible = request.user
        super().save_model(request, obj, form, change)


# @admin.register(ListTechnicalProposal)  # скрыто: замещено TechnicalProposal (ПТ)
class ListTechnicalProposalAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'desig_document_list_technical_proposal', 'status', 'date_of_creation']
    search_fields = ['name', 'desig_document_list_technical_proposal']
    readonly_fields = ('date_of_change',)


    #def save_model(self, request, obj, form, change):
      #  if obj.post and not obj.name:
        #    obj.name = obj.post.name
        #super().save_model(request, obj, form, change)

# @admin.register(GeneralDrawingProduct)  # скрыто: замещено TechnicalProposal (ПТ)
class GeneralDrawingProductAdmin(admin.ModelAdmin):
    list_display = (
        'name','category','author','date_of_creation','status','version',
    )
    search_fields = ('name',)
    list_filter = ('category', 'status', 'trl', 'litera')
    readonly_fields = ('date_of_change',)

# @admin.register(ElectronicModelProduct)  # скрыто: замещено TechnicalProposal (ПТ)
class ElectronicModelProductAdmin(admin.ModelAdmin):
    list_display = (
        'name','desig_document_electronic_model_product','author','date_of_creation','status','version','trl',
    )
    search_fields = ('name', 'desig_document_electronic_model_product')
    list_filter = ('status', 'trl', 'category', 'develop_org')
    readonly_fields = ('date_of_change',)

# @admin.register(GeneralElectricalDiagram)  # скрыто: замещено TechnicalProposal (ПТ)
class GeneralElectricalDiagramAdmin(admin.ModelAdmin):
    list_display = (
        'name','desig_document','author','date_of_creation','status','version',
    )
    search_fields = ('name', 'desig_document', 'author__username')
    list_filter = ('status', 'trl', 'develop_org', 'language')
    readonly_fields = ('date_of_change',)

# @admin.register(SoftwareProduct)  # скрыто: замещено TechnicalProposal (ПТ)
class SoftwareProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'desig_document_software_product', 'status', 'version', 'date_of_creation')
    search_fields = ('name', 'desig_document_software_product', 'status')
    list_filter = ('status', 'trl', 'category', 'version')
    readonly_fields = ('date_of_change',)

# @admin.register(GeneralDrawingUnit)  # скрыто: замещено TechnicalProposal (ПТ)
class GeneralDrawingUnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'desig_document_general_drawing_unit', 'status', 'version')
    readonly_fields = ('date_of_change',)

# @admin.register(ElectronicModelUnit)  # скрыто: замещено TechnicalProposal (ПТ)
class ElectronicModelUnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'desig_document_electronic_model_unit', 'status', 'version')
    readonly_fields = ('date_of_change',)

# @admin.register(DrawingPartUnit)  # скрыто: замещено TechnicalProposal (ПТ)
class DrawingPartUnitAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'desig_document_drawing_part_unit',
        'status',
        'version',
        'date_of_creation',
        'last_editor',
        'develop_org',
    )
    list_filter = ('status', 'category', 'trl', 'develop_org')
    search_fields = ('name', 'author__username', 'last_editor__username')
    inlines = [AttachmentInline]
    ordering = ('-date_of_creation',)
    readonly_fields = ('date_of_change',)

    fieldsets = (
        (None, {
            'fields': (
                'name', 'category', 'desig_document_drawing_part_unit',
                'info_format', 'primary_use', 'change_number'
            )
        }),
        ('Состояние и управление', {
            'fields': (
                'status', 'priority', 'version', 'version_diff',
                'litera', 'trl', 'validity_date', 'subscribers', 'related_documents'
            )
        }),
        ('Ответственные', {
            'fields': (
                'author', 'last_editor', 'current_responsible', 'develop_org', 'language'
            )
        }),
        ('Служебные поля', {
            'fields': (
                'date_of_creation', 'date_of_change', 'pattern'
            )
        }),
    )

# @admin.register(ElectronicModelPartUnit)  # скрыто: замещено TechnicalProposal (ПТ)
class ElectronicModelPartUnitAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'desig_document_electronic_model_part_unit',
        'category',
        'status',
        'version',
        'trl',
        'date_of_creation',
        'last_editor',
    )
    search_fields = ('name', 'desig_document_electronic_model_part_unit', 'category')
    inlines = [AttachmentInline]
    list_filter = ('status', 'trl', 'category', 'develop_org')
    readonly_fields = ('date_of_change',)

    fieldsets = (
        (None, {
            'fields': (
                'category', 'name', 'desig_document_electronic_model_part_unit', 'info_format',
                'primary_use', 'change_number',
                'pattern', 'version', 'version_diff',
                'litera', 'trl', 'validity_date',
                'subscribers', 'related_documents', 'develop_org', 'language'
            )
        }),
        ('Ответственные', {
            'fields': ('author', 'last_editor', 'current_responsible')
        }),
        ('Статус', {
            'fields': ('status', 'priority')
        }),
        ('Временные метки', {
            'fields': ('date_of_creation', 'date_of_change')
        }),
    )

# @admin.register(DrawingPartProduct)  # скрыто: замещено TechnicalProposal (ПТ)
class DrawingPartProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'desig_document_drawing_part_product',
        'category',
        'status',
        'version',
        'trl',
        'author',
        'current_responsible',
        'date_of_creation',
        'date_of_change',
    )
    list_filter = ('category', 'status', 'trl', 'date_of_creation')
    search_fields = ('name', 'desig_document_drawing_part_product', 'author__username', 'current_responsible__username')
    readonly_fields = ('date_of_change',)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

# @admin.register(ElectronicModelPartProduct)  # скрыто: замещено TechnicalProposal (ПТ)
class ElectronicModelPartProductAdmin(admin.ModelAdmin):
    list_display = (
        'desig_document_electronic_model_part_product', 'name', 'category',
        'status', 'version', 'trl', 'author',
        'current_responsible', 'date_of_creation', 'date_of_change', 'info_format'
    )
    list_filter = ('category', 'status', 'trl', 'date_of_creation')
    search_fields = ('desig_document_electronic_model_part_product', 'name', 'author__username', 'current_responsible__username')
    readonly_fields = ('date_of_change',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

# @admin.register(ReportTechnicalProposal)  # скрыто: замещено TechnicalProposal (ПТ)
class ReportTechnicalProposalAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'status', 'version',
        'author', 'current_responsible', 'date_of_creation'
    )
    list_filter = ('category', 'status', 'date_of_creation')
    search_fields = ('name', 'desig_document_report_technical_proposal', 'author__username')
    readonly_fields = ('date_of_change',)

# @admin.register(AddReportTechnicalProposal)  # скрыто: замещено TechnicalProposal (ПТ)
class AddReportTechnicalProposalAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'status',
        'version',
        'priority',
        'author',
        'current_responsible',
        'date_of_creation',
        'date_of_change',
    )
    list_filter = ('category', 'status', 'date_of_creation')
    readonly_fields = ('date_of_change',)
    inlines = [AttachmentInline]
    search_fields = ('name', 'author__username', 'current_responsible__username')
    fieldsets = (
        (None, {
            'fields': (
                'category',
                'name',
                'info_format',
                'status',
                'version',
                'version_diff',
                'priority',
                'validity_date',
                'subscribers',
                'related_documents',
                'develop_org',
                'language',
                'author',
                'last_editor',
                'current_responsible',
                'date_of_creation',
                'date_of_change',
            )
        }),
    )

# @admin.register(ProtocolTechnicalProposal)  # скрыто: замещено TechnicalProposal (ПТ)
class ProtocolTechnicalProposalAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category',
        'status', 'version',
        'author', 'current_responsible',
        'date_of_creation', 'date_of_change'
    )
    list_filter = ('status', 'category', 'date_of_creation')
    search_fields = ('name', 'desig_document_protocol_technical_proporsal', 'author__username', 'current_responsible__username')
    readonly_fields = ('date_of_change',)

    def save_model(self, request, obj, form, change):
        """Автоматически проставляем автора и редактора"""
        if not obj.pk:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

class OverdueFilter(admin.SimpleListFilter):
    title = "Просрочен целевой срок"
    parameter_name = "overdue"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Просрочен"),
            ("no", "Не просрочен"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(is_target_overdue_db=True)

        if self.value() == "no":
            return queryset.filter(is_target_overdue_db=False)

        return queryset


class WorkAssignmentDraftFilter(admin.SimpleListFilter):
    title = "Черновики"
    parameter_name = "draft"

    def lookups(self, request, model_admin):
        return (("yes", "Черновики"),)

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(executor__isnull=True)
        return queryset


class RevenueRangeFilter(admin.SimpleListFilter):
    title = 'Выручка'
    parameter_name = 'revenue_range'

    def lookups(self, request, model_admin):
        return [
            ('<100', 'до 100 млрд'),
            ('100-500', '100–500 млрд'),
            ('>500', 'более 500 млрд'),
        ]

    def queryset(self, request, queryset):
        def parse(value):
            try:
                return float(value.replace(',', '.'))
            except:
                return 0

        if self.value() == '<100':
            return queryset.filter(revenue_for_last_year__lt='100')
        elif self.value() == '100-500':
            return queryset.filter(
                revenue_for_last_year__gte='100',
                revenue_for_last_year__lte='500'
            )
        elif self.value() == '>500':
            return queryset.filter(revenue_for_last_year__gt='500')
        return queryset



QUOTE_CHARS = '\"\'`«»“”„‟‹›‚‛’‘ˮ'  # набор «умных» и обычных кавычек

def normalize_search(text: str) -> list[str]:
    """
    Удаляем кавычки/мусор и разбиваем на слова (кириллица/латиница/цифры).
    Возвращаем список терминов без пустых.
    """
    if not text:
        return []
    # уберем кавычки
    for ch in QUOTE_CHARS:
        text = text.replace(ch, " ")
    # вытащим «слова» (включая кириллицу и латиницу)
    terms = re.findall(r"\w+", text, flags=re.UNICODE)
    return [t for t in terms if t]
    # всё приводим к нижнему через casefold
    return [w.casefold() for w in re.findall(r"\w+", t, flags=re.UNICODE) if w]


class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name_of_company', 'revenue_for_last_year', 'length_of_electrical_network_km', 'support_tickets_link')
    # Объедини фильтры в один список
    list_filter = ('name_of_company', 'revenue_for_last_year')
    list_filter = (RevenueRangeFilter,)
    search_fields = ('name_of_company', 'address', 'name_of_company_ci')

    def support_tickets_link(self, obj):
        """Отображение ссылки на обращения контрагента"""
        count = obj.support_tickets.count()
        if count:
            url = reverse('admin:crm_supportticket_changelist') + f'?customer__id__exact={obj.pk}'
            return format_html(
                '<a href="{}" style="font-weight: bold; background: #79aec8; color: white; padding: 4px 8px; border-radius: 3px; text-decoration: none;">📞 Обращения ({})</a>',
                url, count
            )
        return format_html('<span style="color: gray;">📞 Обращения (0)</span>')
    support_tickets_link.short_description = 'Обращения'
    support_tickets_link.admin_order_field = 'name_of_company'

class SupportTicketInline(admin.TabularInline):
    model = SupportTicket
    extra = 0
    fields = ('created_date', 'category', 'problem', 'status', 'intake_channel')
    readonly_fields = ('created_date',)
    show_change_link = True

inlines = [SupportTicketInline]

class Decision_makerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'city_of_location', 'function', 'customer')
    list_filter = ('city_of_location', 'function', 'customer')
    search_fields = ('full_name__icontains', 'phone_number__icontains', 'email__icontains')


class DealAdmin(admin.ModelAdmin):
    list_display = ('customer', 'start_date', 'status', 'deal_amount')
    list_filter = ('customer', 'start_date', 'customer')
    search_fields = ('customer__name_of_company', 'description')
    date_hierarchy = 'start_date'  # Иерархия по дате


class ProductAdmin(admin.ModelAdmin):
    list_display = ('name_of_product', 'end_customer_price')
    list_filter = ('name_of_product',)
    search_fields = ('name_of_product', 'description')


class Deal_stageAdmin(admin.ModelAdmin):
    list_display = ('deal', 'start_date_step', 'status')
    list_filter = ('status', 'deal')
    search_fields = ('deal__customer__name_of_company', 'description_of_task_at_stage')


#@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ('customer', 'decision_maker', 'planned_date', 'responsible', 'deal')
    list_filter = ('planned_date',)
    date_hierarchy = 'planned_date'
    list_select_related = ('customer',)
    autocomplete_fields = ('customer',)

    # Отключаем стандартный механизм, чтобы полностью контролировать поведение
    search_fields = ('id',)

    # Список полей, по которым ищем (подставь свои реальные имена)
    SEARCH_FIELDS = (
        'customer__name_of_company',     # основной заголовок компании
        'decision_maker__full_name',
        'call_goal',
        'call_result',
    )

    # для экономии запросов в changelist
    list_select_related = ('customer', 'decision_maker')

    def display_customer(self, obj):
        """Заказчик с твоим форматированием"""
        if obj.customer and obj.customer.name_of_company:
            return format_html(
                '<div style="min-width: 150px; max-width: 600px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.customer.name_of_company
            )
        return "—"

    def display_decision_maker(self, obj):
        """ЛПР с твоим форматированием"""
        if obj.decision_maker and obj.decision_maker.full_name:
            return format_html(
                '<div style="min-width: 150px; max-width: 600px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.decision_maker.full_name
            )
        return "—"

    display_decision_maker.short_description = 'ЛПР'
    display_decision_maker.admin_order_field = 'decision_maker__full_name'

    display_customer.short_description = 'Заказчик'
    display_customer.admin_order_field = 'customer__name_of_company'

    def _get_attr_chain(self, obj, dotted):
        """Достаёт значение по цепочке 'customer__name_of_company'."""
        cur = obj
        for part in dotted.split('__'):
            if cur is None:
                return ''
            cur = getattr(cur, part, None)
        return '' if cur is None else str(cur)

    def get_search_results(self, request, queryset, search_term):
        # пустой ввод — стандартное поведение
        if not search_term:
            return queryset, False

        qs = queryset.select_related('customer', 'decision_maker')

        # если ввели число — добавим такой id к результатам
        id_match = set()
        if search_term.isdigit():
            try:
                id_match.add(int(search_term))
            except ValueError:
                pass

        # нормализуем поисковую строку
        s = search_term.strip()
        terms = [t for t in s.split() if t]
        folded_terms = [t.casefold() for t in terms]

        matched_ids = []

        # перебираем объекты пачками, формируем «буфер» и ищем без регистра
        for obj in qs.iterator(chunk_size=500):
            parts = [self._get_attr_chain(obj, f) for f in self.SEARCH_FIELDS]
            blob = ' '.join(parts).casefold()

            ok = True
            for t in folded_terms:
                if t not in blob:
                    ok = False
                    break
            if ok:
                matched_ids.append(obj.id)

        # плюс числовой id, если совпал
        if id_match:
            matched_ids.extend(id_match)

        if not matched_ids:
            return queryset.none(), True

        return queryset.filter(id__in=set(matched_ids)), True


@admin.register(IncomingLetter)
class IncomingLetterAdmin(admin.ModelAdmin):
    class Form(forms.ModelForm):
        date_of_receipt_date = forms.DateField(label="Дата получения")
        date_of_receipt_time = forms.TimeField(label="Время получения", required=False)
        confirm_registration_recalc = forms.BooleanField(
            required=False,
            label="Подтвердить пересчёт внутреннего номера",
            help_text="Обязательно, если меняете календарную дату получения: номер будет выдан заново.",
        )

        class Meta:
            model = IncomingLetter
            exclude = ("registration_number", "registration_number_reassigned")

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            from django.contrib.admin.widgets import AdminDateWidget, AdminTimeWidget
            self.fields["date_of_receipt_date"].widget = AdminDateWidget()
            self.fields["date_of_receipt_time"].widget = AdminTimeWidget()
            if not self.instance.pk:
                self.fields.pop("confirm_registration_recalc", None)
            if self.instance and self.instance.pk and self.instance.date_of_receipt:
                local_receipt = timezone.localtime(self.instance.date_of_receipt)
                self.fields["date_of_receipt_date"].initial = local_receipt.date()
                self.fields["date_of_receipt_time"].initial = local_receipt.time().replace(
                    second=0, microsecond=0
                )

            sig = self.fields.get("sender_signature")
            if sig:
                sender_id = None
                if self.data and self.data.get("sender"):
                    try:
                        sender_id = int(self.data.get("sender"))
                    except (TypeError, ValueError):
                        pass
                elif self.instance and getattr(self.instance, "sender_id", None):
                    sender_id = self.instance.sender_id
                if sender_id:
                    sig.queryset = Decision_maker.objects.filter(customer_id=sender_id).order_by(
                        "full_name", "id"
                    )
                else:
                    sig.queryset = Decision_maker.objects.none()

        def clean(self):
            cleaned = super().clean()
            urgent = cleaned.get("urgent")
            d = cleaned.get("date_of_receipt_date")
            t = cleaned.get("date_of_receipt_time")

            if not d:
                raise forms.ValidationError({"date_of_receipt_date": "Обязательное поле."})

            if urgent and not t:
                raise forms.ValidationError({"date_of_receipt_time": "Укажите время при метке «Срочно»."})

            from datetime import time, datetime
            dt = datetime.combine(d, t or time(0, 0))
            cleaned["date_of_receipt"] = timezone.make_aware(dt, timezone.get_current_timezone())

            letter_date = cleaned.get("letter_date")
            if letter_date is not None and cleaned.get("date_of_receipt"):
                receipt_local_date = timezone.localtime(cleaned["date_of_receipt"]).date()
                if receipt_local_date < letter_date:
                    raise ValidationError(
                        {
                            "date_of_receipt_date": (
                                "Дата получения не может быть раньше даты письма."
                            ),
                        }
                    )

            sender = cleaned.get("sender")
            sender_sig = cleaned.get("sender_signature")
            if sender_sig and sender and sender_sig.customer_id != sender.pk:
                raise ValidationError(
                    {
                        "sender_signature": "Подписант должен относиться к выбранной организации.",
                    }
                )

            if self.instance.pk and cleaned.get("date_of_receipt"):
                try:
                    old = IncomingLetter.objects.only("date_of_receipt").get(pk=self.instance.pk)
                except IncomingLetter.DoesNotExist:
                    old = None
                if old and old.date_of_receipt:
                    old_d = timezone.localtime(old.date_of_receipt).date()
                    new_d = timezone.localtime(cleaned["date_of_receipt"]).date()
                    if old_d != new_d and not cleaned.get("confirm_registration_recalc"):
                        raise ValidationError(
                            {
                                "confirm_registration_recalc": (
                                    "Дата получения изменится — внутренний регистрационный номер будет "
                                    "пересчитан. Отметьте подтверждение ниже и снова нажмите «Сохранить»."
                                ),
                            }
                        )
            return cleaned

        def save(self, commit=True):
            obj = super().save(commit=False)
            obj.date_of_receipt = self.cleaned_data["date_of_receipt"]
            if commit:
                obj.save()
                self.save_m2m()
            return obj

    form = Form

    change_form_template = "admin/crm/incomingletter/change_form.html"

    class Media:
        js = ("blog/js/incoming_letter_lpr.js",)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["incoming_letter_lpr_url"] = reverse(
            "crm_decision_makers_by_customer"
        )
        return super().changeform_view(request, object_id, form_url, extra_context)

    list_display = (
        'letter_date_display',
        'date_of_receipt_display',
        'sender_identification',
        'sender',
        'urgent_warning',
        'receipt_method',
        'subject',
        'replies_link',
        'current_responsible',
        'registration_number_display',
    )
    list_display_links = ('sender_identification',)
    list_filter = ('receipt_method', 'letter_date')
    search_fields = ('sender_identification', 'subject', 'sender__name_of_company')
    date_hierarchy = 'date_of_receipt'
    readonly_fields = ('date_of_creation', 'date_of_change', 'registration_number_display')
    autocomplete_fields = ('sender',)

    fieldsets = (
        (None, {
            'fields': (
                'registration_number_display',
                'sender_identification',
                'sender',
                'sender_signature',
                'letter_date',
                'date_of_receipt_date',
                'urgent',
                'date_of_receipt_time',
                'receipt_method',
                'subject',
            )
        }),
        ('Документ', {'fields': ('document_uploaded_file', 'comment')}),
        ('Ответственные', {'fields': ('current_responsible',)}),
        ('Версия', {'fields': ('version',)}),
        ('Системная информация', {
            'fields': ('date_of_creation', 'date_of_change')
        }),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None:
            fieldsets = list(fieldsets)
            first = fieldsets[0]
            fields = list(first[1]["fields"])
            if "confirm_registration_recalc" not in fields:
                try:
                    idx = fields.index("date_of_receipt_time") + 1
                    fields.insert(idx, "confirm_registration_recalc")
                except ValueError:
                    fields.append("confirm_registration_recalc")
            fieldsets[0] = (first[0], {**first[1], "fields": tuple(fields)})
            return (
                fieldsets[0],
                fieldsets[1],
                fieldsets[2],
                fieldsets[3],
                ('Системная информация', {
                    'fields': ('author', 'last_editor', 'date_of_creation', 'date_of_change')
                }),
            )
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.readonly_fields
        return ('author', 'last_editor') + tuple(self.readonly_fields)

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            try:
                old = IncomingLetter.objects.only("date_of_receipt").get(pk=obj.pk)
            except IncomingLetter.DoesNotExist:
                old = None
            if old and old.date_of_receipt and obj.date_of_receipt:
                old_d = timezone.localtime(old.date_of_receipt).date()
                new_d = timezone.localtime(obj.date_of_receipt).date()
                if old_d != new_d:
                    obj.registration_number = ""
                    obj.registration_number_reassigned = True
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Внутренний рег. номер", ordering="registration_number")
    def registration_number_display(self, obj):
        if not obj or not obj.pk:
            return "Присваивается при сохранении"
        if not obj.registration_number:
            return "—"
        if getattr(obj, "registration_number_reassigned", False):
            return format_html(
                '{} <span style="color:#666;">(изменен)</span>',
                obj.registration_number,
            )
        return obj.registration_number

    @admin.display(description="Связанные исходящие")
    def replies_link(self, obj):
        count = getattr(obj, "replies", None).count() if obj.pk else 0
        if not count:
            return "—"
        url = reverse("admin:crm_outgoingletter_changelist") + f"?reply_to__id__exact={obj.pk}"
        return format_html('<a href="{}">Ответы ({})</a>', url, count)

    @admin.display(description="Дата получения", ordering="date_of_receipt")
    def date_of_receipt_display(self, obj):
        if not obj.date_of_receipt:
            return "—"
        local_dt = timezone.localtime(obj.date_of_receipt)
        if not obj.urgent:
            return local_dt.strftime("%d.%m.%Y")
        return local_dt.strftime("%d.%m.%Y %H:%M")

    @admin.display(description="Срочно")
    def urgent_warning(self, obj):
        if not obj.urgent:
            return "—"
        return mark_safe('<span style="color: #f0ad4e; font-weight: bold;">⚠️</span>')

    @admin.display(description="Дата письма", ordering="letter_date")
    def letter_date_display(self, obj):
        if not obj.letter_date:
            return "—"
        return obj.letter_date.strftime("%d.%m.%Y")


@admin.register(OutgoingLetter)
class OutgoingLetterAdmin(admin.ModelAdmin):
    class Form(forms.ModelForm):
        date_of_send_date = forms.DateField(label="Дата отправки")
        date_of_send_time = forms.TimeField(label="Время отправки", required=False)
        confirm_registration_recalc = forms.BooleanField(
            required=False,
            label="Подтвердить пересчёт регистрационного номера",
            help_text="Обязательно, если меняете дату письма: номер привязан к ней и будет выдан заново.",
        )

        class Meta:
            model = OutgoingLetter
            exclude = ("registration_number", "registration_number_reassigned")

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            from django.contrib.admin.widgets import AdminDateWidget, AdminTimeWidget
            self.fields["date_of_send_date"].widget = AdminDateWidget()
            self.fields["date_of_send_time"].widget = AdminTimeWidget()
            if not self.instance.pk:
                self.fields.pop("confirm_registration_recalc", None)

            if self.instance and self.instance.pk and self.instance.date_of_send:
                local_send = timezone.localtime(self.instance.date_of_send)
                self.fields["date_of_send_date"].initial = local_send.date()
                self.fields["date_of_send_time"].initial = local_send.time().replace(
                    second=0, microsecond=0
                )
            else:
                self.fields["date_of_send_date"].initial = timezone.localdate()

            pr = self.fields.get("person_recipient")
            if pr:
                recipient_id = None
                if self.data and self.data.get("recipient"):
                    try:
                        recipient_id = int(self.data.get("recipient"))
                    except (TypeError, ValueError):
                        pass
                elif self.instance and getattr(self.instance, "recipient_id", None):
                    recipient_id = self.instance.recipient_id
                if recipient_id:
                    pr.queryset = Decision_maker.objects.filter(customer_id=recipient_id).order_by(
                        "full_name", "id"
                    )
                else:
                    pr.queryset = Decision_maker.objects.none()

        def clean(self):
            cleaned = super().clean()
            urgent = cleaned.get("urgent")
            d = cleaned.get("date_of_send_date")
            t = cleaned.get("date_of_send_time")

            if not d:
                raise forms.ValidationError({"date_of_send_date": "Обязательное поле."})

            if urgent and not t:
                raise forms.ValidationError({"date_of_send_time": "Укажите время при метке «Срочно»."})

            from datetime import time, datetime
            dt = datetime.combine(d, t or time(0, 0))
            cleaned["date_of_send"] = timezone.make_aware(dt, timezone.get_current_timezone())

            letter_date = cleaned.get("letter_date")
            if letter_date is not None and cleaned.get("date_of_send"):
                send_local_date = timezone.localtime(cleaned["date_of_send"]).date()
                if send_local_date < letter_date:
                    raise ValidationError(
                        {
                            "date_of_send_date": (
                                "Дата отправки не может быть раньше даты письма."
                            ),
                        }
                    )

            recipient = cleaned.get("recipient")
            person_recipient = cleaned.get("person_recipient")
            if person_recipient and recipient and person_recipient.customer_id != recipient.pk:
                raise ValidationError(
                    {
                        "person_recipient": "Получатель (ЛПР) должен относиться к выбранной организации.",
                    }
                )

            if self.instance.pk and cleaned.get("letter_date") is not None:
                try:
                    old = OutgoingLetter.objects.only("letter_date").get(pk=self.instance.pk)
                except OutgoingLetter.DoesNotExist:
                    old = None
                if old and old.letter_date != cleaned["letter_date"]:
                    if not cleaned.get("confirm_registration_recalc"):
                        raise ValidationError(
                            {
                                "confirm_registration_recalc": (
                                    "Дата письма изменится — регистрационный номер будет пересчитан "
                                    "(он привязан к дате письма). Отметьте подтверждение и снова нажмите «Сохранить»."
                                ),
                            }
                        )
            return cleaned

        def save(self, commit=True):
            obj = super().save(commit=False)
            obj.date_of_send = self.cleaned_data["date_of_send"]
            if commit:
                obj.save()
                self.save_m2m()
            return obj

    form = Form

    change_form_template = "admin/crm/incomingletter/change_form.html"

    class Media:
        js = ("blog/js/incoming_letter_lpr.js",)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["incoming_letter_lpr_url"] = reverse(
            "crm_decision_makers_by_customer"
        )
        extra_context["reply_to_sender_url"] = reverse(
            "crm_incoming_letter_sender_for_reply"
        )
        return super().changeform_view(request, object_id, form_url, extra_context)

    list_display = (
        'registration_number_display',
        'reply_to_link',
        'recipient',
        'letter_date_display',
        'date_of_send_display',
        'urgent_warning',
        'subject',
        'executor',
        'send_method',
        'current_responsible',
    )
    list_display_links = ('registration_number_display',)
    list_filter = ('send_method', 'letter_date')
    search_fields = ('registration_number', 'subject', 'recipient__name_of_company')
    date_hierarchy = 'letter_date'
    readonly_fields = ('date_of_creation', 'date_of_change', 'registration_number_display')
    autocomplete_fields = ('recipient', 'reply_to')

    fieldsets = (
        (None, {
            'fields': (
                'registration_number_display',
                'reply_to',
                'recipient',
                'person_recipient',
                'letter_date',
                'date_of_send_date',
                'urgent',
                'date_of_send_time',
                'subject',
                'sender_signature',
                'executor',
                'send_method',
                'receipt_verification',
            )
        }),
        ('Документы', {'fields': ('document_uploaded_file', 'app_uploaded_file', 'comment')}),
        ('Ответственные', {'fields': ('current_responsible',)}),
        ('Версия', {'fields': ('version',)}),
        ('Системная информация', {
            'fields': ('date_of_creation', 'date_of_change')
        }),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None:
            fieldsets = list(fieldsets)
            first = fieldsets[0]
            fields = list(first[1]["fields"])
            if "confirm_registration_recalc" not in fields:
                try:
                    idx = fields.index("letter_date") + 1
                    fields.insert(idx, "confirm_registration_recalc")
                except ValueError:
                    fields.append("confirm_registration_recalc")
            fieldsets[0] = (first[0], {**first[1], "fields": tuple(fields)})
            return (
                fieldsets[0],
                fieldsets[1],
                fieldsets[2],
                fieldsets[3],
                ('Системная информация', {
                    'fields': ('author', 'last_editor', 'date_of_creation', 'date_of_change')
                }),
            )
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.readonly_fields
        return ('author', 'last_editor') + tuple(self.readonly_fields)

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            try:
                old = OutgoingLetter.objects.only("letter_date").get(pk=obj.pk)
            except OutgoingLetter.DoesNotExist:
                old = None
            if old and obj.letter_date and old.letter_date != obj.letter_date:
                obj.registration_number = ""
                obj.registration_number_reassigned = True
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Рег. номер", ordering="registration_number")
    def registration_number_display(self, obj):
        if not obj or not obj.pk:
            return "Присваивается при сохранении"
        if not obj.registration_number:
            return "—"
        if getattr(obj, "registration_number_reassigned", False):
            return format_html(
                '{} <span style="color:#666;">(изменен)</span>',
                obj.registration_number,
            )
        return obj.registration_number

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("reply_to")

    @admin.display(description="В ответ на")
    def reply_to_link(self, obj):
        if not obj.reply_to_id:
            return "—"
        url = reverse("admin:crm_incomingletter_change", args=[obj.reply_to_id])
        label = obj.reply_to.sender_identification if obj.reply_to else str(obj.reply_to_id)
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="Дата письма", ordering="letter_date")
    def letter_date_display(self, obj):
        if not obj.letter_date:
            return "—"
        return obj.letter_date.strftime("%d.%m.%Y")

    @admin.display(description="Дата отправки", ordering="date_of_send")
    def date_of_send_display(self, obj):
        if not obj.date_of_send:
            return "—"
        local_dt = timezone.localtime(obj.date_of_send)
        if not obj.urgent:
            return local_dt.strftime("%d.%m.%Y")
        return local_dt.strftime("%d.%m.%Y %H:%M")

    @admin.display(description="Срочно")
    def urgent_warning(self, obj):
        if not obj.urgent:
            return "—"
        return mark_safe('<span style="color: #f0ad4e; font-weight: bold;">⚠️</span>')


@admin.register(Company_branch)
class Company_branchAdmin(admin.ModelAdmin):
    list_display = ('name_of_company', 'revenue_for_last_year', 'length_of_electrical_network_km')
    list_filter = ('name_of_company', 'revenue_for_last_year')  # Фильтры в правой части
    list_filter = (RevenueRangeFilter,)
    search_fields = ('name_of_company', 'address')  # Поиск по этим полям

class MeetingFileInline(admin.TabularInline):
    model = MeetingFile
    extra = 1
    fields = ['file', 'description', 'uploaded_at']
    readonly_fields = ['uploaded_at']
    max_num = 10  # Ограничение на количество файлов

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer', 'decision_maker', 'responsible_user',
        'meeting_date', 'meeting_time', 'status'
    ]
    list_filter = ('meeting_date', 'customer', 'decision_maker', 'responsible_user', 'status')
    ordering = ('-meeting_date', '-meeting_time')
    inlines = [MeetingFileInline]  # Добавляем inline для файлов

    # Отключаем стандартный механизм, чтобы полностью контролировать поведение
    search_fields = ('id',)

    # Список полей, по которым ищем (подставь свои реальные имена)
    SEARCH_FIELDS = (
        'customer__name_of_company',     # основной заголовок компании
        'decision_maker__full_name',
    )

    fieldsets = (
        ('Основная информация', {
            'fields': ('customer', 'decision_maker', 'responsible_user')
        }),
        ('Дата и время', {
            'fields': ('meeting_date', 'meeting_time')
        }),
        ('Статус и описание', {
            'fields': ('status', 'goal_description', 'result_description')
        }),
    )

    def display_customer(self, obj):
        """Заказчик с твоим форматированием"""
        if obj.customer and obj.customer.name_of_company:
            return format_html(
                '<div style="min-width: 150px; max-width: 600px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.customer.name_of_company
            )
        return "—"

    display_customer.short_description = 'Заказчик'
    display_customer.admin_order_field = 'customer__name_of_company'

    def display_decision_maker(self, obj):
        """ЛПР с твоим форматированием"""
        if obj.decision_maker and obj.decision_maker.full_name:
            return format_html(
                '<div style="min-width: 150px; max-width: 600px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.decision_maker.full_name
            )
        return "—"

    display_decision_maker.short_description = 'ЛПР'
    display_decision_maker.admin_order_field = 'decision_maker__full_name'

    def save_model(self, request, obj, form, change):
        # Автоматически подставляем ЛПР заказчика, если не выбран
        if obj.customer and not obj.decision_maker:
            obj.decision_maker = obj.customer.лпр
        super().save_model(request, obj, form, change)

    def get_search_results(self, request, queryset, search_term):
        terms = normalize_search(search_term)

        if not terms:
            # Ничего не ввели (или остались только кавычки): стандартное поведение
            return super().get_search_results(request, queryset, search_term)

        # Для каждого слова строим OR по полям, затем AND между словами
        per_term_q = []
        for term in terms:
            ors = [Q(**{f"{field}__icontains": term}) for field in self.SEARCH_FIELDS]
            per_term_q.append(reduce(or_, ors))

        final_q = reduce(and_, per_term_q)
        qs = queryset.filter(final_q)

        # DISTINCT может понадобиться при JOIN'ах (многие-ко-многим).
        # Здесь FK, так что False, но вернём True «на всякий случай», это безопасно.
        return qs, True

#@admin.register(MeetingFile)
#class MeetingFileAdmin(admin.ModelAdmin):
 #   list_display = ['meeting', 'file', 'description', 'uploaded_at']
  #  list_filter = ['uploaded_at', 'meeting']
   # search_fields = ['meeting__customer__name_of_company', 'description']




# Inline для комментариев
class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    form = TicketCommentForm
    extra = 1
    fields = ['author', 'text', 'file', 'created_date']
    readonly_fields = ['created_date']
    verbose_name = 'Запись взаимодействия'
    verbose_name_plural = 'Взаимодействие по обработке обращений'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author')


# Заявки
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    form = SupportTicketForm
    autocomplete_fields = ('customer', 'product', 'assigned_to')
    list_display = [
        'id', 'created_date', 'customer', 'product', 'get_category_display',
        'get_intake_channel_display', 'truncated_problem', 'status_badge',
        'claim_type_display', 'status_changed_date',
        'created_by', 'assigned_to', 'custom_actions',
    ]
    list_filter = [
        'status', 'category', 'intake_channel', 'claim_type',
        'created_date', 'customer', 'product', 'assigned_to',
    ]
    search_fields = [
        'problem', 'description', 'resolution', 'customer__name_of_company',
        'id', 'created_by__username',
    ]
    readonly_fields = ['status_changed_date', 'created_by']
    inlines = [TicketCommentInline]
    date_hierarchy = 'created_date'
    list_per_page = 25

    fieldsets = (
        ('Обращение', {
            'fields': (
                'customer', 'product', 'category', 'problem', 'description',
                'created_date', 'intake_channel',
            ),
        }),
        ('Обработка', {
            'fields': (
                'status', 'resolution', 'claim_type', 'claim_attachment',
                'assigned_to', 'created_by', 'status_changed_date',
            ),
        }),
    )

    def truncated_problem(self, obj):
        return obj.problem[:50] + '...' if len(obj.problem) > 50 else obj.problem

    truncated_problem.short_description = 'Проблема'

    def status_badge(self, obj):
        status_colors = {
            'new': 'gray',
            'in_progress': 'blue',
            'waiting': 'orange',
            'resolved': 'green'
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = 'Статус'

    @admin.display(description='Претензия', ordering='claim_type')
    def claim_type_display(self, obj):
        if not obj.claim_type:
            return '—'
        return obj.get_claim_type_display()

    def custom_actions(self, obj):
        view_url = reverse('admin:crm_supportticket_change', args=[obj.id])
        return format_html(
            '<a href="{}">👁️ Просмотр</a>',
            view_url
        )

    custom_actions.short_description = 'Действия'

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault('created_date', timezone.localdate())
        return initial

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            if not obj.created_date:
                obj.created_date = timezone.localdate()
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'customer', 'product', 'created_by', 'assigned_to'
        )

# Комментарии (отдельная регистрация для полного управления)
@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author', 'truncated_text', 'created_date']
    list_filter = ['created_date', 'author']
    search_fields = ['text', 'ticket__id', 'author__username']
    readonly_fields = ['created_date']

    def truncated_text(self, obj):
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text

    truncated_text.short_description = 'Текст'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('ticket', 'author')



admin.site.register(Customer, CustomerAdmin)
admin.site.register(Decision_maker, Decision_makerAdmin)
admin.site.register(Deal, DealAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(Deal_stage, Deal_stageAdmin)
admin.site.register(Notifications)
admin.site.register(Call, CallAdmin)
#admin.site.register(Meeting, MeetingAdmin)


# EAM (СИСТЕМА УПРАВЛЕНИЕ АКТИВАМИ)
class WorkEquipmentFileInline(admin.TabularInline):
    model = WorkEquipmentFile
    extra = 0
    fields = ("title", "file", "note")
    verbose_name_plural = "Сопроводительные документы"

class TransportVehicleFileInline(admin.TabularInline):
    model = TransportVehicleFile
    extra = 1

class ProductionAreaFileInline(admin.TabularInline):
    model = ProductionAreaFile
    extra = 1

class WorkEquipmentRepairFileInline(admin.TabularInline):
    model = WorkEquipmentRepairFile
    extra = 1
    verbose_name_plural = "Документы, чеки"


class WorkEquipmentRepairInline(admin.StackedInline):
    model = WorkEquipmentRepair
    extra = 0
    show_change_link = True
    verbose_name = "Ремонт / ТО"
    verbose_name_plural = "РЕМОНТЫ / ТО"
    fields = (
        "repair_date",
        "description",
        "next_planned_date",
        "planned_works_description",
    )
    readonly_fields = ()

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("work_equipment")


class TransportRepairFileInline(admin.TabularInline):
    model = TransportRepairFile
    extra = 1

# Рабочее оборудование
@admin.register(WorkEquipment)
class WorkEquipmentAdmin(admin.ModelAdmin):
    list_display = (
        "name_type",
        "serial_number_link",
        "measuring_device_display",
        "next_calibration_date_display",
        "calibration_warning",
        "calibration_date_warning",
        "workstation",
        "status",
        "documents_column",
        "repairs_link",
    )
    list_filter = ("measuring_device",)
    search_fields = ("name_type", "serial_number", "workstation")
    readonly_fields = ("author", "last_editor", "date_of_creation", "date_of_change", "version_diff_display")
    inlines = [WorkEquipmentFileInline, WorkEquipmentRepairInline]

    _VERSION_SKIP_FIELDS = frozenset({
        "id", "version", "version_diff",
        "author", "last_editor",
        "date_of_creation", "date_of_change",
    })

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("files", "repairs")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "calibration_info":
            kwargs["widget"] = forms.Textarea(attrs={"rows": 3})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Средство измерений")
    def measuring_device_display(self, obj):
        if obj.measuring_device:
            return mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="Да">')
        return "—"

    def next_calibration_date_display(self, obj):
        if not obj.next_calibration_date:
            return "—"
        return obj.next_calibration_date

    next_calibration_date_display.short_description = "Дата плановой поверки"
    next_calibration_date_display.admin_order_field = "next_calibration_date"

    @admin.display(description="Сопроводительные документы")
    def documents_column(self, obj):
        docs = [d for d in obj.files.all() if d.file and d.file.name]
        if not docs:
            return "—"
        parts = []
        for d in docs:
            label = d.title or d.file.name.split("/")[-1]
            parts.append(format_html(
                '<div style="margin:0 0 4px 0;line-height:1.35;">'
                '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>'
                '</div>',
                d.file.url,
                label,
            ))
        return mark_safe("".join(str(p) for p in parts))

    @admin.display(description="Сравнение версий")
    def version_diff_display(self, obj):
        if not obj:
            return "—"
        return mark_safe(_render_version_diff(obj.version_diff or ""))

    @admin.display(description="Ремонты / ТО")
    def repairs_link(self, obj):
        url = (
            reverse("admin:enterprise_asset_management_workequipmentrepair_changelist")
            + f"?work_equipment__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{} ({})</a>', url, "Ремонты / ТО", obj.repairs.count())

    def get_fieldsets(self, request, obj=None):
        main_fields = (
            "name_type",
            "serial_number",
            "measuring_device",
            "next_calibration_date",
            "calibration_info",
            "calibration_required",
            "planned_calibration_date",
            "workstation",
            "replacement_equipment",
            "status",
        )
        if obj is None:
            return (
                (None, {"fields": main_fields}),
                ("Сопроводительные документы", {"fields": ("note",)}),
                ("Системные данные", {"fields": (
                    "current_responsible",
                    "version",
                    "version_diff_display",
                    "date_of_creation",
                    "date_of_change",
                )}),
            )
        return (
            (None, {"fields": main_fields}),
            ("Сопроводительные документы", {"fields": ("note",)}),
            ("Ремонты / ТО", {"fields": ("repairs_all_link",)}),
            ("Системные данные", {"fields": (
                "author",
                "last_editor",
                "current_responsible",
                "version",
                "version_diff_display",
                "date_of_creation",
                "date_of_change",
            )}),
        )

    def get_readonly_fields(self, request, obj=None):
        base = ("date_of_creation", "date_of_change", "version_diff_display")
        if obj is None:
            return base
        return ("author", "last_editor", "repairs_all_link") + base

    @admin.display(description="")
    def repairs_all_link(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = (
            reverse("admin:enterprise_asset_management_workequipmentrepair_changelist")
            + f"?work_equipment__id__exact={obj.pk}"
        )
        count = obj.repairs.count()
        return format_html(
            '<a href="{}" class="button" style="'
            'display:inline-block;padding:4px 12px;border-radius:4px;'
            'background:#417690;color:#fff;text-decoration:none;font-size:12px;">'
            '📋 Открыть все ремонты / ТО ({})</a>',
            url, count,
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
            obj.version = "1"
            obj.version_diff = "Стартовая версия"
        else:
            old = WorkEquipment.objects.get(pk=obj.pk)
            try:
                new_version = str(int(old.version) + 1)[:3]
            except (ValueError, TypeError):
                new_version = old.version
            block = _build_version_diff_block(
                old_obj=old,
                new_obj=obj,
                model_cls=WorkEquipment,
                skip_fields=self._VERSION_SKIP_FIELDS,
                user=request.user if request.user.is_authenticated else None,
                version_to=new_version,
            )
            if block:
                obj.version = new_version
                obj.version_diff = ((old.version_diff or "").rstrip() + "\n\n" + block).strip()
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in instances:
            if not obj.pk:
                obj.author = request.user
            obj.last_editor = request.user
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

# Кастомные колонки
    def _warning_triangle_svg(self, *, title: str, color: str) -> str:
        return (
            f'<span title="{title}" style="display:inline-flex;align-items:center;">'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
            f'viewBox="0 0 24 24" aria-hidden="true" focusable="false" style="vertical-align: -2px;">'
            f'<path d="M1 21h22L12 2 1 21z" fill="{color}"></path>'
            f'<rect x="11" y="9" width="2" height="6" fill="#111"></rect>'
            f'<rect x="11" y="17" width="2" height="2" fill="#111"></rect>'
            f"</svg>"
            f"</span>"
        )

    def serial_number_link(self, obj):
        if not obj.serial_number:
            return "—"

        url = reverse(
            "admin:enterprise_asset_management_workequipment_change",
            args=[obj.pk],
        )
        return format_html('<a href="{}">{}</a>', url, obj.serial_number)

    serial_number_link.short_description = "Заводской / инвентарный номер"
    serial_number_link.admin_order_field = "serial_number"

    def calibration_warning(self, obj):
        if not obj.measuring_device or not obj.next_calibration_date:
            return "—"

        today = timezone.now().date()
        days_left = (obj.next_calibration_date - today).days

        if days_left <= 45:
            color = "#9aa0a6" if obj.status == "in_stock" else "#f0ad4e"
            return mark_safe(self._warning_triangle_svg(title="Срок поверки истекает", color=color))

        return "—"

    calibration_warning.short_description = "Срок поверки истекает"

    def calibration_date_warning(self, obj):
        if not obj.calibration_required or not obj.planned_calibration_date:
            return "—"
        today = timezone.now().date()
        days_left = (obj.planned_calibration_date - today).days
        if days_left <= 45:
            color = "#9aa0a6" if obj.status == "in_stock" else "#f0ad4e"
            return mark_safe(self._warning_triangle_svg(title="Срок калибровки истекает", color=color))
        return "—"

    calibration_date_warning.short_description = "Срок калибровки истекает"

# Ремонты / ТО рабочего оборудования
@admin.register(WorkEquipmentRepair)
class WorkEquipmentRepairAdmin(admin.ModelAdmin):

    list_display = (
        "work_equipment",
        "repair_date",
        "description",
        "next_planned_date",
        "author",
        "date_of_creation",
    )

    list_filter = (
        "repair_date",
        "work_equipment",
    )

    search_fields = (
        "work_equipment__name_type",
        "work_equipment__serial_number",
        "description",
    )

    readonly_fields = ("author", "last_editor", "date_of_creation", "date_of_change")

    inlines = [WorkEquipmentRepairFileInline]

    fieldsets = (
        ("Основная информация", {
            "fields": (
                "work_equipment",
                "repair_date",
                "description",
            )
        }),
        ("Планово-предупредительные работы", {
            "fields": (
                "next_planned_date",
                "planned_works_description",
            )
        }),
        ("Системная информация", {
            "fields": (
                "author",
                "last_editor",
                "date_of_creation",
                "date_of_change",
            )
        }),
    )

    def has_module_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)


# Транспорт
@admin.register(TransportVehicle)
class TransportVehicleAdmin(admin.ModelAdmin):

    list_display = (
        "make_model",
        "registration_plate",
        "next_insurance_date",
        "insurance_expiry_warning",
        "next_inspection_date",
        "inspection_expiry_warning",
        "repairs_link",
    )

    search_fields = (
        "make_model",
        "registration_plate",
    )

    readonly_fields = (
        "date_of_creation",
        "date_of_change",
    )

    inlines = [TransportVehicleFileInline]

    fieldsets = (
        ("Основная информация", {
            "fields": (
                "make_model",
                "registration_plate",
            )
        }),
        ("Страхование и техосмотр", {
            "fields": (
                "insurance",
                "next_insurance_date",
                "inspection",
                "next_inspection_date",
            )
        }),
        ("Ответственные", {
            "fields": (
                "author",
                "last_editor",
                "current_responsible",
                "note",
            )
        }),
        ("Версия", {
            "fields": ("version",)
        }),
        ("Системная информация", {
            "fields": (
                "date_of_creation",
                "date_of_change",
            )
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)


    def repairs_link(self, obj):
        url = reverse(
            "admin:enterprise_asset_management_transportrepair_changelist"
        ) + f"?transport_vehicle__id__exact={obj.pk}"

        return format_html(
            '<a href="{}">{} ({})</a>',
            url,
            "Ремонты",
            obj.repairs.count()
        )

    repairs_link.short_description = "Ремонты"

    @admin.display(description="Срок страховки истекает")
    def insurance_expiry_warning(self, obj):
        if not obj.insurance or not obj.next_insurance_date:
            return "—"
        today = timezone.now().date()
        days_left = (obj.next_insurance_date - today).days
        if days_left <= 15:
            return mark_safe('<span style="color: #f0ad4e; font-weight: bold;">⚠️</span>')
        return "—"

    @admin.display(description="Срок техосмотра истекает")
    def inspection_expiry_warning(self, obj):
        if not obj.inspection or not obj.next_inspection_date:
            return "—"
        today = timezone.now().date()
        days_left = (obj.next_inspection_date - today).days
        if days_left <= 15:
            return mark_safe('<span style="color: #f0ad4e; font-weight: bold;">⚠️</span>')
        return "—"


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("repairs")

#ремонтТС
@admin.register(TransportRepair)
class TransportRepairAdmin(admin.ModelAdmin):

    list_display = (
        "transport_vehicle",
        "repair_date",
        "description",
        "author",
        "date_of_creation",
    )

    list_filter = (
        "repair_date",
        "transport_vehicle",
    )

    search_fields = (
        "transport_vehicle__make_model",
        "transport_vehicle__registration_plate",
        "description",
    )

    readonly_fields = (
        "date_of_creation",
    )

    inlines = [TransportRepairFileInline]

    fieldsets = (
        ("Основная информация", {
            "fields": (
                "transport_vehicle",
                "repair_date",
                "description",
            )
        }),
        ("Системная информация", {
            "fields": (
                "author",
                "date_of_creation",
            )
        }),
    )

    def has_module_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)

# ПроизводственныеПлощадки
@admin.register(ProductionAreaLocation)
class ProductionAreaLocationAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("name",)

    def has_module_permission(self, request):
        return False


@admin.register(ProductionArea)
class ProductionAreaAdmin(admin.ModelAdmin):

    list_display = (
        "number_name",
        "object",
        "location_ref",
        "working_conditions",
        "restrictions",
        "contract_date_display",
        "contract_status_display",
        "purpose_display",
    )

    list_display_links = ("number_name",)

    list_filter = (
        "object",
        "location_ref",
        "working_conditions",
        "restrictions",
    )

    search_fields = ("number_name",)

    inlines = [ProductionAreaFileInline]

    fieldsets = (
        ("Основная информация", {
            "fields": (
                "object",
                "location_ref",
                "number_name",
                "area",
                "purpose",
                "workstations",
                "working_conditions",
                "restrictions",
                "contract_date",
                "note",
            )
        }),
        ("Ответственные лица", {
            "fields": (
                "current_responsible",
            )
        }),
        ("Системная информация", {
            "fields": (
                "author",
                "last_editor",
                "date_of_creation",
                "date_of_change",
            )
        }),
    )

    readonly_fields = (
        "author",
        "last_editor",
        "date_of_creation",
        "date_of_change",
        "version",
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "location_ref":
            kwargs["queryset"] = ProductionAreaLocation.objects.order_by("name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user

        if not obj.location_ref:
            obj.location_ref, _ = ProductionAreaLocation.objects.get_or_create(
                name="Технопарк Университетский"
            )

        super().save_model(request, obj, form, change)

    def contract_status_display(self, obj):
        if obj.restrictions == "none" or not obj.contract_date:
            return "—"

        today = timezone.now().date()
        warning_date = obj.contract_date - timedelta(days=45)

        # Просрочено
        if obj.contract_date < today:
            return format_html(
                '<span style="color:red; font-weight:bold;">✖</span>'
            )

        # Меньше 45 дней
        if today >= warning_date:
            return format_html(
                '<span style="color:#f0ad4e; font-weight:bold;">⚠</span>'
            )

        return "—"

    contract_status_display.short_description = "Срок договора истекает"

    @admin.display(description="Дата действия договора")
    def contract_date_display(self, obj):
        return obj.contract_date or "—"

    @admin.display(description="Назначение")
    def purpose_display(self, obj):
        return obj.purpose or "—"

@admin.register(TaskForDesignWork)
class TaskForDesignWorkAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'author', 'date_of_creation', 'status', 'version', 'post', 'open_task_link', 'add_task_link')
    search_fields = ('name', 'author__username', 'current_responsible__username')
    list_filter = ('status', 'priority', 'language', 'post')
    readonly_fields = ('date_of_creation', 'date_of_change')
    search_fields = ('name',)

    def open_task_link(self, obj):
        url = reverse('admin:blog_taskfordesignwork_changelist') + f'?technical_assignment__id__exact={obj.technical_assignment_id}'
        return format_html('<a class="button" href="{}">Открыть ПЗ</a>', url)
    open_task_link.short_description = 'Список ПЗ'

    def add_task_link(self, obj):
        url = reverse('admin:blog_taskfordesignwork_add') + f'?technical_assignment={obj.technical_assignment_id}'
        return format_html('<a class="button" href="{}">Новое ПЗ</a>', url)
    add_task_link.short_description = 'Создать ПЗ'

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        ta_id = request.GET.get('technical_assignment')
        if ta_id:
            initial['technical_assignment'] = ta_id
        return initial

    class Media:
        css = {
            'all': ('admin/admin_hscroll.css',)  # тот же CSS со скроллом
        }


@admin.register(RevisionTask)
class RevisionTaskAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'author', 'post', 'date_of_creation', 'status', 'version')
    search_fields = ('name', 'author__username', 'current_responsible__username', 'post__name')
    list_filter = ('status', 'priority', 'language', 'post',)
    readonly_fields = ('date_of_creation', 'date_of_change')

    autocomplete_fields = ['post']


class DeadlineChangeInline(admin.TabularInline):
    model = WorkAssignmentDeadlineChange
    extra = 0
    can_delete = False
    fields = (
        "old_target_deadline", "new_target_deadline",
        "old_hard_deadline", "new_hard_deadline",
        "reason", "changed_by", "changed_at",
    )
    readonly_fields = fields
    show_change_link = False

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        tech_id = request.GET.get('technical_assignment')
        if tech_id:
            initial['technical_assignment'] = tech_id
        return initial


class WorkAssignmentSubtaskInline(admin.TabularInline):
    model = WorkAssignmentSubtask
    extra = 0
    can_delete = True
    show_change_link = False
    verbose_name = "Подзадача"
    verbose_name_plural = mark_safe(
        'ПОДЗАДАЧИ'
        '<div style="font-weight:normal;font-size:12px;color:#c8c8c8;margin-top:4px;">'
        '💡 Для добавления сохраните основную задачу через «Сохранить и продолжить редактировать»'
        '</div>'
    )
    fields = (
        "parent_rz_display",
        "subtask_code_link",
        "executor",
        "target_deadline",
        "task_preview",
        "criteria_preview",
        "control_status",
        "overdue_flag",
        "comment_preview",
    )
    readonly_fields = (
        "parent_rz_display",
        "subtask_code_link",
        "executor",
        "target_deadline",
        "task_preview",
        "criteria_preview",
        "overdue_flag",
        "comment_preview",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.control_status in WorkAssignment.TERMINAL_STATUSES:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.control_status in WorkAssignment.TERMINAL_STATUSES:
            return False
        return super().has_delete_permission(request, obj)

    @admin.display(description="РЗ")
    def parent_rz_display(self, obj):
        wa = getattr(obj, "work_assignment", None)
        if wa is not None and getattr(wa, "pk", None):
            return wa.wa_full_code or "—"
        return "—"

    @admin.display(description="Подзадача")
    def subtask_code_link(self, obj):
        if not obj.pk:
            return "—"
        code = obj.subtask_full_code or "—"
        url = reverse("admin:blog_workassignmentsubtask_change", args=[obj.pk])
        return format_html(
            '<a href="{}" class="subtask-open-link"><strong>{}</strong></a>',
            url,
            code,
        )

    @admin.display(description="Задача")
    def task_preview(self, obj):
        t = (obj.task or "").strip()
        if not t:
            return "—"
        return mark_safe(
            '<div class="subtask-inline-cell">' + linebreaksbr(t) + "</div>"
        )

    @admin.display(description="Критерий выполнения")
    def criteria_preview(self, obj):
        t = (obj.acceptance_criteria or "").strip()
        if t in ("", "---"):
            return "—"
        return mark_safe(
            '<div class="subtask-inline-cell">' + linebreaksbr(t) + "</div>"
        )

    @admin.display(description="Статус")
    def control_status_colored(self, obj):
        return _render_status_circle(obj.control_status)

    @admin.display(description="Просрочено?")
    def overdue_flag(self, obj):
        active = obj.control_status in (None, "in_progress")
        if not active:
            return "—"
        deadline = obj.hard_deadline or obj.target_deadline
        if deadline and timezone.localdate() > deadline:
            return "⚠️"
        return "—"

    @admin.display(description="Комментарий")
    def comment_preview(self, obj):
        t = (obj.comment or "").strip()
        if not t:
            return "—"
        return mark_safe(
            '<div class="subtask-inline-cell">' + linebreaksbr(t) + "</div>"
        )


@admin.register(WorkAssignmentSubtask)
class WorkAssignmentSubtaskAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return False

    def add_view(self, request, form_url="", extra_context=None):
        extra = dict(extra_context or ())
        extra["title"] = "Добавить подзадачу рабочего задания"
        return super().add_view(request, form_url, extra_context=extra)

    list_display = (
        "id", "work_assignment", "task_short",
        "target_deadline", "executor",
        "control_status_colored", "comment_short",
    )
    search_fields = ("task", "work_assignment__name")
    readonly_fields = ("date_of_creation", "date_of_change")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "category",
                    "executor",
                    "author",
                    "current_responsible",
                    "task",
                    "acceptance_criteria",
                )
            },
        ),
        (
            "Сроки",
            {
                "fields": (
                    "target_deadline",
                    "hard_deadline",
                    ("time_window_start", "time_window_end"),
                    "conditional_deadline",
                )
            },
        ),
        (
            "Статус выполнения / Результат",
            {
                "fields": (
                    "control_status",
                    "control_date",
                    "comment",
                    "result_description",
                    "uploaded_file",
                )
            },
        ),
        (
            "Системная информация",
            {
                "fields": (
                    "date_of_creation",
                    "date_of_change",
                    "last_editor",
                )
            },
        ),
    )

    def get_exclude(self, request, obj=None):
        excl = list(super().get_exclude(request, obj) or [])
        for name in (
            "work_assignment",
            "version",
            "deadline_version",
            "reschedule_count",
        ):
            if name not in excl:
                excl.append(name)
        return excl

    def _get_parent_wa(self, request, obj=None):
        if obj is not None and getattr(obj, "work_assignment_id", None):
            return obj.work_assignment
        wa_id = request.GET.get("work_assignment") or request.POST.get("work_assignment")
        if not wa_id:
            return None
        try:
            return WorkAssignment.objects.get(pk=wa_id)
        except (WorkAssignment.DoesNotExist, ValueError, TypeError):
            return None

    def has_change_permission(self, request, obj=None):
        parent = self._get_parent_wa(request, obj)
        if parent is not None and parent.control_status in WorkAssignment.TERMINAL_STATUSES:
            return False
        return super().has_change_permission(request, obj)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        parent = self._get_parent_wa(request, obj)
        if parent is None:
            return fieldsets

        code = parent.wa_full_code or ""
        title = (parent.name or "").strip()
        if code and title:
            label = f"{code} — {title}"
        else:
            label = code or title or "—"

        description = format_html(
            '<div style="margin:0 0 12px;padding:10px 14px;'
            'background:rgba(121,174,200,.10);border-left:3px solid #79aec8;'
            'border-radius:4px;font-size:13px;">'
            '<span style="opacity:.75;">Рабочее задание:</span> '
            '<strong>{}</strong>'
            '</div>',
            label,
        )

        new_fieldsets = []
        for i, (name, opts) in enumerate(fieldsets):
            opts = dict(opts)
            if i == 0:
                opts["description"] = description
            new_fieldsets.append((name, opts))
        return new_fieldsets

    @admin.display(description="Задача")
    def task_short(self, obj):
        t = (obj.task or "").strip().replace("\n", " ")
        return (t[:60] + "...") if len(t) > 60 else (t or "—")

    @admin.display(description="Статус выполнения / Результат", ordering="control_status")
    def control_status_colored(self, obj):
        return _render_status_circle(obj.control_status)

    @admin.display(description="Комментарий")
    def comment_short(self, obj):
        t = (obj.comment or "").strip().replace("\n", " ")
        return (t[:60] + "...") if len(t) > 60 else (t or "—")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if request.user.is_authenticated:
            initial.setdefault("author", request.user.pk)
            initial.setdefault("last_editor", request.user.pk)
            initial.setdefault("current_responsible", request.user.pk)
        return initial

    def get_form(self, request, obj=None, change=False, **kwargs):
        FormCls = super().get_form(request, obj, change=change, **kwargs)
        parent_wa = self._get_parent_wa(request, obj)

        class _SubtaskForm(FormCls):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                if parent_wa is not None and not getattr(self.instance, "work_assignment_id", None):
                    self.instance.work_assignment = parent_wa

        return _SubtaskForm

    def save_model(self, request, obj, form, change):
        user = request.user
        old_executor_id = None
        if change:
            old_executor_id = (
                WorkAssignmentSubtask.objects
                .filter(pk=obj.pk)
                .values_list("executor_id", flat=True)
                .first()
            )
        if not change:
            if user.is_authenticated:
                obj.author = user
                obj.last_editor = user
            if not getattr(obj, "work_assignment_id", None):
                parent = self._get_parent_wa(request)
                if parent is not None:
                    obj.work_assignment = parent

        if obj.work_assignment_id and not obj.subtask_number:
            from .helpers import next_subtask_number_for_wa
            obj.subtask_number = next_subtask_number_for_wa(
                obj.work_assignment, exclude_pk=obj.pk
            )

        super().save_model(request, obj, form, change)

        if obj.executor_id and obj.executor_id != old_executor_id and obj.executor_id != user.id:
            from approvals.services import notify
            from approvals.models import Notification
            notify(
                obj.executor,
                "Вас назначили исполнителем подзадачи",
                text=f"«{obj.task or obj}» (РЗ: {obj.work_assignment}).",
                url=reverse("admin:blog_workassignmentsubtask_change", args=[obj.pk]),
                kind=Notification.KIND_WORK,
            )

@admin.register(WorkAssignment)
class WorkAssignmentAdmin(admin.ModelAdmin):
    form = WorkAssignmentAdminForm
    formfield_overrides = {
        DateField: {"widget": AdminDateWidget},
    }

    list_display = (
        'wa_code_column',
        'name', 'author_link', 'executor_link', 'post',
        'overdue_target_flag',
        'overdue_hard_flag',
        'control_status_colored',
        'control_date',
        'target_deadline', 'hard_deadline',
    )
    list_display_links = ('wa_code_column', 'name')
    ordering = ('post__wa_code', 'wa_number', 'pk')
    search_fields = (
        'name',
        'author__username',
        'current_responsible__username',
        'post__wa_code',
    )
    list_filter = ('control_status', WorkAssignmentDraftFilter, OverdueFilter)

    @admin.display(description='Код', ordering='post__wa_code')
    def wa_code_column(self, obj):
        return obj.wa_full_code or '—'

    @admin.display(description='Автор', ordering='author')
    def author_link(self, obj):
        if not obj.author_id:
            return '—'
        return format_html(
            '<a href="{}">{}</a>',
            reverse('admin:approvals_user_profile', args=[obj.author_id]),
            obj.author,
        )

    @admin.display(description='Исполнитель', ordering='executor')
    def executor_link(self, obj):
        if not obj.executor_id:
            return '—'
        return format_html(
            '<a href="{}">{}</a>',
            reverse('admin:approvals_user_profile', args=[obj.executor_id]),
            obj.executor,
        )

    readonly_fields = (
        'author', 'last_editor',
        'date_of_creation', 'date_of_change',
        'version', 'version_diff_display',
        'deadline_version', 'reschedule_count',
        'control_status_display', 'control_date_display',
    )

    inlines = [DeadlineChangeInline, WorkAssignmentSubtaskInline, WorkAssignmentAttachmentInline]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'name', 'executor', 'category', 'post',
                'is_urgent',
                'task', 'acceptance_criteria',
            )
        }),
        ('Сроки (изменять через «Перенести срок»)', {
            'fields': (
                'target_deadline',
                'requires_hard_deadline',
                'hard_deadline',
                'conditional_deadline',
            )
        }),
        ('Статус выполнения / Результат', {
            'fields': ('control_status_display', 'control_date_display', 'result_description', 'comment')
        }),
        ('Системные данные', {
            'fields': (
                'author', 'last_editor', 'current_responsible',
                'version', 'version_diff_display',
                'date_of_creation', 'date_of_change',
                'deadline_version', 'reschedule_count',
            )
        }),
    )

    def get_exclude(self, request, obj=None):
        excl = list(super().get_exclude(request, obj) or [])
        for name in (
            'control_status', 'control_date', 'route',
            'reschedule_request_reason', 'reschedule_request_date',
        ):
            if name not in excl:
                excl.append(name)
        return excl

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for name in (
                "target_deadline_display",
                "hard_deadline_display",
            ):
                if name not in fields:
                    fields.append(name)
            if request.user.id != obj.author_id and "comment" not in fields:
                fields.append("comment")
            if request.user.id != obj.author_id and "is_urgent" not in fields:
                fields.append("is_urgent")
        return fields

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.control_status in WorkAssignment.TERMINAL_STATUSES:
            return False
        return super().has_change_permission(request, obj)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        rename = {
            "target_deadline": "target_deadline_display",
            "hard_deadline": "hard_deadline_display",
        }
        drop = {"requires_hard_deadline"}
        new_fieldsets = []
        for title, opts in fieldsets:
            opts = dict(opts)
            new_fields = []
            for f in opts.get("fields", ()):
                if isinstance(f, (tuple, list)):
                    sub = tuple(rename.get(x, x) for x in f if x not in drop)
                    if sub:
                        new_fields.append(sub)
                else:
                    if f in drop:
                        continue
                    new_fields.append(rename.get(f, f))
            opts["fields"] = tuple(new_fields)
            new_fieldsets.append((title, opts))
        return new_fieldsets

    @staticmethod
    def _readonly_date_input(value):
        if value in (None, ""):
            text = ""
        elif hasattr(value, "strftime"):
            text = value.strftime("%d.%m.%Y")
        else:
            text = str(value)
        return format_html(
            '<input type="text" value="{}" disabled '
            'style="background:var(--body-bg);color:var(--body-fg);'
            'border:1px solid var(--border-color);padding:4px 6px;'
            'border-radius:4px;width:160px;cursor:not-allowed;opacity:1;">',
            text,
        )

    @admin.display(description="Целевой срок выполнения")
    def target_deadline_display(self, obj):
        return self._readonly_date_input(obj.target_deadline)

    @admin.display(description="Дедлайн")
    def hard_deadline_display(self, obj):
        return self._readonly_date_input(obj.hard_deadline)

    @admin.display(description="Статус выполнения / Результат")
    def control_status_display(self, obj):
        if not obj or not obj.pk or not obj.control_status:
            return "—"
        return _render_status_circle(obj.control_status)

    @admin.display(description="Дата фиксации статуса")
    def control_date_display(self, obj):
        if not obj or not obj.control_date:
            return "—"
        return timezone.localtime(obj.control_date).strftime("%d.%m.%Y %H:%M:%S")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        post_id = request.GET.get("post")
        if post_id:
            initial["post"] = post_id
        return initial

    _VERSION_SKIP_FIELDS = frozenset({
        "id", "version", "version_diff",
        "author_id", "last_editor_id",
        "date_of_creation", "date_of_change",
        "wa_number", "deadline_version", "reschedule_count",
        "name",
    })

    def save_model(self, request, obj, form, change):
        user = request.user
        is_draft = "_addanother" in request.POST or (
            "_continue" in request.POST and not obj.executor_id
        )
        old_executor_id = None
        old_status = None

        if change:
            try:
                old = WorkAssignment.objects.get(pk=obj.pk)
                old_status = old.control_status
                old_executor_id = old.executor_id
                cur = obj.version or "0"
                try:
                    version_to = str(int(cur) + 1)
                except ValueError:
                    version_to = cur + "+"
                diff = _build_version_diff_block(
                    old_obj=old,
                    new_obj=obj,
                    model_cls=WorkAssignment,
                    skip_fields=self._VERSION_SKIP_FIELDS,
                    user=user,
                    version_to=version_to,
                )
                if diff:
                    existing = (obj.version_diff or "").strip()
                    obj.version_diff = (existing + "\n\n" + diff).strip() if existing else diff
                    obj.version = version_to
            except WorkAssignment.DoesNotExist:
                old_status = None

            obj.last_editor = user
            if is_draft:
                obj.executor = None
                obj.control_status = None
                obj.control_date = None
                obj.current_responsible = user
            else:
                if not old_status and obj.executor_id:
                    obj.control_status = WorkAssignment.STATUS_ASSIGNED
                    obj.control_date = timezone.now()
                elif obj.control_status and obj.control_status != old_status:
                    obj.control_date = timezone.now()
                obj.current_responsible = obj.executor
        else:
            obj.author = user
            obj.last_editor = user
            if is_draft:
                obj.executor = None
                obj.control_status = None
                obj.control_date = None
                obj.current_responsible = user
            else:
                if not obj.control_status:
                    obj.control_status = WorkAssignment.STATUS_ASSIGNED
                    obj.control_date = timezone.now()
                obj.current_responsible = obj.executor or user

        if obj.post_id:
            from .helpers import assign_wa_code_to_post, next_wa_number_for_post
            assign_wa_code_to_post(obj.post)
            if not obj.wa_number:
                obj.wa_number = next_wa_number_for_post(obj.post, exclude_pk=obj.pk)

        super().save_model(request, obj, form, change)

        if (
            not is_draft
            and obj.executor_id
            and obj.executor_id != old_executor_id
            and obj.executor_id != user.id
        ):
            from approvals.services import notify
            from approvals.models import Notification
            notify(
                obj.executor,
                "Вас назначили исполнителем рабочего задания",
                text=f"«{obj.name or obj.task or obj}» — срок: {obj.target_deadline:%d.%m.%Y}.",
                url=reverse("admin:blog_workassignment_change", args=[obj.pk]),
                kind=Notification.KIND_WORK,
            )

    def response_add(self, request, obj, post_url_continue=None):
        if "_addanother" in request.POST:
            return redirect(f"{reverse('admin:blog_workassignment_changelist')}?draft=yes")
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_addanother" in request.POST:
            return redirect(f"{reverse('admin:blog_workassignment_changelist')}?draft=yes")
        return super().response_change(request, obj)

    @staticmethod
    def _is_changelist_request(request):
        match = getattr(request, "resolver_match", None)
        return match is not None and match.url_name == "blog_workassignment_changelist"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self._is_changelist_request(request) and request.GET.get("draft") != "yes":
            qs = qs.exclude(executor__isnull=True)

        today = timezone.localdate()

        active_q = (
            Q(control_status__isnull=True)
            | Q(control_status__in=WorkAssignment.ACTIVE_STATUSES)
        )
        qs = qs.annotate(
            is_target_overdue_db=Case(
                When(
                    active_q & Q(target_deadline__lt=today),
                    then=True,
                ),
                default=False,
                output_field=BooleanField(),
            ),
            is_hard_overdue_db=Case(
                When(
                    active_q
                    & Q(hard_deadline__isnull=False)
                    & Q(hard_deadline__lt=today),
                    then=True,
                ),
                default=False,
                output_field=BooleanField(),
            ),
        )

        return qs

    @admin.display(description="Просрочен целевой срок")
    def overdue_target_flag(self, obj):
        overdue = getattr(obj, "is_target_overdue_db", None)
        if overdue is None:
            overdue = obj.is_target_overdue()
        if overdue:
            return mark_safe(
                _admin_warning_triangle_html(
                    title="Целевой срок выполнения просрочен",
                    color="#f0ad4e",
                )
            )
        return "—"

    @admin.display(description="Просрочен дедлайн")
    def overdue_hard_flag(self, obj):
        if not obj.hard_deadline:
            return "—"
        overdue = getattr(obj, "is_hard_overdue_db", None)
        if overdue is None:
            overdue = obj.is_hard_overdue()
        if overdue:
            return mark_safe(
                _admin_warning_triangle_html(
                    title="Дедлайн просрочен",
                    color="#E53935",
                )
            )
        return "—"

    @admin.display(description="Статус выполнения / Результат", ordering="control_status")
    def control_status_colored(self, obj):
        return _render_status_circle(obj.control_status)

    @admin.display(description="История изменений")
    def version_diff_display(self, obj):
        if not obj:
            return "—"
        return mark_safe(_render_version_diff(obj.version_diff or ""))

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:object_id>/reschedule/",
                self.admin_site.admin_view(self.reschedule_view),
                name="blog_workassignment_reschedule",
            ),
            path(
                "<int:object_id>/acknowledge/",
                self.admin_site.admin_view(self.acknowledge_view),
                name="blog_workassignment_acknowledge",
            ),
            path(
                "<int:object_id>/submit-review/",
                self.admin_site.admin_view(self.submit_review_view),
                name="blog_workassignment_submit_review",
            ),
            path(
                "<int:object_id>/close/",
                self.admin_site.admin_view(self.close_view),
                name="blog_workassignment_close",
            ),
            path(
                "<int:object_id>/return/",
                self.admin_site.admin_view(self.return_view),
                name="blog_workassignment_return",
            ),
            path(
                "<int:object_id>/request-reschedule/",
                self.admin_site.admin_view(self.request_reschedule_view),
                name="blog_workassignment_request_reschedule",
            ),
            path(
                "<int:object_id>/deny-reschedule/",
                self.admin_site.admin_view(self.deny_reschedule_view),
                name="blog_workassignment_deny_reschedule",
            ),
            path(
                "<int:object_id>/toggle-urgent/",
                self.admin_site.admin_view(self.toggle_urgent_view),
                name="blog_workassignment_toggle_urgent",
            ),
        ]
        return custom + urls

    @staticmethod
    def _wa_label(obj):
        return obj.wa_full_code or obj.name or (obj.task or "").strip()[:80] or str(obj)

    @staticmethod
    def _wa_result_attachments(obj):
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(WorkAssignment)
        return Attachment.objects.filter(content_type=ct, object_id=obj.pk, kind="result")

    @staticmethod
    def _wa_task_attachments(obj):
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(WorkAssignment)
        return Attachment.objects.filter(content_type=ct, object_id=obj.pk).exclude(kind="result")

    def _notify_wa(self, recipient, title, text, obj):
        if not recipient:
            return
        from approvals.services import notify
        from approvals.models import Notification
        notify(
            recipient,
            title,
            text=text,
            url=reverse("admin:blog_workassignment_change", args=[obj.pk]),
            kind=Notification.KIND_WORK,
        )

    def acknowledge_view(self, request, object_id: int):
        from django.shortcuts import redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)
        back = redirect("admin:approvals_cabinet")
        if request.user.id != obj.executor_id:
            messages.error(request, "Принять задачу в работу может только её исполнитель.")
            return back
        if obj.control_status != WorkAssignment.STATUS_ASSIGNED:
            messages.warning(request, "Задача уже не ожидает принятия.")
            return back
        if request.method != "POST":
            return back
        obj.control_status = WorkAssignment.STATUS_IN_PROGRESS
        obj.control_date = timezone.now()
        obj.current_responsible = obj.executor
        obj.last_editor = request.user
        obj.save(update_fields=[
            "control_status", "control_date", "current_responsible", "last_editor", "date_of_change",
        ])
        self._notify_wa(
            obj.author,
            "Исполнитель приступил к задаче",
            f"«{self._wa_label(obj)}» взята в работу.",
            obj,
        )
        messages.success(request, "Задача принята в работу.")
        return back

    def toggle_urgent_view(self, request, object_id: int):
        from django.shortcuts import redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)
        back = redirect("admin:approvals_cabinet")
        if request.user.id != obj.author_id:
            messages.error(request, "Повысить приоритет задачи может только её автор.")
            return back
        if obj.control_status not in (WorkAssignment.STATUS_ASSIGNED, WorkAssignment.STATUS_IN_PROGRESS):
            messages.warning(request, "Повысить приоритет можно, пока задача ожидает принятия или в работе.")
            return back
        if request.method != "POST":
            return back
        obj.is_urgent = not obj.is_urgent
        obj.save(update_fields=["is_urgent"])
        if obj.is_urgent:
            self._notify_wa(
                obj.executor,
                "Приоритет задачи повышен",
                f"«{self._wa_label(obj)}» отмечена автором как срочная.",
                obj,
            )
            messages.success(request, "Приоритет задачи повышен.")
        else:
            messages.success(request, "Повышенный приоритет снят.")
        return back

    def submit_review_view(self, request, object_id: int):
        from django.shortcuts import render, redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)
        back = redirect("admin:approvals_cabinet")
        if request.user.id != obj.executor_id:
            messages.error(request, "Сдать задачу может только её исполнитель.")
            return back
        if obj.control_status != WorkAssignment.STATUS_IN_PROGRESS:
            messages.warning(request, "Сдать на проверку можно только задачу в работе.")
            return back

        if request.method == "POST":
            form = WorkAssignmentSubmitReviewForm(request.POST, request.FILES)
            if form.is_valid():
                self._append_text(obj, "result_description", form.cleaned_data["result_description"])
                obj.control_status = WorkAssignment.STATUS_REVIEW
                obj.control_date = timezone.now()
                obj.current_responsible = obj.author
                obj.last_editor = request.user
                obj.returned_for_rework = False
                obj.save(update_fields=[
                    "result_description", "control_status", "control_date",
                    "current_responsible", "last_editor", "date_of_change",
                    "returned_for_rework",
                ])
                for uploaded in form.cleaned_data.get("file") or []:
                    Attachment.objects.create(content_object=obj, file=uploaded, kind="result")
                self._notify_wa(
                    obj.author,
                    "Задача сдана на проверку",
                    f"«{self._wa_label(obj)}» ожидает вашей проверки.",
                    obj,
                )
                messages.success(request, "Задача отправлена автору на проверку.")
                return back
        else:
            form = WorkAssignmentSubmitReviewForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": obj,
            "title": "Сдать задачу на проверку",
            "form": form,
            "object_id": object_id,
        }
        return render(request, "admin/blog/workassignment/submit_review.html", context)

    _CLOSE_STATUS_BY_CHOICE = {
        "partial": "partial",
        "not_done": "not_done",
    }
    _RESULT_TEXT = _WA_RESULT_TEXT

    @staticmethod
    def _append_text(obj, field_name, text, label=None):
        text = (text or "").strip()
        if not text:
            return
        ts = timezone.localtime().strftime("%d.%m.%Y %H:%M")
        header = f"{label} — {ts}" if label else ts
        entry = f"{header}\n{text}"
        existing = (getattr(obj, field_name) or "").strip()
        setattr(obj, field_name, (existing + "\n\n" + entry) if existing else entry)

    @classmethod
    def _append_comment(cls, obj, text, label=None):
        cls._append_text(obj, "comment", text, label=label)

    def close_view(self, request, object_id: int):
        from django.shortcuts import render, redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)
        back = redirect("admin:approvals_cabinet")
        if request.user.id != obj.author_id:
            messages.error(request, "Закрыть задачу может только её автор.")
            return back
        if obj.control_status not in WorkAssignment.ACTIVE_STATUSES:
            messages.warning(request, "Эта задача уже закрыта.")
            return back

        if request.method == "POST":
            form = WorkAssignmentCloseForm(request.POST)
            if form.is_valid():
                choice = form.cleaned_data["result"]
                comment = form.cleaned_data.get("comment", "").strip()
                if choice == "done":
                    status = "rescheduled" if obj.reschedule_count else "on_time"
                else:
                    status = self._CLOSE_STATUS_BY_CHOICE[choice]
                obj.control_status = status
                obj.control_date = timezone.now()
                obj.result = self._RESULT_TEXT.get(status)
                obj.current_responsible = obj.author
                obj.last_editor = request.user
                fields = [
                    "control_status", "control_date", "result",
                    "current_responsible", "last_editor", "date_of_change",
                ]
                if comment:
                    self._append_comment(obj, comment, label=self._RESULT_TEXT.get(status))
                    fields.append("comment")
                obj.save(update_fields=fields)
                self._notify_wa(
                    obj.executor,
                    "Задача проверена и закрыта",
                    f"«{self._wa_label(obj)}»: {self._RESULT_TEXT.get(status)}."
                    + (f" Комментарий: {comment}" if comment else ""),
                    obj,
                )
                messages.success(
                    request,
                    f"Задача закрыта со статусом «{self._RESULT_TEXT.get(status)}».",
                )
                return back
        else:
            form = WorkAssignmentCloseForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": obj,
            "title": "Проверить и закрыть задачу",
            "form": form,
            "object_id": object_id,
            "rescheduled_note": bool(obj.reschedule_count),
            "result_attachments": self._wa_result_attachments(obj),
            "task_attachments": self._wa_task_attachments(obj),
        }
        return render(request, "admin/blog/workassignment/close.html", context)

    def return_view(self, request, object_id: int):
        from django.shortcuts import render, redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)
        back = redirect("admin:approvals_cabinet")
        if request.user.id != obj.author_id:
            messages.error(request, "Вернуть задачу может только её автор.")
            return back
        if obj.control_status != WorkAssignment.STATUS_REVIEW:
            messages.warning(request, "Вернуть на доработку можно только задачу на проверке.")
            return back

        if request.method == "POST":
            form = WorkAssignmentReturnForm(request.POST)
            if form.is_valid():
                comment = form.cleaned_data.get("comment", "").strip()
                obj.control_status = WorkAssignment.STATUS_IN_PROGRESS
                obj.control_date = timezone.now()
                obj.current_responsible = obj.executor
                obj.last_editor = request.user
                obj.returned_for_rework = True
                fields = [
                    "control_status", "control_date", "current_responsible", "last_editor", "date_of_change",
                    "returned_for_rework",
                ]
                if comment:
                    self._append_comment(obj, comment, label="Отказано в приёмке (возврат на доработку)")
                    fields.append("comment")
                obj.save(update_fields=fields)
                self._notify_wa(
                    obj.executor,
                    "Задача возвращена на доработку",
                    f"«{self._wa_label(obj)}» возвращена автором."
                    + (f" Комментарий: {comment}" if comment else ""),
                    obj,
                )
                messages.success(request, "Задача возвращена исполнителю на доработку.")
                return back
        else:
            form = WorkAssignmentReturnForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": obj,
            "title": "Вернуть задачу на доработку",
            "form": form,
            "object_id": object_id,
            "result_attachments": self._wa_result_attachments(obj),
            "task_attachments": self._wa_task_attachments(obj),
        }
        return render(request, "admin/blog/workassignment/return.html", context)

    def reschedule_view(self, request, object_id: int):
        from django.shortcuts import render, redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)

        next_param = request.POST.get("next") or request.GET.get("next")

        if request.user.id != obj.author_id:
            messages.error(request, "Перенести срок может только автор рабочего задания.")
            if next_param == "cabinet":
                return redirect("admin:approvals_cabinet")
            return redirect("admin:blog_workassignment_changelist")

        was_pending_approval = obj.control_status == WorkAssignment.STATUS_RESCHEDULE_PENDING

        if request.method == "POST":
            form = RescheduleAdminForm(request.POST)
            if form.is_valid():
                try:
                    assignment = WorkAssignmentService.reschedule_deadline(
                        obj,
                        new_target_deadline=form.cleaned_data.get("new_target_deadline"),
                        new_hard_deadline=form.cleaned_data.get("new_hard_deadline"),
                        reason=form.cleaned_data.get("reason", ""),
                        user=request.user if request.user.is_authenticated else None,
                        expected_deadline_version=form.cleaned_data["expected_deadline_version"],
                    )
                except ValueError as e:
                    messages.error(request, str(e))
                except RuntimeError as e:
                    messages.error(request, str(e))  # конфликт версий
                else:
                    if was_pending_approval:
                        assignment.control_status = WorkAssignment.STATUS_IN_PROGRESS
                        assignment.reschedule_request_reason = ""
                        assignment.reschedule_request_date = None
                        assignment.current_responsible = assignment.executor
                        assignment.control_date = timezone.now()
                        assignment.last_editor = request.user
                        assignment.save(update_fields=[
                            "control_status", "reschedule_request_reason", "reschedule_request_date",
                            "current_responsible", "control_date", "last_editor", "date_of_change",
                        ])
                        self._notify_wa(
                            assignment.executor,
                            "Перенос срока согласован",
                            f"«{self._wa_label(assignment)}»: автор согласовал перенос срока.",
                            assignment,
                        )
                    messages.success(request, "Срок успешно перенесён.")
                    if next_param == "cabinet":
                        return redirect("admin:approvals_cabinet")
                    return redirect(f"../change/")
        else:
            initial = {
                "new_target_deadline": obj.reschedule_request_date or obj.target_deadline,
                "requires_hard_deadline": bool(obj.hard_deadline),
                "new_hard_deadline": obj.hard_deadline,
                "expected_deadline_version": obj.deadline_version,
            }
            if was_pending_approval and obj.reschedule_request_reason:
                initial["reason"] = obj.reschedule_request_reason
            form = RescheduleAdminForm(initial=initial)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": obj,
            "title": "Перенести срок",
            "form": form,
            "object_id": object_id,
            "has_view_permission": self.has_view_permission(request, obj),
            "has_change_permission": self.has_change_permission(request, obj),
            "next_param": next_param,
        }
        return render(request, "admin/blog/workassignment/reschedule.html", context)

    def request_reschedule_view(self, request, object_id: int):
        from django.shortcuts import render, redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)
        back = redirect("admin:approvals_cabinet")
        if request.user.id != obj.executor_id:
            messages.error(request, "Запросить перенос срока может только исполнитель.")
            return back
        if obj.control_status not in (WorkAssignment.STATUS_ASSIGNED, WorkAssignment.STATUS_IN_PROGRESS):
            messages.warning(request, "Запросить перенос срока можно только для задачи в работе.")
            return back

        if request.method == "POST":
            form = WorkAssignmentRescheduleRequestForm(request.POST)
            if form.is_valid():
                obj.control_status = WorkAssignment.STATUS_RESCHEDULE_PENDING
                obj.reschedule_request_reason = form.cleaned_data["reason"]
                obj.reschedule_request_date = form.cleaned_data["desired_date"]
                obj.current_responsible = obj.author
                obj.control_date = timezone.now()
                obj.last_editor = request.user
                obj.save(update_fields=[
                    "control_status", "reschedule_request_reason", "reschedule_request_date",
                    "current_responsible", "control_date", "last_editor", "date_of_change",
                ])
                self._notify_wa(
                    obj.author,
                    "Запрос на перенос срока",
                    f"«{self._wa_label(obj)}»: исполнитель просит перенести срок на "
                    f"{obj.reschedule_request_date:%d.%m.%Y}.",
                    obj,
                )
                messages.success(request, "Запрос на перенос срока отправлен автору.")
                return back
        else:
            form = WorkAssignmentRescheduleRequestForm(initial={"desired_date": obj.target_deadline})

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": obj,
            "title": "Запрос переноса срока задачи",
            "form": form,
            "object_id": object_id,
        }
        return render(request, "admin/blog/workassignment/request_reschedule.html", context)

    def deny_reschedule_view(self, request, object_id: int):
        from django.shortcuts import redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)
        back = redirect("admin:approvals_cabinet")
        if request.user.id != obj.author_id:
            messages.error(request, "Отказать в переносе срока может только автор рабочего задания.")
            return back
        if obj.control_status != WorkAssignment.STATUS_RESCHEDULE_PENDING:
            messages.warning(request, "Эта задача не ожидает согласования переноса срока.")
            return back
        if request.method != "POST":
            return back
        obj.control_status = WorkAssignment.STATUS_IN_PROGRESS
        obj.reschedule_request_reason = ""
        obj.reschedule_request_date = None
        obj.current_responsible = obj.executor
        obj.control_date = timezone.now()
        obj.last_editor = request.user
        obj.save(update_fields=[
            "control_status", "reschedule_request_reason", "reschedule_request_date",
            "current_responsible", "control_date", "last_editor", "date_of_change",
        ])
        self._notify_wa(
            obj.executor,
            "Отказано в переносе срока",
            f"«{self._wa_label(obj)}»: автор отказал в переносе срока.",
            obj,
        )
        messages.success(request, "В переносе срока отказано, задача возвращена исполнителю.")
        return back

@admin.register(WorkAssignmentDeadlineChange)
class WorkAssignmentDeadlineChangeAdmin(admin.ModelAdmin):
    list_display = ("id","assignment","changed_by","changed_at", "old_target_deadline","new_target_deadline", "old_hard_deadline","new_hard_deadline")
    list_filter = ("changed_by","changed_at")
    search_fields = ("assignment__name","reason")

@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")

    def has_module_permission(self, request):
        return False


class RouteProcessInline(admin.TabularInline):
    model = RouteProcess
    extra = 0
    autocomplete_fields = ("process",)
    ordering = ("order",)



@admin.register(ApprovalDocumentWorkflow)
class ApprovalDocumentWorkflowAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "last_editor", "date_of_change")
    search_fields = ("name", "author__username", "last_editor__username")
    autocomplete_fields = ("author", "last_editor")


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "author", "current_responsible", "date_of_change")
    list_filter = ("access_level",)
    search_fields = ("name",)
    inlines = [RouteProcessInline]
    autocomplete_fields = ("author", "last_editor", "current_responsible", "check_document", "approval_document")

    def sequence_preview(self, obj: Route):
        # «IT → Тех → Нормо» — просто подсказка
        steps = (obj.routeprocess_set
                 .select_related("process")
                 .order_by("order")
                 .values_list("process__name", flat=True))
        return " → ".join(steps) if steps else "—"
    sequence_preview.short_description = "Последовательность"

    def visible_reviewer(self, obj: Route):
        """
        показывает ТОЛЬКО текущего проверяющего по связанному workflow (Route.check_document).
        идея: пока первый шаг не подписан — виден только его юзер;
              после подписи — виден следующий.
        """
        wf = obj.check_document
        if not wf:
            return "—"
        code = first_incomplete_step_code(obj, wf)
        if not code:
            return "—"
        user = wf_step_responsible(wf, code)
        return getattr(user, "get_username", lambda: str(user))()
    visible_reviewer.short_description = "Текущий проверяющий"


# ==== CHECK DOCUMENT WORKFLOW ====

class ReturnReasonForm(forms.Form):
    """простая форма для ввода причины возврата"""
    reason = forms.CharField(
        label="Причина возврата", widget=forms.Textarea(attrs={"rows": 4}), required=True
    )


@admin.register(CheckDocumentWorkflow)
class CheckDocumentWorkflowAdmin(admin.ModelAdmin):
    list_display = ("current_step_display",          # вычисляемый «Текущий шаг»
        "current_reviewer_display",      # вычисляемый «Проверяющий сейчас»
        "it_responsible_display",        # ответственные по этапам (ниже методы)
        "tech_responsible_display", "m3d_responsible_display", "norm_responsible_display", "date_of_change")
    search_fields = ("desig_or_name_document", "types_check_document", "author__username", "last_editor__username", "current_responsible__username", "check_it_requirements_responsible__username", "check_technical_requirements_responsible__username", "check_3D_model_responsible__username", "norm_control_responsible__username")
    list_filter = ("process_sequence", "check_it_requirements", "check_technical_requirements", "check_3D_model", "norm_control")
    autocomplete_fields = ("author", "last_editor", "current_responsible")

    # ---- служебное: определяем текущий шаг по первому НЕподписанному в маршруте ----
    def _current_code(self, obj: CheckDocumentWorkflow) -> str | None:
        route = obj.routes.first()   # WF <- Route (related_name='routes' со стороны Route.check_document)
        if not route:
            return None
        return first_incomplete_step_code(route, obj)

    # ---- вычисляемые колонки ----
    def current_step_display(self, obj):
        return self._current_code(obj) or "—"
    current_step_display.short_description = "Текущий шаг"

    def current_reviewer_display(self, obj):
        code = self._current_code(obj)
        if not code:
            return "—"
        user = wf_step_responsible(obj, code)
        return getattr(user, "get_username", lambda: str(user))() if user else "—"
    current_reviewer_display.short_description = "Проверяющий сейчас"

    # ---- вывод ответственных с подсветкой текущего шага ----
    def _fmt_user(self, user, highlight: bool):
        if not user:
            return "—"
        text = getattr(user, "get_username", lambda: str(user))()
        return format_html("<b>{}</b>", text) if highlight else text

    def it_responsible_display(self, obj):
        u = getattr(obj, "check_it_requirements_responsible", None)
        return self._fmt_user(u, self._current_code(obj) == "it_requirements")
    it_responsible_display.short_description = "IT"

    def tech_responsible_display(self, obj):
        u = getattr(obj, "check_technical_requirements_responsible", None)
        return self._fmt_user(u, self._current_code(obj) == "tech_requirements")
    tech_responsible_display.short_description = "Техтреб."

    def m3d_responsible_display(self, obj):
        u = getattr(obj, "check_3D_model_responsible", None)
        # если код процесса для 3D у тебя другой — поменяй сравнение
        return self._fmt_user(u, self._current_code(obj) == "model3d_check")
    m3d_responsible_display.short_description = "3D"

    def norm_responsible_display(self, obj):
        u = getattr(obj, "norm_control_responsible", None)
        return self._fmt_user(u, self._current_code(obj) == "norm_control")
    norm_responsible_display.short_description = "Нормоконтроль"

    # ---- ACTION: Подтвердить текущий шаг ----
    @admin.action(description="Подтвердить текущий шаг (подписать) и передать далее")
    def confirm_current_step(self, request, queryset):
        """
        1) ставим ..._signature = True для текущего шага
        2) назначаем current_responsible = ответственный следующего шага (если есть)
        """
        updated = 0
        for wf in queryset:
            route = wf.routes.first()
            if not route:
                continue
            cur = first_incomplete_step_code(route, wf)
            if not cur:
                continue  # все шаги уже закрыты
            # 1) подписываем текущий шаг
            sig_field = PROCESS_FIELD_MAP.get(cur, {}).get("signature")
            if sig_field:
                setattr(wf, sig_field, True)
            # 2) находим следующего и назначаем ответственным
            nxt = next_step_code_after(route, cur)
            next_user = wf_step_responsible(wf, nxt) if nxt else None
            if next_user:
                wf.current_responsible = next_user
            wf.date_of_change = timezone.now()
            wf.save()
            updated += 1
        self.message_user(request, f"Подтверждено и передано дальше: {updated}", messages.SUCCESS)

    # ---- Кнопка/роут «Вернуть отправителю» с причиной ----
    change_form_template = "admin/blog/checkworkflow_changeform.html"  # добавим кнопку на форме

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/return/",
                self.admin_site.admin_view(self.return_to_author_view),
                name="blog_checkdocumentworkflow_return",
            ),
        ]
        return custom + urls

    def return_to_author_view(self, request, object_id):
        """
        страница с формой "причина возврата" → сохраняем в соответствующий ..._comment
        и назначаем current_responsible = author (или кому нужно)
        """
        wf = self.get_object(request, object_id)
        if not wf:
            self.message_user(request, "Объект не найден", messages.ERROR)
            return redirect("admin:blog_checkdocumentworkflow_changelist")

        route = wf.routes.first()
        cur = first_incomplete_step_code(route, wf) if route else None
        if request.method == "POST":
            form = ReturnReasonForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data["reason"]
                # пишем причину в комментарий текущего шага
                if cur:
                    wf_step_set_comment(wf, cur, reason)
                # назначаем "отправителю" (здесь — автору WF; при желании можно route.author)
                wf.current_responsible = wf.author
                wf.date_of_change = timezone.now()
                wf.save()
                self.message_user(request, "Документ возвращён отправителю", messages.SUCCESS)
                return redirect("admin:blog_checkdocumentworkflow_change", object_id=wf.pk)
        else:
            form = ReturnReasonForm()

        context = dict(
            self.admin_site.each_context(request),
            title="Вернуть отправителю",
            original=wf,
            form=form,
            current_step=cur or "—",
        )
        return render(request, "admin/blog/return_to_author.html", context)

    @admin.action(description="Вернуть отправителю (указать причину на форме объекта)")
    def return_to_author(self, request, queryset):
        """
        экшен-подсказка: для единичного объекта переадресуем на форму возврата,
        для мульти — выдадим подсказку
        """
        if queryset.count() != 1:
            self.message_user(
                request, "Выберите один объект и нажмите кнопку 'Вернуть отправителю' на его форме.",
                messages.WARNING
            )
            return
        obj = queryset.first()
        return redirect("admin:blog_checkdocumentworkflow_return", object_id=obj.pk)

    @admin.register(Attachment)
    class AttachmentAdmin(admin.ModelAdmin):
        list_display = ('id', 'file')

#admin.site.register(SharedRepository, SoftwareProductAdmin)

class IndependentDocumentAcceptSignatureInline(admin.TabularInline):
    """Inline для множественных подписей ознакомления"""
    model = IndependentDocumentAcceptSignature
    extra = 1
    fields = ['signature_file', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_at']
    verbose_name = "Подписи ознакомления"

@admin.register(SharedRepository)
class SharedRepositoryAdmin(admin.ModelAdmin):
    actions = ["send_to_approval_action", "send_to_acknowledgment_action"]

    @admin.action(description="Отправить на согласование")
    def send_to_approval_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=independent&mode=approval&ids={ids}"
        return redirect(url)

    @admin.action(description="Отправить на ознакомление")
    def send_to_acknowledgment_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=independent&mode=ack&ids={ids}"
        return redirect(url)

    list_display = [
        'display_document_title',
        'display_approval',
        'display_date_approval',
        'display_accept',
        'display_author',
        'display_date_of_change',
        'display_version',
        'display_uploaded_file',
        'display_lu_lo_sheets',
        'display_document_purpose',
        'display_note',
        'display_related_documents',
        'display_related_sharedrepository',
    ]

    list_filter = [
        'category',
        'approval',
        'author',
        'current_responsible',
        'date_of_creation',
    ]

    search_fields = [
        'document_title',
        'document_purpose',
        'note',
        'id',
    ]

    readonly_fields = [
        'date_of_creation',
        'date_of_change',
        'last_editor',
        'author',
        'display_file_list',
        'display_related_qms_documents_list',
        'display_related_shared_documents_list',
        'approval_document',
        'acquaintance_document',
    ]

    filter_horizontal = ['related_documents','related_sharedrepository']

    inlines = [IndependentDocumentAcceptSignatureInline]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                #'id',
                'category',
                'document_title',
                'version',
                'uploaded_file',
                #'display_file_info',
                'document_purpose',
                'note',
            )
        }),
        ('Утверждение', {
            'fields': (
                'approval',
                'signature_approval',
                'date_approval',
                'approval_document',
                'acquaintance_document',
            )
        }),
        ('Ознакомление', {
            'fields': (
                'accept',
                #'signature_accept',
            )
        }),
        ('Связанные документы', {
            'fields': ('related_documents','related_sharedrepository'),
        }),
        ('Пользователи системы', {
            'fields': (
                'author',
                'last_editor',
                'current_responsible',
            )
        }),
        ('Системные даты', {
            'fields': (
                'date_of_creation',
                'date_of_change',
            )
        }),
        ('Файлы документа', {
            'fields': ('display_file_list',),
        }),
    )

    def display_related_documents(self, obj):
        """Связанные документы СМК — списком, каждый с новой строки"""
        docs = obj.related_documents.all()
        if not docs:
            return "—"
        fmt = "<br>".join(["{}"] * len(docs))
        return format_html(fmt, *[doc.document_title for doc in docs])

    display_related_documents.short_description = 'Связанные документы СМК'

    def display_related_qms_documents(self, obj):
        """Отображение количества связанных документов СМК"""
        count = obj.related_qms_documents.count()
        if count:
            return format_html(
                '<span style="color: #79aec8;">📄 Документов СМК: {}</span>',
                count
            )
        return "—"

    display_related_qms_documents.short_description = 'Связанные документы СМК'

    def display_related_qms_documents_list(self, obj):
        """Список связанных документов СМК для детального просмотра"""
        docs = obj.related_qms_documents.all()
        if not docs.exists():
            return "Нет связанных документов СМК"

        html = '<div style="background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px;">'
        html += '<h4>📄 СВЯЗАННЫЕ ДОКУМЕНТЫ СМК</h4>'
        html += '<ul style="margin-top: 5px;">'

        for doc in docs:
            url = reverse('admin:qmsdocument_qmsdocument_change', args=[doc.pk])
            html += f'<li style="margin-bottom: 5px;">🔗 <a href="{url}" target="_blank">{doc.document_title}</a></li>'

        html += '</ul></div>'
        return format_html(html)

    display_related_qms_documents_list.short_description = 'Связанные документы СМК'

    def display_related_sharedrepository(self, obj):
        """Связанные отдельные документы — списком, каждый с новой строки"""
        docs = obj.related_sharedrepository.all()
        if not docs:
            return "—"
        fmt = "<br>".join(["{}"] * len(docs))
        return format_html(fmt, *[doc.document_title for doc in docs])

    display_related_sharedrepository.short_description = 'Связанные отдельные документы'

    def display_related_shared_documents(self, obj):
        """Отображение количества связанных отдельных документов"""
        count = obj.related_shared_documents.count()
        if count:
            return format_html(
                '<span style="color: #79aec8;">📄 Отдельных документов: {}</span>',
                count
            )
        return "—"

    display_related_shared_documents.short_description = 'Связанные отдельные документы'

    def display_related_shared_documents_list(self, obj):
        """Список связанных отдельных документов для детального просмотра"""
        docs = obj.related_shared_documents.all()
        if not docs.exists():
            return "Нет связанных отдельных документов"

        html = '<div style="background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px;">'
        html += '<h4>📄 СВЯЗАННЫЕ ОТДЕЛЬНЫХ ДОКУМЕНТЫ </h4>'
        html += '<ul style="margin-top: 5px;">'

        for doc in docs:
            url = reverse('admin:shareddocument_shareddocument_change', args=[doc.pk])
            html += f'<li style="margin-bottom: 5px;">🔗 <a href="{url}" target="_blank">{doc.document_title}</a></li>'

        html += '</ul></div>'
        return format_html(html)

    display_related_qms_documents_list.short_description = 'Связанные отдельные документы'

    def display_id(self, obj):
        return obj.id

    display_id.short_description = 'ID'
    display_id.admin_order_field = 'id'

    def display_category(self, obj):
        """Отображение категории """
        return obj.get_category_display()

    display_category.short_description = 'Категория'
    display_category.admin_order_field = 'category'

    def display_document_title(self, obj):
        """Отображение названия документа """
        return obj.document_title

    display_document_title.short_description = 'Название документа'
    display_document_title.admin_order_field = 'document_title'

    def display_approval(self, obj):
        """Отображение утвердившего """
        if obj.approval:
            return obj.approval.username
        return "—"

    display_approval.short_description = 'Утвердил'
    display_approval.admin_order_field = 'approval__username'

    def display_date_approval(self, obj):
        """Отображение даты утверждения """
        if obj.date_approval:
            return obj.date_approval.strftime('%Y-%m-%d')
        return "—"

    display_date_approval.short_description = 'Дата утверждения'
    display_date_approval.admin_order_field = 'date_approval'

    def display_accept(self, obj):
        if obj.accept:
            return obj.get_accept_display()
        return "—"
    display_accept.short_description = 'Ознакомление'
    display_accept.admin_order_field = 'accept'


    def display_author(self, obj):
        return obj.author.username

    display_author.short_description = 'Автор'
    display_author.admin_order_field = 'author__username'

    def display_date_of_change(self, obj):
        """Отображение даты изменения """
        return obj.date_of_change.strftime('%Y-%m-%d %H:%M:%S')

    display_date_of_change.short_description = 'Дата изменения'
    display_date_of_change.admin_order_field = 'date_of_change'

    def display_current_responsible(self, obj):
        """Отображение ответственного """
        return obj.current_responsible.username

    display_current_responsible.short_description = 'Ответственный'
    display_current_responsible.admin_order_field = 'current_responsible__username'

    def display_version(self, obj):
        """Отображение версии """
        return obj.version

    display_version.short_description = 'Версия'
    display_version.admin_order_field = 'version'

    def display_uploaded_file(self, obj):
        """Отображение файла только ссылка"""
        if obj.uploaded_file:
            filename = obj.uploaded_file.name.split('/')[-1]
            return format_html(
                '<a href="{}" target="_blank" title="{}">{}</a>',
                obj.uploaded_file.url,
                filename,
                filename[:30] + '...' if len(filename) > 30 else filename
            )
        return "—"

    display_uploaded_file.short_description = 'Файл'

    @admin.display(description="ЛУ/ЛО")
    def display_lu_lo_sheets(self, obj):
        return _admin_lu_lo_sheets_column_html(obj)

    def display_document_purpose(self, obj):
        """Отображение назначения документа"""
        if obj.document_purpose:
            # Показываем текст полностью с переносом
            return format_html(
                '<div style="min-width: 150px; max-width: 600px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.document_purpose
            )
        return "—"

    display_document_purpose.short_description = 'Назначение'

    def display_note(self, obj):
        """Отображение примечания"""
        if obj.note:
            return format_html(
                '<div style="min-width: 150px; max-width: 600px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.note
            )
        return "—"

    display_note.short_description = 'Примечание'
    display_note.admin_order_field = 'note'

    def uploaded_file_info(self, obj):
        """Информация о файле для детального просмотра"""
        if obj.uploaded_file:
            return format_html(
                '<div style="background: #f0f0f0; padding: 10px; margin: 10px 0;">'
                '<p><strong>Имя файла:</strong> {}</p>'
                '<p><a href="{}" target="_blank" class="button">📥 Открыть файл</a></p>'
                '</div>',
                obj.uploaded_file.name,
                obj.uploaded_file.url
            )
        return "Файл не загружен"

    uploaded_file_info.short_description = 'Информация о файле'

    def save_model(self, request, obj, form, change):
        """Автоматическая установка пользователей при сохранении из админки"""
        if not change:  # Если это создание нового документа
            # Устанавливаем автора и последнего редактора как текущего пользователя
            obj.author = request.user
            obj.last_editor = request.user
            # Если current_responsible не указан, устанавливаем текущего пользователя
            if not obj.current_responsible:
                obj.current_responsible = request.user
        else:  # Редактирование существующего
            # Обновляем только последнего редактора
            obj.last_editor = request.user

        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        """Кастомизация формы в админке"""
        form = super().get_form(request, obj, **kwargs)

        # Устанавливаем help_text для полей как в ТЗ
        help_texts = {
            'id': 'Уникальное поле',
            'category': 'Значение по умолчанию "ОД"',
            'document_title': 'Уникальное поле. Все текстовые символы - 100 символов max',
            'approval': 'Имя пользователя системы (ссылка на User)',
            'signature_approval': 'Возможность подгрузить только один файл ЭЦП',
            'date_approval': 'Текст, до 20 символов. Значение по умолчанию "---"',
            'accept': 'ЭЦП',
            'author': 'Имя пользователя системы (ссылка на User)',
            'date_of_creation': 'Формат: YYYY-MM-DD HH:MI:SS',
            'last_editor': 'Имя пользователя системы (ссылка на User)',
            'date_of_change': 'Формат: YYYY-MM-DD HH:MI:SS',
            'current_responsible': 'Имя пользователя системы (ссылка на User)',
            'version': 'Цифры, 3 символа max. Значение по умолчанию: 1',
            'uploaded_file': 'Подгружаем только один файл',
            'document_purpose': 'Все текстовые символы - 5000 символов max',
            'note': 'Дополнительные заметки и комментарии',
        }

        for field_name, help_text in help_texts.items():
            if field_name in form.base_fields:
                form.base_fields[field_name].help_text = help_text

        return form

    def display_file_list(self, obj):
        """Список всех файлов документа (аналогично QMSDocument)"""
        html = '<div style="background: #f8f9fa; padding: 10px; margin: 10px 0;">'

        # Основной файл
        html += '<h4>Основной документ:</h4>'
        if obj.uploaded_file:
            filename = obj.uploaded_file.name.split('/')[-1]
            html += f'<p>📄 <a href="{obj.uploaded_file.url}" target="_blank">{filename}</a></p>'
        else:
            html += '<p>Не загружен</p>'

        # Подпись утверждения
        html += '<h4>Подпись утверждения:</h4>'
        if obj.signature_approval:
            filename = obj.signature_approval.name.split('/')[-1]
            html += f'<p>🖊️ <a href="{obj.signature_approval.url}" target="_blank">{filename}</a></p>'
        else:
            html += '<p>Не загружена</p>'

        # Подписи ознакомления
        signatures = obj.accept_signatures.all()
        if signatures.exists():
            html += '<h4>Подписи ознакомления:</h4><ul>'
            for sig in signatures:
                filename = sig.signature_file.name.split('/')[-1]
                html += f'<li>🖊️ <a href="{sig.signature_file.url}" target="_blank">{filename}</a>'
                if sig.uploaded_by:
                    html += f' <span style="color: #666;">(загрузил: {sig.uploaded_by.username})</span>'
                html += '</li>'
            html += '</ul>'
        else:
            html += '<h4>Подписи ознакомления:</h4><p>Нет загруженных подписей</p>'

        html += '</div>'
        return format_html(html)

    display_file_list.short_description = 'Файлы документа'

#@admin.register(IndependentDocumentAcceptSignature)
#class IndependentDocumentAcceptSignatureAdmin(admin.ModelAdmin):
  #  """Админка для подписей ознакомления"""
   # list_display = ['document', 'signature_file', 'uploaded_by', 'uploaded_at']
    #list_filter = ['uploaded_at', 'uploaded_by']
    #search_fields = ['document__document_title']


class KnowledgeBaseFileInline(admin.TabularInline):
    """Inline для множественных файлов"""
    model = KnowledgeBaseFile
    extra = 1
    fields = ['file', 'description', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_at']


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = [
        'title_short',
        'display_knowledge_group',
        'display_knowledge_apply',
        'display_author',
        #'display_files_count',
        'display_consumer_info',
        #'display_consumer_ticket_link',
        'display_document_contents_short',
        #'version',
        #'date_of_creation_short',
    ]

    list_filter = [
        'knowledge_group',
        'date_of_creation',
        'author',
        'consumer_customer',
    ]

    search_fields = [
        'title',
        'document_contents',
        'note',
    ]

    readonly_fields = [
        'date_of_creation',
        'date_of_change',
        'display_files_list',
        'last_editor',
        'author',
    ]

    filter_horizontal = ['knowledge_apply']  # Удобный виджет для ManyToMany

    inlines = [KnowledgeBaseFileInline]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'category',
                'title',
                'knowledge_group',
            )
        }),
        ('Связи', {
            'fields': (
                #'consumer',
                'consumer_customer',
                'consumer_ticket',
                'knowledge_apply',
            )
        }),
        ('Содержание', {
            'fields': (
                'document_contents',
                'note',
            )
        }),
        ('Пользователи системы', {
            'fields': (
                'author',
                'last_editor',
                'current_responsible',
            )
        }),
        ('Версия и системные даты', {
            'fields': (
                'version',
                'date_of_creation',
                'date_of_change',
                'display_files_list',
            )
        }),
    )

    def title_short(self, obj):
        """Краткое отображение названия"""
        if obj.title:
            return obj.title[:50] + '...' if len(obj.title) > 50 else obj.title
        return "—"

    title_short.short_description = 'Название'
    title_short.admin_order_field = 'title'

    def display_knowledge_group(self, obj):
        """Отображение группы знаний"""
        if obj.knowledge_group:
            return obj.get_knowledge_group_display()
        return "—"

    display_knowledge_group.short_description = 'Группа знаний'

    def display_knowledge_apply(self, obj):
        """Отображение применения знаний (список пользователей)"""
        users = obj.knowledge_apply.all()
        if users.exists():
            return ", ".join([user.username for user in users])
        return "—"

    display_knowledge_apply.short_description = 'Применение знаний/ практик'

    def display_author(self, obj):
        """Отображение автора"""
        if obj.author:
            return obj.author.username
        return "—"

    display_author.short_description = 'Автор'

    def display_consumer_info(self, obj):
        """Отображение информации о потребителе со ссылкой на его обращения"""
        # Показываем только если выбрана соответствующая группа знаний
        if obj.knowledge_group != 'lesson_consumer':
            return "—"

        # Информация о контрагенте
        if obj.consumer_customer:
            customer_url = reverse('admin:crm_customer_change', args=[obj.consumer_customer.pk])
            tickets_count = obj.consumer_customer.support_tickets.count()

            # Формируем HTML с контрагентом и ссылкой на обращения
            return format_html(
                '<div>'
                '<strong> </strong> <a href="{}" style="font-weight: bold;">{}</a><br>'
                '<a href="{}?customer__id__exact={}" style="font-size: 11px; color: #79aec8;">📞 Обращения ({})</a>'
                '</div>',
                customer_url,
                obj.consumer_customer.name_of_company,
                reverse('admin:crm_supportticket_changelist'),
                obj.consumer_customer.pk,
                tickets_count
            )
        else:
            return '<div><strong>Контрагент:</strong> <span style="color: red;">Не указан!</span></div>'

    display_consumer_info.short_description = 'Потребитель (контрагент)'

    def display_files_count(self, obj):
        """Количество файлов"""
        count = obj.attached_files.count()
        return f"{count} файл(ов)" if count > 0 else "—"

    display_files_count.short_description = 'Файлы'

    def display_document_contents_short(self, obj):
        """Краткое отображение содержания документа (последний столбец)"""
        if obj.document_contents:
            return format_html(
                '<div style="min-width: 250px; max-width: 400px; white-space: normal; word-wrap: break-word;">{}</div>',
                obj.document_contents[:100] + '...' if len(obj.document_contents) > 100 else obj.document_contents
            )
        return "—"

    display_document_contents_short.short_description = 'Содержание документа'

    def date_of_creation_short(self, obj):
        """Краткое отображение даты"""
        return obj.date_of_creation.strftime('%d.%m.%Y')

    date_of_creation_short.short_description = 'Дата'
    date_of_creation_short.admin_order_field = 'date_of_creation'

    def display_files_list(self, obj):
        """Список файлов для детального просмотра"""
        files = obj.attached_files.all()
        if not files.exists():
            return "Нет загруженных файлов"

        html = '<ul style="list-style-type: none; padding-left: 0;">'
        for file in files:
            filename = file.file.name.split('/')[-1]
            html += f'<li style="margin-bottom: 5px;">📄 <a href="{file.file.url}" target="_blank">{filename}</a>'
            if file.description:
                html += f' <span style="color: #666;">- {file.description}</span>'
            if file.uploaded_by:
                html += f' <span style="color: #999; font-size: 0.9em;">(загрузил: {file.uploaded_by.username})</span>'
            html += '</li>'
        html += '</ul>'
        return format_html(html)

    display_files_list.short_description = 'Загруженные файлы'

    def save_model(self, request, obj, form, change):
        """Автоматическая установка пользователей при сохранении"""
        if not change:  # Создание
            obj.author = request.user
            obj.last_editor = request.user
            if not obj.current_responsible:
                obj.current_responsible = request.user
        else:  # Редактирование
            # Обновляем только последнего редактора, автор не меняется
            obj.last_editor = request.user

        # Если группа знаний не lesson_consumer, очищаем поля потребителя и обращения
        if obj.knowledge_group != 'lesson_consumer':
            obj.consumer_customer = None
            obj.consumer_ticket = None

        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        """Кастомизация формы для динамической валидации"""
        form = super().get_form(request, obj, **kwargs)

        # Добавляем классы для полей
        if 'consumer_customer' in form.base_fields:
            form.base_fields['consumer_customer'].required = False
        if 'consumer_ticket' in form.base_fields:
            form.base_fields['consumer_ticket'].required = False

        return form


#@admin.register(KnowledgeBaseFile)
#class KnowledgeBaseFileAdmin(admin.ModelAdmin):
 #   list_display = ['knowledge_base', 'file', 'description', 'uploaded_by', 'uploaded_at']
  #  list_filter = ['uploaded_at', 'uploaded_by']
   # search_fields = ['knowledge_base__title', 'description']
    #readonly_fields = ['uploaded_at']


class QMSDocumentAcceptSignatureInline(admin.TabularInline):
    """Inline для множественных подписей ознакомления"""
    model = QMSDocumentAcceptSignature
    extra = 1
    fields = ['signature_file', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_at']


@admin.register(QMSDocument)
class QMSDocumentAdmin(admin.ModelAdmin):
    actions = ["send_to_approval_action", "send_to_acknowledgment_action"]

    @admin.action(description="Отправить на согласование")
    def send_to_approval_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=qms&mode=approval&ids={ids}"
        return redirect(url)

    @admin.action(description="Отправить на ознакомление")
    def send_to_acknowledgment_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=qms&mode=ack&ids={ids}"
        return redirect(url)

    list_display = [
        'display_document_title',
        'display_category',
        'change_number',
        'display_approval',
        'display_date_approval',
        'display_accept',
        'display_uploaded_file',
        'display_lu_lo_sheets',
        'display_review_date',
        'display_review_status',
        'document_purpose',
        'display_related_documents',
        'display_related_qms_documents',
        'remark_note'
    ]

    list_filter = [
        'category',
        'date_approval',
        'review_date',
        'author',
    ]

    search_fields = [
        'document_title',
        'document_purpose',
        'note',
        'id',
    ]

    readonly_fields = [
        'date_of_creation',
        'date_of_change',
        'display_files_list',
        'last_editor',
        'author',
        'display_related_shared_documents_list',
        'display_related_qms_documents_list',
        'approval_document',
        'acquaintance_document',
    ]

    filter_horizontal = ['related_documents','related_qms_documents']

    inlines = [QMSDocumentAcceptSignatureInline]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'category',
                'document_title',
                'change_number',
                'version',
            )
        }),
        ('Утверждение', {
            'fields': (
                'approval',
                'approval_signature',
                'date_approval',
                'approval_document',
                'acquaintance_document',
            )
        }),
        ('Ознакомление', {
            'fields': (
                'accept',
            )
        }),
        ('Документ', {
            'fields': (
                'uploaded_file',
                'document_purpose',
            )
        }),
        ('Связанные документы', {
            'fields': ('related_documents','related_qms_documents'),
        }),
        ('Дата планового пересмотра', {
            'fields': (
                'review_date',
            )
        }),
        ('Пользователи системы', {
            'fields': (
                'author',
                'last_editor',
                'current_responsible',
            )
        }),
        ('Дополнительно', {
            'fields': (
                'note',
            )
        }),
        ('Системные даты', {
            'fields': (
                'date_of_creation',
                'date_of_change',
                'display_files_list',
            )
        }),
    )

    def display_related_documents(self, obj):
        """Связанные отдельные документы — списком, каждый с новой строки"""
        docs = obj.related_documents.all()
        if not docs:
            return "—"
        fmt = "<br>".join(["{}"] * len(docs))
        return format_html(fmt, *[doc.document_title for doc in docs])

    display_related_documents.short_description = 'Связанные отдельные документы'

    def display_related_shared_documents(self, obj):
        """Отображение количества связанных отдельных документов"""
        count = obj.related_shared_documents.count()
        if count:
            return format_html(
                '<span style="color: #79aec8;">📄 Отдельных документов: {}</span>',
                count
            )
        return "—"

    display_related_shared_documents.short_description = 'Связанные отдельные документы'

    def display_related_shared_documents_list(self, obj):
        """Список связанных отдельных документов для детального просмотра"""
        docs = obj.related_shared_documents.all()
        if not docs.exists():
            return "Нет связанных отдельных документов"

        html = '<div style="background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px;">'

        html += '<h4>📄 СВЯЗАННЫЕ ОТДЕЛЬНЫЕ ДОКУМЕНТЫ</h4>'
        html += '<ul style="margin-top: 5px;">'
        
        for doc in docs:
            url = reverse('admin:shared_repository_sharedrepository_change', args=[doc.pk])
            html += f'<li style="margin-bottom: 5px;">🔗 <a href="{url}" target="_blank">{doc.document_title}</a></li>'

        html += '</ul></div>'
        return format_html(html)

    display_related_shared_documents_list.short_description = 'Связанные отдельные документы'

    def display_related_qms_documents(self, obj):
        """Связанные документы СМК — списком, каждый с новой строки"""
        docs = obj.related_qms_documents.all()
        if not docs:
            return "—"
        fmt = "<br>".join(["{}"] * len(docs))
        return format_html(fmt, *[doc.document_title for doc in docs])

    display_related_qms_documents.short_description = 'Связанные документы СМК'


    def display_related_qms_documents_list(self, obj):
        """Список связанных документов СМК для детального просмотра"""
        docs = obj.related_qms_documents.all()
        if not docs.exists():
            return "Нет связанных документов СМК"

        html = '<div style="background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px;">'
        html += '<h4>📄 СВЯЗАННЫЕ ДОКУМЕНТЫ СМК</h4>'
        html += '<ul style="margin-top: 5px;">'

        for doc in docs:
            url = reverse('admin:qmsdocument_qmsdocument_change', args=[doc.pk])
            html += f'<li style="margin-bottom: 5px;">🔗 <a href="{url}" target="_blank">{doc.document_title}</a></li>'

        html += '</ul></div>'
        return format_html(html)

    display_related_qms_documents_list.short_description = 'Связанные документы СМК'

    def display_category(self, obj):
        """Отображение категории"""
        return obj.get_category_display() if obj.category else "—"

    display_category.short_description = 'Категория'
    display_category.admin_order_field = 'category'

    def display_document_title(self, obj):
        """Отображение названия документа"""
        if obj.document_title:
            return format_html(
                '<div style="min-width: 200px; max-width: 400px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.document_title
            )
        return "—"

    display_document_title.short_description = 'Название документа'
    display_document_title.admin_order_field = 'document_title'

    def display_approval(self, obj):
        """Отображение утвердившего"""
        if obj.approval:
            return obj.approval.username
        return "—"

    display_approval.short_description = 'Утвердил'
    display_approval.admin_order_field = 'approval__username'

    def display_date_approval(self, obj):
        """Отображение даты утверждения"""
        if obj.date_approval:
            return obj.date_approval.strftime('%d.%m.%Y')
        return "—"

    display_date_approval.short_description = 'Дата утв.'

    def display_accept(self, obj):
        """Отображение ознакомления"""
        if obj.accept:
            return obj.get_accept_display()
        return "—"

    display_accept.short_description = 'Ознакомление'

    def display_version(self, obj):
        """Отображение версии"""
        return obj.version

    display_version.short_description = 'Версия'

    def display_uploaded_file(self, obj):
        """Отображение файла с иконкой"""
        if obj.uploaded_file:
            filename = obj.uploaded_file.name.split('/')[-1]
            return format_html(
                '<a href="{}" target="_blank" title="{}">📄 {}</a>',
                obj.uploaded_file.url,
                filename,
                filename[:20] + '...' if len(filename) > 20 else filename
            )
        return "—"

    display_uploaded_file.short_description = 'Файл'

    @admin.display(description="ЛУ/ЛО")
    def display_lu_lo_sheets(self, obj):
        return _admin_lu_lo_sheets_column_html(obj)

    def display_review_date(self, obj):
        """Отображение даты планового пересмотра"""
        if obj.review_date:
            return obj.review_date.strftime('%d.%m.%Y')
        return "—"
    display_review_date.short_description = 'Дата планового пересмотра'
    display_review_date.admin_order_field = 'review_date'

    def display_review_status(self, obj):
        """Отображение статуса Срока пересмотра истекает с предупреждением"""
        if not obj.review_date:
            return "—"

        if obj.is_review_overdue():
            return format_html(
                '<span style="color: red; font-weight: bold; white-space: nowrap;">⚠️ ПРОСРОЧЕН!</span>'
            )
        elif obj.is_review_approaching():
            days_left = (obj.review_date - timezone.now().date()).days
            return format_html(
                '<span style="color: orange; white-space: nowrap;">⚠️ Истекает через {} дн.</span>',
                days_left
            )
        return "—"
    display_review_status.short_description = 'Срок пересмотра истекает'

    def display_files_list(self, obj):
        """Список всех файлов для детального просмотра"""
        html = '<div style="background: #f8f9fa; padding: 10px; margin: 10px 0;">'

        # Основной файл
        html += '<h4>Основной документ:</h4>'
        if obj.uploaded_file:
            filename = obj.uploaded_file.name.split('/')[-1]
            html += f'<p>📄 <a href="{obj.uploaded_file.url}" target="_blank">{filename}</a></p>'
        else:
            html += '<p>Не загружен</p>'

        # Подпись утверждения
        html += '<h4>Подпись утверждения:</h4>'
        if obj.approval_signature:
            filename = obj.approval_signature.name.split('/')[-1]
            html += f'<p>🖊️ <a href="{obj.approval_signature.url}" target="_blank">{filename}</a></p>'
        else:
            html += '<p>Не загружена</p>'

        # Подписи ознакомления
        signatures = obj.accept_signatures.all()
        if signatures.exists():
            html += '<h4>Подписи ознакомления:</h4><ul>'
            for sig in signatures:
                filename = sig.signature_file.name.split('/')[-1]
                html += f'<li>🖊️ <a href="{sig.signature_file.url}" target="_blank">{filename}</a>'
                if sig.uploaded_by:
                    html += f' <span style="color: #666;">(загрузил: {sig.uploaded_by.username})</span>'
                html += '</li>'
            html += '</ul>'

        html += '</div>'
        return format_html(html)
    display_files_list.short_description = 'Файлы документа'

    def save_model(self, request, obj, form, change):
        """Автоматическая установка пользователей при сохранении"""
        if not change:  # Создание
            obj.author = request.user
            obj.last_editor = request.user
            if not obj.current_responsible:
                obj.current_responsible = request.user
        else:  # Редактирование
            obj.last_editor = request.user
        super().save_model(request, obj, form, change)

    def remark_note(self, obj):
        """Отображение примечания"""
        if obj.note:
            return format_html(
                '<div style="min-width: 150px; max-width: 600px; white-space: normal; word-wrap: break-word; padding: 5px;">{}</div>',
                obj.note
            )
        return "—"

    remark_note.short_description = 'Примечание'
    remark_note.admin_order_field = 'remark_note'


#@admin.register(QMSDocumentAcceptSignature)
#class QMSDocumentAcceptSignatureAdmin(admin.ModelAdmin):
 #   list_display = ['document', 'signature_file', 'uploaded_by', 'uploaded_at']
  #  list_filter = ['uploaded_at', 'uploaded_by']
   # search_fields = ['document__document_title']
    #readonly_fields = ['uploaded_at']

      #Приказы
class AdministrativeOrderAcceptSignatureInline(admin.TabularInline):
    """Inline для множественных подписей ознакомления приказов"""
    model = AdministrativeOrderAcceptSignature
    extra = 1
    fields = ['signature_file', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_at']


@admin.register(AdministrativeOrder)
class AdministrativeOrderAdmin(admin.ModelAdmin):
    actions = ["send_to_approval_action", "send_to_acknowledgment_action"]

    @admin.action(description="Отправить на согласование")
    def send_to_approval_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=order&mode=approval&ids={ids}"
        return redirect(url)

    @admin.action(description="Отправить на ознакомление")
    def send_to_acknowledgment_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:approvals_approvalprocess_start") + f"?doc_type=order&mode=ack&ids={ids}"
        return redirect(url)

    list_display = [
        'registration_number',
        'enterprise_display',
        'order_date',
        'subject_short',
        'approval_display',
        'scope_display',
        'status_display',
        'validity_date_warning',
        'uploaded_file',
        'display_lu_lo_sheets',
    ]

    list_filter = [
        'enterprise',
        'scope',
        'status',
        'order_date',
        'author',
    ]

    search_fields = [
        'registration_number',
        'subject',
        'note',
    ]

    readonly_fields = [
        'id',
        'author',
        'date_of_creation',
        'last_editor',
        'date_of_change',
        'approval_document',
        'acquaintance_document',
    ]

    inlines = [AdministrativeOrderAcceptSignatureInline]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'enterprise',
                'registration_number',
                'order_date',
                'subject',
                'scope',
                'status',
            )
        }),
        ('Утверждение и ознакомление', {
            'fields': (
                'approval',
                'signature_approval',
                'accept',
                'approval_document',
                'acquaintance_document',
            )
        }),
        ('Сроки', {
            'fields': (
                'validity_date',
            )
        }),
        ('Файлы', {
            'fields': (
                'uploaded_file',
                'app_uploaded_file',
            )
        }),
        ('Примечание', {
            'fields': (
                'note',
            )
        }),
        ('Пользователи системы', {
            'fields': (
                'author',
                'last_editor',
                'current_responsible',
            )
        }),
        ('Системные даты', {
            'fields': (
                'date_of_creation',
                'date_of_change',
                'version',
            )
        }),
    )

    def save_model(self, request, obj, form, change):
        """Автоматическая установка пользователей и валидация"""
        # Вызываем clean() для валидации
        try:
            obj.clean()
        except ValidationError as e:
            from django.forms import ValidationError as FormValidationError
            raise FormValidationError(e.message_dict)

        if not change:  # Создание
            obj.author = request.user
            obj.last_editor = request.user
            if not obj.current_responsible:
                obj.current_responsible = request.user
        else:  # Редактирование
            obj.last_editor = request.user
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        """Кастомизация формы — ограничиваем дату приказа"""
        form = super().get_form(request, obj, **kwargs)

        # Ограничиваем выбор даты приказа — только прошедшие даты
        if 'order_date' in form.base_fields:
            today = timezone.now().date().isoformat()
            form.base_fields['order_date'].widget = forms.DateInput(
                attrs={
                    'type': 'date',
                    'max': today,                    # нельзя выбрать сегодня и будущее
                },
                format='%Y-%m-%d'
            )

        # Для даты пересмотра оставляем ограничение "минимум сегодня"
        if 'validity_date' in form.base_fields:
            form.base_fields['validity_date'].widget = forms.DateInput(
                attrs={
                    'type': 'date',
                    'min': today,
                },
                format='%Y-%m-%d'
            )

        return form

    def enterprise_display(self, obj):
        """Отображение предприятия"""
        return dict(AdministrativeOrder.ENTERPRISE_CHOICES).get(obj.enterprise, obj.enterprise)

    enterprise_display.short_description = 'Предприятие'
    enterprise_display.admin_order_field = 'enterprise'

    def approval_display(self, obj):
        """Отображение утвердившего"""
        if obj.approval:
            return obj.approval.username
        return "—"

    approval_display.short_description = 'Утвердил'

    def scope_display(self, obj):
        """Отображение области применения"""
        return dict(AdministrativeOrder.SCOPE_CHOICES).get(obj.scope, obj.scope)

    scope_display.short_description = 'Область применения'

    def status_display(self, obj):
        """Отображение статуса с цветом"""
        colors = {
            'active': 'green',
            'archived': 'gray',
        }
        color = colors.get(obj.status, 'gray')
        status_text = dict(AdministrativeOrder.STATUS_CHOICES).get(obj.status, obj.status)
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, status_text
        )

    status_display.short_description = 'Статус'

    def subject_short(self, obj):
        """Краткое отображение темы"""
        if obj.subject:
            return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
        return "—"

    subject_short.short_description = 'Тема'
    subject_short.admin_order_field = 'subject'

    def validity_date_warning(self, obj):
        """Отображение срока пересмотра с предупреждением"""
        if not obj.validity_date:
            return "—"

        if obj.status != 'active':
            return obj.validity_date.strftime('%d.%m.%Y')

        if obj.is_validity_approaching():
            days_left = (obj.validity_date - timezone.now().date()).days
            return format_html(
                '<span style="color: orange;">{} ⚠️ ({} дн.)</span>',
                obj.validity_date.strftime('%d.%m.%Y'),
                days_left
            )
        return obj.validity_date.strftime('%d.%m.%Y')

    validity_date_warning.short_description = 'Срок пересмотра истекает'
    validity_date_warning.admin_order_field = 'validity_date'

    def display_uploaded_file(self, obj):
        """Отображение файла"""
        if obj.uploaded_file:
            filename = obj.uploaded_file.name.split('/')[-1]
            return format_html(
                '<a href="{}" target="_blank" title="{}">📄 {}</a>',
                obj.uploaded_file.url,
                filename,
                filename[:30] + '...' if len(filename) > 30 else filename
            )
        return "—"

    display_uploaded_file.short_description = 'Файл'

    @admin.display(description="ЛУ/ЛО")
    def display_lu_lo_sheets(self, obj):
        return _admin_lu_lo_sheets_column_html(obj)

class DocumentTemplateAcceptSignatureInline(admin.TabularInline):
    """Inline для множественных подписей ознакомления шаблонов"""
    model = DocumentTemplateAcceptSignature
    extra = 1
    fields = ['signature_file', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_at']

    # Шаблоны
@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'document_template',
        'author_display',
        'date_of_creation',
        'validity_date_warning',
        'display_uploaded_file',
        'document_purpose_short',
    ]

    list_filter = [
        'author',
        'date_of_creation',
        'current_responsible',
    ]

    search_fields = [
        'document_template',
        'document_purpose',
        'note',
    ]

    readonly_fields = [
        'id',
        'author',
        'date_of_creation',
        'last_editor',
        'date_of_change',
    ]

    inlines = [DocumentTemplateAcceptSignatureInline]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'document_template',
                'version',
            )
        }),
        ('Файлы', {
            'fields': (
                'uploaded_file',
                #'app_uploaded_file',
            )
        }),
        ('Срок пересмотра', {
            'fields': (
                'validity_date',
            )
        }),
        ('Назначение и примечание', {
            'fields': (
                'document_purpose',
                'note',
            )
        }),
        ('Пользователи системы', {
            'fields': (
                'author',
                'last_editor',
                'current_responsible',
            )
        }),
        ('Системные даты', {
            'fields': (
                'date_of_creation',
                'date_of_change',
            )
        }),
    )

    def save_model(self, request, obj, form, change):
        """Автоматическая установка пользователей и валидация"""
        # Вызываем clean() для валидации
        try:
            obj.clean()
        except ValidationError as e:
            from django.forms import ValidationError as FormValidationError
            raise FormValidationError(e.message_dict)

        if not change:  # Создание
            obj.author = request.user
            obj.last_editor = request.user
            if not obj.current_responsible:
                obj.current_responsible = request.user
        else:  # Редактирование
            obj.last_editor = request.user
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        """Кастомизация формы для динамической валидации"""
        form = super().get_form(request, obj, **kwargs)

        # Добавляем атрибут min для поля даты
        if 'validity_date' in form.base_fields:
            today = timezone.now().date().isoformat()
            form.base_fields['validity_date'].widget = forms.DateInput(
                attrs={'type': 'date', 'min': today}
            )

        return form

    def author_display(self, obj):
        """Отображение автора"""
        if obj.author:
            return obj.author.username
        return "—"

    author_display.short_description = 'Автор'
    author_display.admin_order_field = 'author__username'

    def last_editor_display(self, obj):
        """Отображение последнего редактора"""
        if obj.last_editor:
            return obj.last_editor.username
        return "—"

    last_editor_display.short_description = 'Последний редактор'

    def validity_date_warning(self, obj):
        """Отображение срока пересмотра с предупреждением"""
        if not obj.validity_date:
            return "—"

        if obj.is_validity_approaching():
            days_left = (obj.validity_date - timezone.now().date()).days
            return format_html(
                '<span style="color: orange;">{} ⚠️ ({} дн.)</span>',
                obj.validity_date.strftime('%d.%m.%Y'),
                days_left
            )
        return obj.validity_date.strftime('%d.%m.%Y')

    validity_date_warning.short_description = 'Срок пересмотра истекает'
    validity_date_warning.admin_order_field = 'validity_date'

    def display_uploaded_file(self, obj):
        """Отображение файла"""
        if obj.uploaded_file:
            filename = obj.uploaded_file.name.split('/')[-1]
            return format_html(
                '<a href="{}" target="_blank" title="{}">📄 {}</a>',
                obj.uploaded_file.url,
                filename,
                filename[:30] + '...' if len(filename) > 30 else filename
            )
        return "—"

    display_uploaded_file.short_description = 'Файл'

    def document_purpose_short(self, obj):
        """Отображение назначения документа (последний столбец)"""
        if obj.document_purpose:
            return format_html(
                '<div style="min-width: 250px; max-width: 400px; white-space: normal; word-wrap: break-word;">{}</div>',
                obj.document_purpose[:100] + '...' if len(obj.document_purpose) > 100 else obj.document_purpose
            )
        return "—"

    document_purpose_short.short_description = 'Назначение документа'

    def save_model(self, request, obj, form, change):
        """Автоматическая установка пользователей"""
        if not change:  # Создание
            obj.author = request.user
            obj.last_editor = request.user
            if not obj.current_responsible:
                obj.current_responsible = request.user
        else:  # Редактирование 
            obj.last_editor = request.user
        super().save_model(request, obj, form, change)


from blog.utils import generate_pdf_logic


#ПСИ СПМ ИБП
class GeneratedDocumentInline(admin.TabularInline):
    """Inline для отображения сгенерированных PDF внутри протокола"""
    model = GeneratedDocument
    extra = 0
    readonly_fields = ('version', 'file_link', 'generated_at')
    fields = ('version', 'file_link', 'generated_at')
    can_delete = False

    def file_link(self, obj):
        if obj.file:
            if obj.psi_source and obj.psi_source.shipment:
                serial = obj.psi_source.shipment.serial_number
            else:
                serial = "—"
            return format_html(
                '<a href="{}" target="_blank">📄 Протокол_ПСИ_ИБП_СПМ_{}_v{}</a>',
                obj.file.url, serial, obj.version
            )
        return "Файл отсутствует"

    file_link.short_description = "Ссылка"


class DocumentHistoryInline(admin.TabularInline):
    """Inline для отображения истории изменений протокола"""
    model = DocumentHistory
    extra = 0
    readonly_fields = ('user', 'action', 'timestamp')
    fields = ('user', 'action', 'timestamp')
    can_delete = False
    verbose_name = "Запись истории"
    verbose_name_plural = "История изменений"

class ShipmentSelect(forms.Select):
    """Выпадающий список «Изделие к отгрузке»: синим цветом подсвечивает
    заводские номера, на которые ещё нет Протокола ПСИ (задача по ПСИ ИБП СПМ)."""

    no_psi_ids = frozenset()

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        # value для реальных пунктов — ModelChoiceIteratorValue (pk в .value),
        # для «---------» — пустая строка.
        raw = getattr(value, "value", value)
        if raw not in ("", None) and raw in self.no_psi_ids:
            option["attrs"]["style"] = "color: #1a56db;"
            option["attrs"]["data-no-psi"] = "1"
        return option


class PSIDocumentForm(forms.ModelForm):
    # Группа разработок, с которой работает эта сущность (см. лист замечаний 21.07.2026).
    PRODUCT_GROUP_NAME = "ИБП СПМ"

    # Сопротивление изоляции вводим как текст: полный контроль над разделителем
    # (только запятая) и над округлением, чтобы «1» не превращалось в «0.96».
    # Поле необязательное: пусто → статус «нет данных» (лист замечаний по ПСИ ИБП СПМ).
    insulation_res_value = forms.CharField(
        required=False,
        label="Фактическое значение сопротивления изоляции, МОм",
        help_text=(
            "Введите измеренное значение в МОм. Статус устанавливается автоматически: при ≥ 1 МОм - Соответствует; при < 1 МОм - Не соответствует. "
        ),
        widget=forms.TextInput(attrs={"placeholder": "например: 1,25"}),
    )

    class Meta:
        model = PSIDocument
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Сохранённое значение сопротивления показываем с запятой,
        # чтобы при повторном сохранении не срабатывала ошибка про точку.
        val = getattr(self.instance, "insulation_res_value", None)
        if val is not None:
            self.initial["insulation_res_value"] = str(val).replace(".", ",")
        # Для п. 5.6 ручной выбор — только из двух вариантов (при наличии файла).
        # Значение "нет данных" проставляется автоматически, когда файл не прикреплён.
        if 'func_audio' in self.fields:
            self.fields['func_audio'].choices = [
                ('соответствует', 'Соответствует'),
                ('не соответствует', 'Не соответствует'),
            ]

        # --- Обязательные поля (лист замечаний 21.07.2026, п. 1-3) ---
        # На уровне модели поля остаются null/blank, чтобы не ломать старые записи;
        # обязательность включаем только в форме админки.
        for req_name in ('shipment', 'developer_org'):
            if req_name in self.fields:
                self.fields[req_name].required = True

        # «Представитель ОТК» и «Текущий ответственный» — обязательные поля
        # (лист замечаний 23.07.2026). По умолчанию подставляется создатель
        # протокола (см. PSIDocumentAdmin.get_changeform_initial_data), но
        # остаётся выпадающий список всех пользователей — значение можно изменить.
        _all_users = User.objects.all().order_by('last_name', 'first_name', 'username')
        for _user_field in ('inspector', 'current_responsible'):
            if _user_field in self.fields:
                self.fields[_user_field].required = True
                self.fields[_user_field].queryset = _all_users

        # --- Каскад «Группа → Разработка (модификация) → Изделие к отгрузке» (п. 6) ---
        # Разработку выбираем только из группы «ИБП СПМ».
        if 'post' in self.fields:
            self.fields['post'].required = True
            self.fields['post'].queryset = Post.objects.filter(
                product_group__name=self.PRODUCT_GROUP_NAME
            ).order_by('name')

        # «Изделие к отгрузке» — только отгрузки выбранной разработки.
        if 'shipment' in self.fields:
            field = self.fields['shipment']
            # Свой виджет: синим подсвечивает изделия без Протокола ПСИ.
            # Меняем виджет ДО присвоения queryset, чтобы choices попали в него.
            field.widget = ShipmentSelect(attrs=field.widget.attrs)
            field.widget.is_required = field.required
            field.help_text = (
                "Выбрать через функцию «Сохранить и продолжить редактирование»"
            )

            selected_post = None
            if self.is_bound:
                selected_post = self.data.get(self.add_prefix('post')) or None
            elif getattr(self.instance, 'post_id', None):
                selected_post = self.instance.post_id
            if selected_post:
                qs = Shipment.objects.filter(
                    post_id=selected_post
                ).order_by('serial_number')
            else:
                # До выбора разработки список ограничен изделиями группы «ИБП СПМ».
                qs = Shipment.objects.filter(
                    post__product_group__name=self.PRODUCT_GROUP_NAME
                ).order_by('serial_number')
            # Присвоение queryset пробрасывает choices в новый виджет.
            field.queryset = qs

            # Заводские номера без Протокола ПСИ — для синей подсветки.
            ship_ids = list(qs.values_list('pk', flat=True))
            with_psi = set(
                PSIDocument.objects.filter(shipment_id__in=ship_ids)
                .values_list('shipment_id', flat=True)
            )
            field.widget.no_psi_ids = frozenset(set(ship_ids) - with_psi)

    def clean_insulation_res_value(self):
        from decimal import Decimal, InvalidOperation
        raw = (self.cleaned_data.get("insulation_res_value") or "").strip()
        if not raw:
            # Поле необязательное: пусто → значение не задано (статус «нет данных»).
            return None
        if "." in raw:
            raise forms.ValidationError("Использовать запятую в качестве десятичного разделителя")
        normalized = raw.replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            value = Decimal(normalized)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Введите корректное числовое значение (например: 1,25)")
        # Квантуем ровно до 2 знаков: «1» → 1.00 (устраняет искажение вроде 1 → 0.96).
        return value.quantize(Decimal("0.01"))

    def clean(self):
        cleaned_data = super().clean()

        interface_file = cleaned_data.get('interface_file')
        func_audio = cleaned_data.get('func_audio')
        interface_note = cleaned_data.get('interface_note')

        if not interface_file:
            # Файл (SNMP/UART) не прикреплён — статус п. 5.6 автоматически "нет данных"
            cleaned_data['func_audio'] = 'нет данных'
        elif func_audio == 'не соответствует' and not (interface_note and interface_note.strip()):
            # Файл прикреплён, выбрано "Не соответствует" — примечание обязательно
            self.add_error(
                'interface_note',
                'При статусе «Не соответствует» необходимо заполнить «Примечание (п. 5.6)».'
            )

        # Прямая связь «Разработка → Изделие к отгрузке» (п. 6):
        # изделие обязано принадлежать выбранной разработке.
        post = cleaned_data.get('post')
        shipment = cleaned_data.get('shipment')
        if post and shipment and shipment.post_id != post.id:
            self.add_error(
                'shipment',
                'Выбранное изделие к отгрузке не относится к выбранной разработке (модификации).'
            )

        # Один протокол ПСИ на один заводской номер (shipment).
        if shipment:
            duplicates = PSIDocument.objects.filter(shipment=shipment)
            if self.instance and self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    'shipment',
                    'Для этого заводского номера уже существует протокол ПСИ. '
                    'На один заводской номер допускается только один протокол.'
                )

        return cleaned_data


@admin.register(PSIDocument)
class PSIDocumentAdmin(admin.ModelAdmin):
    form = PSIDocumentForm
    """Админка для протоколов ПСИ"""

    list_display = (
        'get_post_name',      # отображение модификации
        'get_serial_number',  # заводской номер из shipment
        'get_developer_name', # организация-разработчик
        'test_date',
        'inspector',
        'get_workshop_name',
        'conclusion_short',
        'pdf_count_display',
        'created_at',
        #'func_audio_status'
    )

    list_filter = (
        'test_date',
        'inspector',
        'conclusion',
        'workshop',
    )

    search_fields = (
        'shipment__serial_number', # Ищем по заводскому номеру
        'post__name', # Ищем по связанной модели
        'fw_version',
        'inspector__last_name',   # inspector — FK на User, ищем по полям пользователя
        'inspector__first_name',
        'inspector__username',
        'comment',
        'workshop__number_name',
    )

    readonly_fields = (
        'created_at',
        'pdf_count_display',
        'display_files_list',
        'date_of_change',
        'insulation_res',  # определяется автоматически по фактическому значению
        'conclusion',  # определяется автоматически по результатам проверок
        'author',  # проставляется автоматически
        'last_editor',  # проставляется автоматически
        'date_of_creation',
        'version',  # вычисляется программно (+1 при каждом изменении), вручную не редактируется
    )

    # post/shipment — обычные зависимые списки (каскад), поэтому убраны из autocomplete.
    autocomplete_fields = ('developer_org', 'workshop')

    inlines = [GeneratedDocumentInline, DocumentHistoryInline]

    class Media:
        # Жирные подписи пунктов 3 (сопротивление изоляции) и 4 (прочность изоляции)
        css = {
            'all': ('blog/psi_admin_bold.css',)
        }
        # Каскад «Разработка → Изделие к отгрузке».
        js = ('blog/js/chained_shipment.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'shipments-for-post/',
                self.admin_site.admin_view(self.shipments_for_post_view),
                name='blog_psidocument_shipments_for_post',
            ),
        ]
        return custom + urls

    def shipments_for_post_view(self, request):
        """JSON-список изделий к отгрузке для выбранной разработки (каскад).
        Флаг no_psi=true → на изделие ещё нет Протокола ПСИ (синяя подсветка)."""
        from django.http import JsonResponse
        post_id = request.GET.get('post_id')
        results = []
        if post_id:
            shipments = list(
                Shipment.objects.filter(post_id=post_id).order_by('serial_number')
            )
            ship_ids = [s.pk for s in shipments]
            with_psi = set(
                PSIDocument.objects.filter(shipment_id__in=ship_ids)
                .values_list('shipment_id', flat=True)
            )
            results = [
                {'id': s.pk, 'text': str(s), 'no_psi': s.pk not in with_psi}
                for s in shipments
            ]
        return JsonResponse({'results': results})

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Передаём JS URL для подгрузки изделий выбранной разработки.
        if 'post' in form.base_fields:
            form.base_fields['post'].widget.attrs['data-shipments-url'] = reverse(
                'admin:blog_psidocument_shipments_for_post'
            )
        return form

    def get_changeform_initial_data(self, request):
        """Для нового протокола «Представитель ОТК» и «Текущий ответственный»
        по умолчанию — его создатель. Значения остаются редактируемыми
        (выпадающий список всех пользователей)."""
        initial = super().get_changeform_initial_data(request)
        if request.user.is_authenticated:
            initial.setdefault('inspector', request.user.pk)
            initial.setdefault('current_responsible', request.user.pk)
        return initial

    fieldsets = (
        ('1. Идентификация изделия', {
            'fields': (
                'post',  # выбор модификации
                'shipment',  # выбор заводского номера
                'developer_org',  # выбор организации
                'test_date',
                'fw_version'
            )
        }),
        ('2. Общие проверки (ТУ,ПМ)', {
            'fields': ('visual_check', 'marking_check', 'insulation_res', 'insulation_res_value', 'insulation_strength')
        }),
        ('3. Проверка функционирования (1.2.5 ТУ, 5.8 ПМ)', {
            'fields': (
                'func_power_on', 'func_display', 'func_navigation',
                'func_battery_mode', 'func_bypass', 'func_audio', 'interface_file',      # <-- ПОЛЕ ДЛЯ ЗАГРУЗКИ ФАЙЛА
                'interface_note',
                'func_settings', 'func_terminal'
            )
        }),
        ('4. Итоговое заключение', {
            'fields': ('conclusion', 'comment')
        }),
        ('5. Метеоусловия и Персонал', {
            #'classes': ('collapse',),
            'fields': ('inspector', 'workshop', 'remark', 'temperature', 'humidity', 'pressure')
        }),
        (
            '6. Системные данные',
            {
                "fields": (
                    "author",
                    "current_responsible",
                    "last_editor",
                    "version",
                    #"version_diff_display",
                    "date_of_creation",
                    "date_of_change",
                )
            },
        ),
    )

    actions = ['create_pdf_action']
#отображаемая кнопка для применения выбранного действия к выбранным объектам (в этом случае для генерации pdf  файла пси)
#    @admin.action(description="Сгенерировать PDF протокол")
 #   def create_pdf_action(self, request, queryset):
  #      """Экшен для массовой генерации PDF"""
   #     count = 0
   #     for obj in queryset:
    #        generate_pdf_logic(obj, request.user)
     #       count += 1
      #  self.message_user(request, f"✅ PDF отчеты успешно сформированы для {count} протокол(ов).")

    def conclusion_short(self, obj):
        """Краткое отображение заключения"""
        if obj.conclusion:
            return obj.conclusion[:50] + '...' if len(obj.conclusion) > 50 else obj.conclusion
        return "—"

    conclusion_short.short_description = 'Заключение'

    def pdf_count_display(self, obj):
        """Ссылка на актуальную (последнюю) версию PDF протокола"""
        latest = obj.pdfs.order_by('-version').first()
        if not latest or not latest.file:
            return "—"
        return format_html(
            '<a href="{}" target="_blank">📄_v{}</a>',
            latest.file.url, latest.version
        )

    pdf_count_display.short_description = 'Протокол PDF'

    def display_files_list(self, obj):
        """Список всех PDF файлов для детального просмотра"""
        pdfs = obj.pdfs.all().order_by('-version')
        if not pdfs.exists():
            return "Нет сгенерированных PDF"

        html = '<div style="background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px;">'
        html += '<h4>📑 Сгенерированные PDF:</h4><ul style="margin-top: 5px;">'
        for pdf in pdfs:
            html += f'<li style="margin-bottom: 5px;">'
            html += f'📄 <a href="{pdf.file.url}" target="_blank">Версия {pdf.version}</a>'
            html += f' <span style="color: #666; font-size: 0.9em;">(создан: {pdf.generated_at.strftime("%d.%m.%Y %H:%M")})</span>'
            html += '</li>'
        html += '</ul></div>'
        return format_html(html)

    display_files_list.short_description = 'Файлы PDF'

    def save_model(self, request, obj, form, change):
        """Сохранение с логированием и автогенерацией PDF при изменениях.

        PDF формируется ТОЛЬКО по кнопке «Сохранить» (и «Сохранить и добавить
        другой»), но не по «Сохранить и продолжить редактирование» (_continue).
        Изменения, внесённые при промежуточных сохранениях, копятся в сессии
        (без изменения схемы БД) и попадают в PDF при финальном «Сохранить»."""
        is_new = obj.pk is None

        # Определяем были ли реальные изменения (для существующих объектов)
        has_changes = is_new or bool(form.changed_data)

        # Кнопка «Сохранить и продолжить редактирование» присылает _continue.
        # По ней PDF не генерируем — только сохраняем данные.
        is_continue = '_continue' in request.POST

        # Автор / последний редактор проставляются автоматически (поля readonly).
        if request.user.is_authenticated:
            if not obj.author_id:
                obj.author = request.user
            obj.last_editor = request.user
            # «Представитель ОТК» не должен сохраняться пустым («--------»):
            # по умолчанию — тот, кто формирует протокол (переходный период, пока роли не работают).
            if not obj.inspector_id:
                obj.inspector = request.user
            # «Текущий ответственный» по умолчанию — тот, кто последним вносил правки.
            if not obj.current_responsible_id:
                obj.current_responsible = request.user

        # «Версия» вычисляется программно и проставляется после каждого реального
        # изменения сущности (+1 по порядку). Поле только для чтения — вручную
        # его менять нельзя. При создании версия = «1».
        if is_new:
            obj.version = "1"
        elif has_changes:
            try:
                next_version = int(obj.version or "0") + 1
            except (TypeError, ValueError):
                next_version = 1
            # version — CharField(max_length=3): не выходим за пределы столбца БД.
            obj.version = str(min(next_version, 999))

        super().save_model(request, obj, form, change)

        action_text = "Создан новый протокол" if is_new else "Протокол отредактирован"
        if not is_new and has_changes:
            action_text += f" (изменены поля: {', '.join(form.changed_data)})"

        # action — CharField(max_length=255): длинный список изменённых полей
        # обрезаем, иначе PostgreSQL выдаёт ошибку StringDataRightTruncation.
        DocumentHistory.objects.create(
            psi_source=obj,
            user=request.user,
            action=action_text[:255]
        )

        # --- Генерация PDF по кнопке ---
        # PDF формируем ТОЛЬКО по финальному «Сохранить» (или «Сохранить и
        # добавить другой»), но не по «Сохранить и продолжить редактирование».
        # Признак «есть изменения без PDF» копим в сессии по id протокола, чтобы
        # правки из промежуточных сохранений попали в PDF при финальном «Сохранить»
        # (form.changed_data к тому моменту уже пустой). Схему БД не трогаем.
        session_key = 'psi_pdf_pending_ids'
        pending_ids = request.session.get(session_key, [])
        obj_key = str(obj.pk)

        if has_changes and obj_key not in pending_ids:
            pending_ids.append(obj_key)

        if is_continue:
            # Промежуточное сохранение — PDF не создаём, изменения запоминаем.
            if has_changes:
                self.message_user(
                    request,
                    "💾 Изменения сохранены. Новый PDF будет сформирован "
                    "при нажатии «Сохранить».",
                    level='info'
                )
        elif obj_key in pending_ids:
            # Финальное «Сохранить»: есть накопленные изменения → формируем PDF.
            try:
                from blog.utils import generate_pdf_logic
                generate_pdf_logic(obj, request.user)
                pending_ids = [i for i in pending_ids if i != obj_key]
                self.message_user(request, "✅ PDF протокол автоматически сгенерирован.")
            except Exception as e:
                # При ошибке отметку не снимаем — повторим при следующем «Сохранить».
                self.message_user(
                    request,
                    f"⚠️ Протокол сохранён, но PDF не удалось сгенерировать: {e}",
                    level='warning'
                )

        request.session[session_key] = pending_ids
        request.session.modified = True

    def get_queryset(self, request):
        """Оптимизация запросов"""
        return super().get_queryset(request).prefetch_related('pdfs')

    def get_post_name(self, obj):
        return obj.post.name if obj.post else "—"

    get_post_name.short_description = 'Модификация'
    get_post_name.admin_order_field = 'post__name'

    def get_serial_number(self, obj):
        return obj.shipment.serial_number if obj.shipment else "—"

    get_serial_number.short_description = 'Заводской номер'
    get_serial_number.admin_order_field = 'shipment__serial_number'

    def get_developer_name(self, obj):
        return obj.developer_org.name if obj.developer_org else "—"

    get_developer_name.short_description = 'Организация'
    get_developer_name.admin_order_field = 'developer_org__name'

    def get_workshop_name(self, obj):
        """Отображение цеха/площадки"""
        return obj.workshop.number_name if obj.workshop else "—"

    get_workshop_name.short_description = 'Цех/Площадка'
    get_workshop_name.admin_order_field = 'workshop__number_name'


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    """Админка для сгенерированных PDF документов"""

    list_display = (
        'id',
        'psi_source_link',
        'version',
        'generated_at',
        'file_link',
    )

    list_filter = (
        'version',
        'generated_at',
    )

    search_fields = (
        'psi_source__serial_number',
        'psi_source__model_name',
        'file',
    )

    readonly_fields = (
        'psi_source',
        'version',
        'generated_at',
        'file_link_display',
    )

    fieldsets = (
        ('Основная информация', {
            'fields': ('psi_source', 'version', 'generated_at')
        }),
        ('Файл', {
            'fields': ('file_link_display',)
        }),
    )

    def has_module_permission(self, request):
        return False

    def psi_source_link(self, obj):
        """Ссылка на родительский протокол"""
        if obj.psi_source:
            url = f"/admin/blog/psidocument/{obj.psi_source.id}/change/"
            return format_html('<a href="{}">{}</a>', url, obj.psi_source.serial_number)
        return "—"

    psi_source_link.short_description = 'Протокол'

    def file_link(self, obj):
        """Отображение файла в списке"""
        if obj.file:
            return format_html('<a href="{}" target="_blank">📄 Открыть</a>', obj.file.url)
        return "—"

    file_link.short_description = 'PDF'

    def file_link_display(self, obj):
        """Отображение файла в детальной форме"""
        if obj.file:
            return format_html(
                '<div style="background: #f0f0f0; padding: 10px;">'
                '<p><strong>Файл:</strong> {}</p>'
                '<p><a href="{}" target="_blank" class="button">📥 Протокол_ПСИ_ИБП_СПМ</a></p>'
                '</div>',
                obj.file.name,
                obj.file.url
            )
        return "Файл не найден"

    file_link_display.short_description = 'Файл PDF'

    def has_add_permission(self, request):
        """Запрещаем ручное создание PDF"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещаем изменение PDF"""
        return False


@admin.register(DocumentHistory)
class DocumentHistoryAdmin(admin.ModelAdmin):
    """Админка для истории изменений протоколов"""

    list_display = (
        'id',
        'psi_source_link',
        'user',
        'action_short',
        'timestamp',
    )

    list_filter = (
        'timestamp',
        'user',
        'psi_source',
    )

    search_fields = (
        'action',
        'user__username',
        'psi_source__serial_number',
    )

    readonly_fields = (
        'psi_source',
        'user',
        'action',
        'timestamp',
    )

    fieldsets = (
        ('Информация об изменении', {
            'fields': ('psi_source', 'user', 'action', 'timestamp')
        }),
    )

    def has_module_permission(self, request):
        return False

    def psi_source_link(self, obj):
        """Ссылка на родительский протокол"""
        if obj.psi_source:
            url = f"/admin/blog/psidocument/{obj.psi_source.id}/change/"
            return format_html('<a href="{}">{}</a>', url, obj.psi_source.serial_number)
        return "—"

    psi_source_link.short_description = 'Протокол'

    def action_short(self, obj):
        """Краткое отображение действия"""
        if obj.action:
            return obj.action[:60] + '...' if len(obj.action) > 60 else obj.action
        return "—"

    action_short.short_description = 'Действие'

    def has_add_permission(self, request):
        """Запрещаем ручное добавление истории"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещаем изменение истории"""
        return False

#Модель пользовательского разделе с доп информацией
class UserWithProfileForm(UserChangeForm):
    """Поля профиля сотрудника (EmployeeProfile) """
    patronymic = forms.CharField(label='Отчество', max_length=100, required=False)
    phone = forms.CharField(label='Телефон', max_length=20, required=False)
    birth_date = forms.DateField(label='Дата рождения', required=False, widget=AdminDateWidget)
    avatar = forms.ImageField(label='Фото', required=False)
    org_department = forms.ModelChoiceField(
        label='Структурное подразделение (Отдел)',
        queryset=Department.objects.all(),
        required=False,
    )
    is_head = forms.BooleanField(label='Руководитель отдела', required=False)
    position = forms.CharField(label='Должность', max_length=100, required=False)
    supervisor = forms.ModelChoiceField(
        label='Непосредственное подчинение',
        queryset=User.objects.all(),
        required=False,
    )
    roles_responsibilities = forms.CharField(
        label='Роли / обязанности',
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, 'profile', None) if self.instance.pk else None
        if profile:
            self.fields['patronymic'].initial = profile.patronymic
            self.fields['phone'].initial = profile.phone
            self.fields['birth_date'].initial = profile.birth_date
            self.fields['avatar'].initial = profile.avatar
            self.fields['org_department'].initial = profile.org_department_id
            self.fields['is_head'].initial = profile.is_head
            self.fields['position'].initial = profile.position
            self.fields['supervisor'].initial = profile.supervisor_id
            self.fields['roles_responsibilities'].initial = profile.roles_responsibilities

        # Кнопка «+» для добавления нового подразделения прямо из карточки.
        dep_rel = EmployeeProfile._meta.get_field('org_department').remote_field
        self.fields['org_department'].widget = RelatedFieldWidgetWrapper(
            self.fields['org_department'].widget,
            dep_rel,
            admin.site,
            can_add_related=True,
            can_change_related=True,
        )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Справочник отделов. Скрыт из бокового меню — заполняется через «плюсик»
    в карточке пользователя (поле «Отдел»)."""
    list_display = ('name', 'is_active')
    search_fields = ('name',)

    def get_model_perms(self, request):
        return {}


admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    form = UserWithProfileForm

    _PROFILE_FIELDS = (
        'patronymic', 'phone', 'birth_date', 'avatar', 'org_department',
        'is_head', 'position', 'supervisor', 'roles_responsibilities',
    )

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Персональные данные', {
            'fields': ('first_name', 'last_name', 'patronymic', 'birth_date', 'phone', 'email', 'avatar'),
        }),
        ('Профиль сотрудника', {
            'fields': ('org_department', 'is_head', 'position', 'supervisor', 'roles_responsibilities'),
        }),
        ('Права доступа', {
            'classes': ('collapse',),
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Важные даты', {
            'classes': ('collapse',),
            'fields': ('last_login', 'date_joined'),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if any(f in form.cleaned_data for f in self._PROFILE_FIELDS):
            profile, _ = EmployeeProfile.objects.get_or_create(user=obj)
            profile.patronymic = form.cleaned_data.get('patronymic', '')
            profile.phone = form.cleaned_data.get('phone', '')
            profile.birth_date = form.cleaned_data.get('birth_date')
            avatar = form.cleaned_data.get('avatar')
            if avatar is False:
                profile.avatar = None
            elif avatar:
                profile.avatar = avatar
            profile.org_department = form.cleaned_data.get('org_department')
            profile.is_head = form.cleaned_data.get('is_head', False)
            profile.position = form.cleaned_data.get('position', '')
            profile.supervisor = form.cleaned_data.get('supervisor')
            profile.roles_responsibilities = form.cleaned_data.get('roles_responsibilities', '')
            profile.save()

    list_filter = BaseUserAdmin.list_filter + ('profile__org_department',)

    list_display = (
        'username',
        'get_full_name_with_patronymic',
        'email',
        'get_phone',
        'get_department',
        'get_is_head',
        'get_position',
        'get_supervisor',
        'is_active',
    )

    @admin.display(description='ФИО (Фамилия Имя Отчество)', ordering='last_name')
    def get_full_name_with_patronymic(self, obj):
        """Полное ФИО: Фамилия Имя Отчество из профиля."""
        profile = getattr(obj, 'profile', None)
        return profile.full_name() if profile else obj.username

    # оставляем для обратной совместимости, но прячем из list_display
    def get_full_name(self, obj):
        name = f"{obj.last_name} {obj.first_name}".strip()
        return name or obj.username

    @admin.display(description='Руководитель', boolean=True, ordering='profile__is_head')
    def get_is_head(self, obj):
        return obj.profile.is_head if hasattr(obj, 'profile') else False

    def get_patronymic(self, obj):
        return obj.profile.patronymic if hasattr(obj, 'profile') else ''

    get_patronymic.short_description = 'Отчество'
    get_patronymic.admin_order_field = 'profile__patronymic'

    def get_phone(self, obj):
        return obj.profile.phone if hasattr(obj, 'profile') else ''

    get_phone.short_description = 'Телефон'
    get_phone.admin_order_field = 'profile__phone'

    def get_department(self, obj):
        if hasattr(obj, 'profile') and obj.profile.org_department:
            return obj.profile.org_department.name
        return ''

    get_department.short_description = 'Структурное подразделение (Отдел)'
    get_department.admin_order_field = 'profile__org_department__name'

    def get_position(self, obj):
        return obj.profile.position if hasattr(obj, 'profile') else ''

    get_position.short_description = 'Должность'
    get_position.admin_order_field = 'profile__position'

    def get_supervisor(self, obj):
        if hasattr(obj, 'profile') and obj.profile.supervisor:
            return obj.profile.supervisor.get_full_name() or obj.profile.supervisor.username
        return ''

    get_supervisor.short_description = 'Непосредственное подчинение'
    get_supervisor.admin_order_field = 'profile__supervisor'


# ПСИ ПАК СПМ
from .utils import generate_pak_pdf_logic


class PAKGeneratedDocumentInline(admin.TabularInline):
    model = PAKGeneratedDocument
    extra = 0
    can_delete = False
    readonly_fields = ('version', 'file_link', 'generated_at')
    fields = ('version', 'file_link', 'generated_at')

    def file_link(self, obj):
        if obj.file:
            if obj.pak_source and obj.pak_source.shipment:
                serial = obj.pak_source.shipment.serial_number
            else:
                serial = "—"
            return format_html(
                '<a href="{}" target="_blank">📄 Протокол_ПСИ_ПАК_СПМ_{}_v{}</a>',
                obj.file.url, serial, obj.version
            )
        return "Файл отсутствует"

    file_link.short_description = "Ссылка"


class PAKDocumentHistoryInline(admin.TabularInline):
    model = PAKDocumentHistory
    extra = 0
    can_delete = False
    readonly_fields = ('action', 'user', 'timestamp')
    fields = ('action', 'user', 'timestamp')


class PAKDocumentForm(forms.ModelForm):
    class Meta:
        model = PAKDocument
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Для п. 4 ручной выбор — только из двух вариантов (при наличии файла).
        # Значение "нет данных" проставляется автоматически, когда файл не прикреплён.
        if 'check_alarm' in self.fields:
            self.fields['check_alarm'].required = False
            self.fields['check_alarm'].choices = [
                ('соответствует', 'Соответствует'),
                ('не соответствует', 'Не соответствует'),
            ]
        if 'alarm_note' in self.fields:
            self.fields['alarm_note'].required = False

    def clean(self):
        cleaned_data = super().clean()

        alarm_log_file = cleaned_data.get('alarm_log_file')
        check_alarm = cleaned_data.get('check_alarm')
        alarm_note = cleaned_data.get('alarm_note')

        if not alarm_log_file:
            # если файл с логами не прикреплён — статус п. 4 автоматически "нет данных"
            cleaned_data['check_alarm'] = 'не соответствует'
        elif check_alarm == 'не соответствует' and not (alarm_note and alarm_note.strip()):
            # Файл прикреплён, выбрано "Не соответствует" — примечание обязательно
            self.add_error(
                'alarm_note',
                'При статусе «Не соответствует» необходимо заполнить «Примечание (п. 4)».'
            )

        return cleaned_data


@admin.register(PAKDocument)
class PAKDocumentAdmin(admin.ModelAdmin):
    form = PAKDocumentForm
    list_display = (
        'get_model_name',
        'get_serial_number',
        'get_developer_name',
        'test_date_start',
        'test_date_end',
        'inspector',
        'conclusion',
        'pdf_link',
        'created_at',
    )
    list_filter = ('test_date_start', 'inspector', 'conclusion')
    search_fields = (
        'shipment__serial_number',
        'post__name',
        'fw_version',
        'inspector__last_name',   # inspector — FK на User, ищем по полям пользователя
        'inspector__first_name',
        'inspector__username',
    )
    autocomplete_fields = ('shipment', 'post', 'developer_org')

    readonly_fields = (
        'created_at',
        'date_of_change',
        'author',
        'last_editor',
        'conclusion',  # определяется автоматически по результатам проверок
        'pdf_count_display',
        'date_of_creation',
    )

    inlines = [PAKGeneratedDocumentInline, PAKDocumentHistoryInline]

    fieldsets = (
        ('1. Основная информация', {
            'fields': (
                'shipment',
                'post',
                'developer_org',
                'fw_version',
                'test_date_start',
                'test_date_end',
            )
        }),
        ('2. Общие проверки (ТУ,ПМ)', {
            'fields': (
                'check_marking',
                'check_kd_appearance',
                'check_server_link',
                'check_alarm',
                'alarm_log_file',
                'alarm_note',
                'check_battery_status',
                'check_radio_settings',
                'check_long_run',
            )
        }),
        ('3. Итоговое заключение', {
            'fields': ('conclusion', 'comment'),
        }),
        ('4. Метеоусловия и Персонал', {
            'fields': ('inspector','workshop', 'remark', 'temperature', 'humidity', 'pressure'),
        }),
        ('5. Системные данные',
            {
                "fields": (
                    "author",
                    "current_responsible",
                    "last_editor",
                    "version",
                    #"version_diff_display",
                    "date_of_creation",
                    "date_of_change",
                ),
        }),
    )

    actions = ['create_pak_pdf_action']

    def conclusion_short(self, obj):
        """Краткое отображение заключения"""
        if obj.conclusion:
            return obj.conclusion[:50] + '...' if len(obj.conclusion) > 50 else obj.conclusion
        return "—"

    conclusion_short.short_description = 'Заключение'

    # ---- Колонки списка ----
    def get_model_name(self, obj):
        return obj.post.name if obj.post else "—"

    get_model_name.short_description = 'Модификация'

    def get_serial_number(self, obj):
        return obj.shipment.serial_number if obj.shipment else "—"

    get_serial_number.short_description = 'Заводской номер'

    def get_developer_name(self, obj):
        return obj.developer_org.name if obj.developer_org else "—"

    get_developer_name.short_description = 'Организация'

    def pdf_link(self, obj):
        """Кликабельная ссылка на актуальную (последнюю) версию PDF."""
        latest = obj.pdfs.order_by('-version').first()
        if not latest or not latest.file:
            return "—"
        return format_html(
            '<a href="{}" target="_blank">📄 v{}</a>',
            latest.file.url, latest.version
        )

    pdf_link.short_description = 'Протокол PDF'

    def pdf_count_display(self, obj):
        latest = obj.pdfs.order_by('-version').first()
        if not latest or not latest.file:
            return "—"
        return format_html(
            '<a href="{}" target="_blank">📄 v{}</a>',
            latest.file.url, latest.version
        )

    pdf_count_display.short_description = 'Протокол PDF'

    # ---- Автор / редактор + автогенерация PDF ----
    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

        PAKDocumentHistory.objects.create(
            pak_source=obj,
            user=request.user,
            action=("Создан новый протокол" if not change else "Протокол отредактирован")
        )

        # Автоматически формируем PDF сразу после сохранения протокола.
        # Ошибку генерации не «роняем» на пользователя — сохранение уже прошло,
        # просто показываем предупреждение.
        try:
            generated = generate_pak_pdf_logic(obj, request.user)
            self.message_user(
                request,
                f"✅ PDF протокола сформирован автоматически (версия {generated.version})."
            )
        except Exception as e:
            self.message_user(
                request,
                f"⚠️ Протокол сохранён, но PDF не сформировался: {e}",
                level=messages.WARNING,
            )

    # ---- Экшен генерации PDF ----
    @admin.action(description="Сгенерировать PDF протокол ПАК СПМ")
    def create_pak_pdf_action(self, request, queryset):
        count = 0
        for obj in queryset:
            generate_pak_pdf_logic(obj, request.user)
            count += 1
        self.message_user(request, f"✅ PDF сформированы для {count} протокол(ов) ПАК СПМ.")


#@admin.register(PAKGeneratedDocument)
#class PAKGeneratedDocumentAdmin(admin.ModelAdmin):
#    list_display = ('pak_source', 'version', 'open_pdf', 'generated_at')
#    readonly_fields = ('generated_at',)

    def open_pdf(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">📄 Открыть PDF</a>', obj.file.url)
        return "—"

    open_pdf.short_description = 'Ссылка'


#@admin.register(PAKDocumentHistory)
#class PAKDocumentHistoryAdmin(admin.ModelAdmin):
#    list_display = ('pak_source', 'action', 'user', 'timestamp')
#    list_filter = ('timestamp', 'user')
#    readonly_fields = ('pak_source', 'action', 'user', 'timestamp')


# ============================================================================
#  Скрытие моделей из индекса админ-панели БЕЗ снятия регистрации.
#  get_model_perms -> {} убирает модель из списка приложения на главной
#  админки, но модель остаётся зарегистрированной: прямые URL, автокомплит,
#  выбор в ForeignKey (попапы "+"), инлайны — продолжают работать.
# ============================================================================
def _hide_from_admin_index(*models):
    for _model in models:
        _model_admin = admin.site._registry.get(_model)
        if _model_admin is not None:
            _model_admin.get_model_perms = (lambda request: {})

_hide_from_admin_index(
    Route,
    WorkAssignmentDeadlineChange,
    CheckDocumentWorkflow,
    ApprovalDocumentWorkflow,
)