from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from datetime import timedelta
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
import re
from django.db.models import Q, F, Value, TextField, DateField, BooleanField, Case, When
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

from .admin_forms import RescheduleAdminForm
from .forms import WorkAssignmentForm, UniversalRKDForm
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
    ProtocolTechnicalProposal,
    ReportTechnicalProposal,
    Route,
    RouteProcess,
    SoftwareProduct,
    TechnicalProposal,
    TaskForDesignWork,
    RevisionTask,
    WorkAssignment,
    WorkAssignmentDeadlineChange,
    Attachment,
    UniversalRKD,
    RKDDeveloper,
)
from .services import WorkAssignmentService


def _inject_rkd_category_json(extra_context):
    extra_context = extra_context or {}
    extra_context["rkd_category_by_section_dict"] = {
        k: list(v) for k, v in RKD_CATEGORY_BY_SECTION.items()
    }
    return extra_context


def _admin_warning_triangle_html(*, title: str, color: str = "#f0ad4e") -> str:
    """Как в журнале СИЗ / поверки: жёлтый треугольник с подсказкой."""
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


def _universal_rkd_planned_review_show_warning(validity_date) -> bool:
    """Предупреждение, если до даты пересмотра осталось не более 60 дней или срок уже прошёл."""
    if not validity_date:
        return False
    today = timezone.now().date()
    return (validity_date - today).days <= 60


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
    formset = RequiredFileGenericFormSet   # ваш общий formset
    extra = 1
    fields = ("file",)

@admin.register(TechnicalProposal)
class TechnicalProposalAdmin(admin.ModelAdmin):
    list_display = ['name', 'author', 'date_of_creation']
    readonly_fields = ('date_of_creation', 'date_of_change')

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
    fields = (
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
        "result",
    )
    show_change_link = True

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
        "category",
        "desig_document",
        "name",
        "status",
    )


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    change_form_template = "admin/blog/universal_rkd_category_change_form.html"
    list_display = (
        'name',
        'desig_document_post',
        'modification_code',
        'author',
        'date_of_creation',
        'date_of_change',
    )
    search_fields = ('name', 'modification_code')
    readonly_fields = ('date_of_change',)
    inlines = [
        # ListTechnicalProposalInline,  # ВТП — в форме «Разработка» не показываем
        TaskForDesignWorkInline,
        RevisionTaskInline,
        WorkAssignmentInline,
        UniversalRKDInline,
    ]

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = _inject_rkd_category_json(extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            instance.post = form.instance

            # Если name пустое или только пробелы — взять из головной модели
            if not instance.name or not instance.name.strip():
                instance.name = instance.post.name


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


@admin.register(RKDDeveloper)
class RKDDeveloperAdmin(admin.ModelAdmin):
    fields = (
        "name",
        "charter",
        "requisites",
        "additional_data",
    )
    search_fields = ("name",)


@admin.register(UniversalRKD)
class UniversalRKDAdmin(admin.ModelAdmin):
    change_form_template = "admin/blog/universal_rkd_category_change_form.html"
    change_list_template = "admin/blog/universalrkd/change_list.html"
    form = UniversalRKDForm
    list_display = (
        "rkd_post_column",
        "rkd_specification_section",
        "rkd_sheet_format",
        "position",
        "desig_document",
        "name",
        "rkd_documents_column",
        "quantity",
        "rkd_planned_review_warning",
        "note",
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

    @admin.display(
        description="Срок пересмотра истекает",
        ordering="validity_date",
    )
    def rkd_planned_review_warning(self, obj):
        if not _universal_rkd_planned_review_show_warning(obj.validity_date):
            return "—"
        return mark_safe(
            _admin_warning_triangle_html(
                title="Плановый пересмотр: осталось не более 60 дней или срок прошёл",
            )
        )

    @admin.display(description="Напоминание о пересмотре (до 60 дн.)")
    def rkd_planned_review_warning_display(self, obj):
        if not obj or not getattr(obj, "validity_date", None):
            return "—"
        if not _universal_rkd_planned_review_show_warning(obj.validity_date):
            return "—"
        return mark_safe(
            _admin_warning_triangle_html(
                title="Плановый пересмотр: осталось не более 60 дней или срок прошёл",
            )
        )

    autocomplete_fields = (
        "post",
        "author",
        "last_editor",
        "current_responsible",
        "checked_by",
        "approved_by",
        "develop_org",
        "internal_recipients",
        "external_recipients",
    )
    readonly_fields = (
        "date_of_creation",
        "date_of_change",
        "rkd_planned_review_warning_display",
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
                    "validity_date",
                    "rkd_planned_review_warning_display",
                    "language",
                    "internal_recipients",
                    "external_recipients",
                    "status",
                    "related_documents",
                    "develop_org",
                    "document_uploaded_file",
                    "approval_document",
                    "attestation_document",
                )
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
                    "quantity",
                    "note",
                    "weight",
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
    )

    def get_ordering(self, request):
        if request.GET.get("post__id__exact"):
            return ("section_sort_index", "order_in_section", "pk")
        return ("post_id", "section_sort_index", "order_in_section", "pk")

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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("post", "develop_org")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)


@admin.register(ListTechnicalProposal)
class ListTechnicalProposalAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'desig_document_list_technical_proposal', 'status', 'date_of_creation']
    search_fields = ['name', 'desig_document_list_technical_proposal']
    readonly_fields = ('date_of_change',)


    #def save_model(self, request, obj, form, change):
      #  if obj.post and not obj.name:
        #    obj.name = obj.post.name
        #super().save_model(request, obj, form, change)

@admin.register(GeneralDrawingProduct)
class GeneralDrawingProductAdmin(admin.ModelAdmin):
    list_display = (
        'name','category','author','date_of_creation','status','version',
    )
    search_fields = ('name',)
    list_filter = ('category', 'status', 'trl', 'litera')
    readonly_fields = ('date_of_change',)

@admin.register(ElectronicModelProduct)
class ElectronicModelProductAdmin(admin.ModelAdmin):
    list_display = (
        'name','desig_document_electronic_model_product','author','date_of_creation','status','version','trl',
    )
    search_fields = ('name', 'desig_document_electronic_model_product')
    list_filter = ('status', 'trl', 'category', 'develop_org')
    readonly_fields = ('date_of_change',)

@admin.register(GeneralElectricalDiagram)
class GeneralElectricalDiagramAdmin(admin.ModelAdmin):
    list_display = (
        'name','desig_document','author','date_of_creation','status','version',
    )
    search_fields = ('name', 'desig_document', 'author__username')
    list_filter = ('status', 'trl', 'develop_org', 'language')
    readonly_fields = ('date_of_change',)

@admin.register(SoftwareProduct)
class SoftwareProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'desig_document_software_product', 'status', 'version', 'date_of_creation')
    search_fields = ('name', 'desig_document_software_product', 'status')
    list_filter = ('status', 'trl', 'category', 'version')
    readonly_fields = ('date_of_change',)

@admin.register(GeneralDrawingUnit)
class GeneralDrawingUnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'desig_document_general_drawing_unit', 'status', 'version')
    readonly_fields = ('date_of_change',)

@admin.register(ElectronicModelUnit)
class ElectronicModelUnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'desig_document_electronic_model_unit', 'status', 'version')
    readonly_fields = ('date_of_change',)

@admin.register(DrawingPartUnit)
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

@admin.register(ElectronicModelPartUnit)
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

@admin.register(DrawingPartProduct)
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

@admin.register(ElectronicModelPartProduct)
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

@admin.register(ReportTechnicalProposal)
class ReportTechnicalProposalAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'status', 'version',
        'author', 'current_responsible', 'date_of_creation'
    )
    list_filter = ('category', 'status', 'date_of_creation')
    search_fields = ('name', 'desig_document_report_technical_proposal', 'author__username')
    readonly_fields = ('date_of_change',)

@admin.register(AddReportTechnicalProposal)
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

@admin.register(ProtocolTechnicalProposal)
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
    title = "Просрочено?"
    parameter_name = "overdue"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Просрочено"),
            ("no", "Не просрочено"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(is_overdue=True)

        if self.value() == "no":
            return queryset.filter(is_overdue=False)

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
    search_fields = ('name_of_company__icontains', 'address__icontains')  # Поиск по этим полям

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
    fields = ('problem', 'status', 'created_date')
    readonly_fields = ('created_date',)

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

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author')


# Заявки
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    form = SupportTicketForm
    list_display = [
        'id', 'created_date', 'customer', 'product', 'get_category_display',
        'truncated_problem', 'status_badge', 'status_changed_date',
        'created_by', 'assigned_to', 'custom_actions'
    ]
    list_filter = [
        'status', 'category', 'created_date', 'customer',
        'product', 'assigned_to'
    ]
    search_fields = [
        'problem', 'description', 'customer__name_of_company',
        'id', 'created_by__username'
    ]
    readonly_fields = ['created_date', 'status_changed_date', 'created_by']
    inlines = [TicketCommentInline]
    date_hierarchy = 'created_date'
    list_per_page = 25

    fieldsets = (
        ('Основная информация', {
            'fields': ('customer', 'product', 'category', 'problem', 'description')
        }),
        ('Статус и назначение', {
            'fields': ('status', 'assigned_to', 'created_by', 'created_date', 'status_changed_date')
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

    def custom_actions(self, obj):
        view_url = reverse('admin:crm_supportticket_change', args=[obj.id])
        return format_html(
            '<a href="{}">👁️ Просмотр</a>',
            view_url
        )

    custom_actions.short_description = 'Действия'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
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

    truncated_text.short_description = 'Комментарий'

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
    extra = 1

class TransportVehicleFileInline(admin.TabularInline):
    model = TransportVehicleFile
    extra = 1

class ProductionAreaFileInline(admin.TabularInline):
    model = ProductionAreaFile
    extra = 1

class TransportRepairFileInline(admin.TabularInline):
    model = TransportRepairFile
    extra = 1

# Рабочее оборудование
@admin.register(WorkEquipment)
class WorkEquipmentAdmin(admin.ModelAdmin):
    list_display = ("name_type", "serial_number_link", "measuring_device_display", "next_calibration_date_display", "calibration_warning", "calibration_date_warning", "workstation", "status")
    list_filter = ("measuring_device",)
    search_fields = ("name_type", "serial_number", "workstation")
    readonly_fields = ("date_of_creation", "date_of_change")
    exclude = ("version_diff",)
    inlines = [WorkEquipmentFileInline]

    @admin.display(description="Средство измерений")
    def measuring_device_display(self, obj):
        if obj.measuring_device:
            return mark_safe(
                '<img src="/static/admin/img/icon-yes.svg" alt="Да">'
            )
        return "—"

    def next_calibration_date_display(self, obj):
        if not obj.next_calibration_date:
            return "—"
        return obj.next_calibration_date

    next_calibration_date_display.short_description = "Дата плановой поверки"
    next_calibration_date_display.admin_order_field = "next_calibration_date"

    def get_fieldsets(self, request, obj=None):
        main_fields = (
            "name_type",
            "serial_number",
            "measuring_device",
            "next_calibration_date",
            "calibration_required",
            "planned_calibration_date",
            "workstation",
            "replacement_equipment",
            "status",
        )
        if obj is None:
            return (
                (None, {"fields": main_fields}),
                ("Ответственные", {"fields": ("current_responsible",)}),
                ("Версия", {"fields": ("version",)}),
                ("Системная информация", {"fields": ("date_of_creation", "date_of_change", "note")}),
            )
        return (
            (None, {"fields": main_fields}),
            ("Ответственные", {"fields": ("author", "last_editor", "current_responsible")}),
            ("Версия", {"fields": ("version",)}),
            ("Системная информация", {"fields": ("date_of_creation", "date_of_change", "note")}),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.readonly_fields
        return ("author", "last_editor") + tuple(self.readonly_fields)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
        super().save_model(request, obj, form, change)

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
    readonly_fields = (
        "old_target_deadline","old_hard_deadline","old_time_window_start","old_time_window_end",
        "new_target_deadline","new_hard_deadline","new_time_window_start","new_time_window_end",
        "reason","changed_by","changed_at",
    )
    show_change_link = False

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        tech_id = request.GET.get('technical_assignment')
        if tech_id:
            initial['technical_assignment'] = tech_id
        return initial

@admin.register(WorkAssignment)
class WorkAssignmentAdmin(admin.ModelAdmin):
    #form = WorkAssignmentForm

    list_display = (
        'name', 'author', 'executor', 'post',
        'effective_deadline_readonly',
        'overdue_flag',
        'result', 'version',
        'target_deadline', 'hard_deadline',
        'control_status', 'control_date',
        'deadline_version', 'reschedule_count', # служебные
    )
    search_fields = ('name','author__username','current_responsible__username')
    list_filter = ('result','control_status', OverdueFilter)

    readonly_fields = ('date_of_creation','date_of_change',
                       'effective_deadline_readonly','deadline_version','reschedule_count')

    inlines = [DeadlineChangeInline, AttachmentInline]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'name', 'executor', 'category', 'post',
                'author', 'current_responsible', 'version',
                'task', 'acceptance_criteria',
            )
        }),
        ('Сроки (изменять через «Перенести срок»)', {
            'fields': (
                'target_deadline', 'hard_deadline',
                ('time_window_start', 'time_window_end'),
                'conditional_deadline',
                'effective_deadline_readonly',
            )
        }),
        ('Контроль выполнения', {
            'fields': ('control_status', 'control_date', 'result', 'result_description')
        }),
        ('Системная информация', {
            'fields': ('route', 'date_of_creation', 'date_of_change', 'last_editor',
                       'deadline_version','reschedule_count')
        }),
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)
        for name in (
            "target_deadline",
            "hard_deadline",
            "time_window_start",
            "time_window_end",
        ):
            if name in form.base_fields:
                form.base_fields[name].disabled = True
        return form

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        post_id = request.GET.get("post")
        if post_id:
            initial["post"] = post_id
        return initial

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        today = timezone.localdate()

        qs = qs.annotate(
            effective_deadline_db=Case(
                When(hard_deadline__isnull=False, then=F("hard_deadline")),
                default=F("target_deadline"),
                output_field=DateField(),
            )
        )

        qs = qs.annotate(
            is_overdue=Case(
                When(
                    Q(result__isnull=True) & Q(effective_deadline_db__lt=today),
                    then=True
                ),
                default=False,
                output_field=BooleanField(),
            )
        )

        return qs

    def effective_deadline_readonly(self, obj):
        return obj.effective_deadline
    effective_deadline_readonly.short_description = "Эффективный срок"

    def overdue_flag(self, obj):
        return "—" if obj.result else ("⚠️" if obj.is_overdue else "—")
    overdue_flag.short_description = "Просрочено?"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:object_id>/reschedule/",
                self.admin_site.admin_view(self.reschedule_view),
                name="blog_workassignment_reschedule",
            ),
        ]
        return custom + urls

    def reschedule_view(self, request, object_id: int):
        from django.shortcuts import render, redirect, get_object_or_404
        obj = get_object_or_404(WorkAssignment, pk=object_id)

        if request.method == "POST":
            form = RescheduleAdminForm(request.POST)
            if form.is_valid():
                try:
                    WorkAssignmentService.reschedule_deadline(
                        obj,
                        new_target_deadline=form.cleaned_data.get("new_target_deadline"),
                        new_hard_deadline=form.cleaned_data.get("new_hard_deadline"),
                        new_time_window_start=form.cleaned_data.get("new_time_window_start"),
                        new_time_window_end=form.cleaned_data.get("new_time_window_end"),
                        reason=form.cleaned_data.get("reason", ""),
                        user=request.user if request.user.is_authenticated else None,
                        expected_deadline_version=form.cleaned_data["expected_deadline_version"],
                    )
                except ValueError as e:
                    messages.error(request, str(e))
                except RuntimeError as e:
                    messages.error(request, str(e))  # конфликт версий
                else:
                    messages.success(request, "Срок успешно перенесён.")
                    return redirect(f"../change/")
        else:
            form = RescheduleAdminForm(initial={
                "new_target_deadline": obj.target_deadline,
                "new_hard_deadline": obj.hard_deadline,
                "new_time_window_start": obj.time_window_start,
                "new_time_window_end": obj.time_window_end,
                "expected_deadline_version": obj.deadline_version,
            })

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": obj,
            "title": "Перенести срок",
            "form": form,
            "object_id": object_id,
            "has_view_permission": self.has_view_permission(request, obj),
            "has_change_permission": self.has_change_permission(request, obj),
        }
        return render(request, "admin/blog/workassignment/reschedule.html", context)

@admin.register(WorkAssignmentDeadlineChange)
class WorkAssignmentDeadlineChangeAdmin(admin.ModelAdmin):
    list_display = ("id","assignment","changed_by","changed_at",
                    "old_target_deadline","new_target_deadline",
                    "old_hard_deadline","new_hard_deadline")
    list_filter = ("changed_by","changed_at")
    search_fields = ("assignment__name","reason")

@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


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
    autocomplete_fields = (
        "author",
        "last_editor",
        "current_responsible",
        "check_document",
        "approval_document",
    )

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
    list_display = (
        "current_step_display",          # вычисляемый «Текущий шаг»
        "current_reviewer_display",      # вычисляемый «Проверяющий сейчас»
        "it_responsible_display",        # ответственные по этапам (ниже методы)
        "tech_responsible_display",
        "m3d_responsible_display",
        "norm_responsible_display",
        "date_of_change",
    )
    search_fields = (
        "desig_or_name_document",
        "types_check_document",
        "author__username",
        "last_editor__username",
        "current_responsible__username",
        "check_it_requirements_responsible__username",
        "check_technical_requirements_responsible__username",
        "check_3D_model_responsible__username",
        "norm_control_responsible__username",
    )
    list_filter = (
        "process_sequence",
        "check_it_requirements",
        "check_technical_requirements",
        "check_3D_model",
        "norm_control",
    )
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

    list_display = [
        'display_document_title',
        'display_approval',
        'display_date_approval',
        'display_accept',
        'display_author',
        'display_date_of_change',
        'display_version',
        'display_uploaded_file',
        'display_document_purpose',
        'display_note',
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
    ]

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
            )
        }),
        ('Ознакомление', {
            'fields': (
                'accept',
                #'signature_accept',
            )
        }),
        ('Пользователи системы', {
            'fields': (
                'author',
                'last_editor',
                'current_responsible',
            )
        }),
        ('Даты и время', {
            'fields': (
                'date_of_creation',
                'date_of_change',
            )
        }),
    )

    # --- Кастомные отображения для соответствия ТЗ ---

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

    def display_files_list(self, obj):
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

    display_files_list.short_description = 'Файлы документа'

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
        ('Версия и даты', {
            'fields': (
                'version',
                'date_of_creation',
                'date_of_change',
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
    list_display = [
        'display_document_title',
        'display_category',
        'change_number',
        'display_approval',
        'display_date_approval',
        'display_accept',
        'display_uploaded_file',
        'display_review_date',
        'display_review_status',
        'document_purpose',
        'display_related_documents',
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
    ]

    filter_horizontal = ['related_documents']

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
        ('Связанные отдельные документы', {
            'fields': ('related_documents',),
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
        """Отображение связанных отдельных документов в списке"""
        docs = obj.related_documents.all()
        if docs.exists():
            return ", ".join([doc.document_title for doc in docs[:3]]) + ("..." if docs.count() > 3 else "")
        return "—"

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
    list_display = [
        'registration_number',
        'enterprise_display',
        'order_date',
        'subject_short',
        'approval_display',
        'scope_display',
        'status_display',
        'validity_date_warning',
        'uploaded_file'
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
        #'registration_number',
        'author',
        'date_of_creation',
        'last_editor',
        'date_of_change',
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