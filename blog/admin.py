from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from datetime import timedelta
from django.utils.html import format_html
from django.utils.safestring import mark_safe
import re
from django.db.models import Q, F, Value, TextField, DateField, BooleanField, Case, When
from functools import reduce
from operator import and_, or_
from django.forms.models import BaseInlineFormSet
from django.forms import ValidationError
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.contenttypes.forms import BaseGenericInlineFormSet

from crm.models import Notifications, Customer, Decision_maker, Deal, Product, Deal_stage, Call, Letter, Company_branch, Meeting, MeetingFile, SupportTicket, TicketComment, KnowledgeBaseArticle
from crm.forms import TicketCommentForm, KnowledgeBaseArticleForm, SupportTicketForm
from shared_repository.models import SharedRepository
from enterprise_asset_management.models import WorkEquipment, WorkEquipmentFile, TransportVehicle, ProductionArea, ProductionAreaFile, TransportVehicleFile, TransportRepair, TransportRepairFile

from .admin_forms import RescheduleAdminForm
from .forms import WorkAssignmentForm
from .helpers import (
    first_incomplete_step_code,
    next_step_code_after,
    PROCESS_FIELD_MAP,
    wf_step_is_signed,
    wf_step_responsible,
    wf_step_set_comment,
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
)
from .services import WorkAssignmentService

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
    extra = 1


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('name', 'desig_document_post', 'author', 'date_of_creation', 'date_of_change')
    search_fields = ('name',)
    readonly_fields = ('date_of_change',)
    inlines = [ListTechnicalProposalInline, TaskForDesignWorkInline, RevisionTaskInline, WorkAssignmentInline]

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
    list_display = ('name_of_company', 'revenue_for_last_year', 'length_of_electrical_network_km')
    # Объедини фильтры в один список
    list_filter = ('name_of_company', 'revenue_for_last_year')
    list_filter = (RevenueRangeFilter,)
    search_fields = ('name_of_company__icontains', 'address__icontains')  # Поиск по этим полям

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


@admin.register(Letter)
class LetterAdmin(admin.ModelAdmin):
    list_display = ('incoming_number', 'customer', 'planned_date', 'responsible', 'deal')
    search_fields = ('incoming_number', 'responsible_person_from_customer')
    list_filter = ('planned_date',)
    date_hierarchy = 'planned_date'


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

@admin.register(MeetingFile)
class MeetingFileAdmin(admin.ModelAdmin):
    list_display = ['meeting', 'file', 'description', 'uploaded_at']
    list_filter = ['uploaded_at', 'meeting']
    search_fields = ['meeting__customer__name_of_company', 'description']




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


# База знаний
@admin.register(KnowledgeBaseArticle)
class KnowledgeBaseArticleAdmin(admin.ModelAdmin):
    form = KnowledgeBaseArticleForm
    list_display = [
        'title', 'get_category_display', 'created_date', 'updated_date',
        'author', 'status_badge', 'custom_actions'
    ]
    list_filter = ['status', 'category', 'created_date', 'author']
    search_fields = ['title', 'content', 'author__username']
    readonly_fields = ['created_date', 'updated_date', 'author']
    list_per_page = 25

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'category', 'status')
        }),
        ('Содержание', {
            'fields': ('content', 'file')
        }),
        ('Системная информация', {
            'fields': ('author', 'created_date', 'updated_date'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        status_colors = {
            'draft': 'gray',
            'published': 'green',
            'archived': 'red'
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )

    status_badge.short_description = 'Статус'

    def custom_actions(self, obj):
        view_url = reverse('admin:crm_knowledgebasearticle_change', args=[obj.id])
        return format_html(
            '<a href="{}">👁️ Просмотр</a>',
            view_url
        )

    custom_actions.short_description = 'Действия'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author')


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
            "replacement_allowed",
            "status",
        )
        if obj is None:
            return (
                (None, {"fields": main_fields}),
                ("Ответственные", {"fields": ("current_responsible", "note")}),
                ("Версия", {"fields": ("version",)}),
                ("Системная информация", {"fields": ("date_of_creation", "date_of_change")}),
            )
        return (
            (None, {"fields": main_fields}),
            ("Ответственные", {"fields": ("author", "last_editor", "current_responsible", "note")}),
            ("Версия", {"fields": ("version",)}),
            ("Системная информация", {"fields": ("date_of_creation", "date_of_change")}),
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
    def serial_number_link(self, obj):
        if not obj.serial_number:
            return "—"

        url = reverse(
            "admin:enterprise_asset_management_workequipment_change",
            args=[obj.pk],
        )
        return format_html('<a href="{}">{}</a>', url, obj.serial_number)

    serial_number_link.short_description = "Заводской номер (s/n)"
    serial_number_link.admin_order_field = "serial_number"

    def calibration_warning(self, obj):
        if not obj.measuring_device or not obj.next_calibration_date:
            return "—"

        today = timezone.now().date()
        days_left = (obj.next_calibration_date - today).days

        if days_left <= 45:
            return mark_safe(
                '<span style="color: #f0ad4e; font-weight: bold;">⚠️</span>'
            )

        return "—"

    calibration_warning.short_description = "Срок поверки истекает"

    def calibration_date_warning(self, obj):
        if not obj.calibration_required or not obj.planned_calibration_date:
            return "—"
        today = timezone.now().date()
        days_left = (obj.planned_calibration_date - today).days
        if days_left <= 45:
            return mark_safe(
                '<span style="color: #f0ad4e; font-weight: bold;">⚠️</span>'
            )
        return "—"

    calibration_date_warning.short_description = "Срок калибровки истекает"

# Транспорт
@admin.register(TransportVehicle)
class TransportVehicleAdmin(admin.ModelAdmin):

    list_display = (
        "make_model",
        "registration_plate",
        "insurance",
        "next_insurance_date",
        "inspection",
        "next_inspection_date",
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


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("repairs")

#ремонтТС
@admin.register(TransportRepair)
class TransportRepairAdmin(admin.ModelAdmin):

    list_display = (
        "transport_vehicle",
        "repair_date",
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
@admin.register(ProductionArea)
class ProductionAreaAdmin(admin.ModelAdmin):

    list_display = (
        "number_name",
        "object",
        "location",
        "working_conditions",
        "restrictions",
        "contract_status_display",
    )

    list_display_links = ("number_name",)

    list_filter = (
        "object",
        "location",
        "working_conditions",
        "restrictions",
    )

    search_fields = ("number_name",)

    inlines = [ProductionAreaFileInline]

    fieldsets = (
        ("Основная информация", {
            "fields": (
                "object",
                "location",
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

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        obj.last_editor = request.user
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

    contract_status_display.short_description = "Срок договора"

class WorkAssignmentInline(admin.TabularInline):
    model = WorkAssignment
    extra = 0
    fields = ('name', 'deadline', 'result')
    readonly_fields = ('name',)

    def get_extra_buttons(self, obj):
        if obj and obj.id:
            url = reverse('admin:blog_workassignment_add') + f'?technical_assignment={obj.id}'
            return format_html('<a class="button" href="{}">➕ Добавить рабочее задание</a>', url)
        return ''

    def get_fieldsets(self, request, obj=None):
        """Добавляем кнопку прямо в заголовок инлайна"""
        fieldsets = super().get_fieldsets(request, obj)
        if obj and obj.id:
            return [(f"Рабочие задания {self.get_extra_buttons(obj)}", {'fields': self.fields})]
        return fieldsets

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

@admin.register(SharedRepository)
class SharedRepositoryAdmin(admin.ModelAdmin):
    list_display = [
        'id_display',
        'document_title_display',
        'version_display',
        'author_display',
        'current_responsible_display',
        'date_of_creation_display',
        'date_of_change_display',
        'uploaded_file_display',
    ]

    list_filter = [
        'author',
        'current_responsible',
        'date_of_creation',
    ]

    search_fields = [
        'document_title',
        'document_purpose',
        'id',
    ]

    readonly_fields = [
        'id',
        'date_of_creation',
        'date_of_change',
        'uploaded_file_info',
    ]

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'id',
                'document_title',
                'version',
                'uploaded_file',
                'uploaded_file_info',
                'document_purpose',
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

    # Кастомные отображения для соответствия ТЗ

    def id_display(self, obj):
        """Отображение id как в ТЗ: 'id: хххххххх'"""
        return format_html(
            '<strong>id:</strong> {}',
            obj.id
        )

    id_display.short_description = 'Уникальный идентификатор'
    id_display.admin_order_field = 'id'

    def document_title_display(self, obj):
        """Отображение названия документа как в ТЗ: 'document title: Название'"""
        return format_html(
            '<strong>document title:</strong> {}',
            obj.document_title
        )

    document_title_display.short_description = 'Название документа'
    document_title_display.admin_order_field = 'document_title'

    def version_display(self, obj):
        """Отображение версии как в ТЗ: 'version: 1*'"""
        return format_html(
            '<strong>version:</strong> {}',
            obj.version
        )

    version_display.short_description = 'Версия'
    version_display.admin_order_field = 'version'

    def author_display(self, obj):
        """Отображение автора как в ТЗ: 'author: NeradovskayaIV'"""
        return format_html(
            '<strong>author:</strong> {}',
            obj.author.username
        )

    author_display.short_description = 'Создатель (автор)'
    author_display.admin_order_field = 'author__username'

    def current_responsible_display(self, obj):
        """Отображение ответственного как в ТЗ: 'current_responsible: NeradovskayaIV'"""
        return format_html(
            '<strong>current_responsible:</strong> {}',
            obj.current_responsible.username
        )

    current_responsible_display.short_description = 'Текущий ответственный'
    current_responsible_display.admin_order_field = 'current_responsible__username'

    def date_of_creation_display(self, obj):
        """Отображение даты создания как в ТЗ: 'date_of_creation: 2025-04-03 14:52:13'"""
        return format_html(
            '<strong>date_of_creation:</strong> {}',
            obj.date_of_creation.strftime('%Y-%m-%d %H:%M:%S')
        )

    date_of_creation_display.short_description = 'Дата и время создания'
    date_of_creation_display.admin_order_field = 'date_of_creation'

    def date_of_change_display(self, obj):
        """Отображение даты изменения как в ТЗ: 'date_of_change: 2025-04-04 11:53:15'"""
        return format_html(
            '<strong>date_of_change:</strong> {}',
            obj.date_of_change.strftime('%Y-%m-%d %H:%M:%S')
        )

    date_of_change_display.short_description = 'Дата и время последнего изменения'
    date_of_change_display.admin_order_field = 'date_of_change'

    def uploaded_file_display(self, obj):
        """Отображение файла как в ТЗ: 'uploaded_file: имя файла'"""
        if obj.uploaded_file:
            filename = obj.uploaded_file.name.split('/')[-1]  # Только имя файла
            return format_html(
                '<strong>uploaded_file:</strong> <a href="{}" target="_blank">{}</a>',
                obj.uploaded_file.url,
                filename
            )
        return format_html(
            '<strong>uploaded_file:</strong> Нет файла'
        )

    uploaded_file_display.short_description = 'Загружаемый файл'

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
        if 'id' in form.base_fields:
            form.base_fields['id'].help_text = 'Уникальное поле'

        if 'document_title' in form.base_fields:
            form.base_fields['document_title'].help_text = 'Уникальное поле. Все текстовые символы - 100 символов max'

        if 'author' in form.base_fields:
            form.base_fields['author'].help_text = 'Имя пользователя системы (ссылка на User)'

        if 'date_of_creation' in form.base_fields:
            form.base_fields['date_of_creation'].help_text = 'Формат: YYYY-MM-DD HH:MI:SS'

        if 'last_editor' in form.base_fields:
            form.base_fields['last_editor'].help_text = 'Имя пользователя системы (ссылка на User)'

        if 'date_of_change' in form.base_fields:
            form.base_fields['date_of_change'].help_text = 'Формат: YYYY-MM-DD HH:MI:SS'

        if 'current_responsible' in form.base_fields:
            form.base_fields['current_responsible'].help_text = 'Имя пользователя системы (ссылка на User)'

        if 'version' in form.base_fields:
            form.base_fields['version'].help_text = 'Цифры, 3 символа max. Значение по умолчанию: 1'

        if 'uploaded_file' in form.base_fields:
            form.base_fields[
                'uploaded_file'].help_text = 'Текст, строго в соответствии с данными в колонке "Визуализация"'

        if 'document_purpose' in form.base_fields:
            form.base_fields['document_purpose'].help_text = 'Все текстовые символы - 5000 символов max'

        return form