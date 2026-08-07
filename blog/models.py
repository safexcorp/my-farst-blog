from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from datetime import date, datetime

from .helpers import (
    SPECIFICATION_SECTION_CHOICES,
    allowed_categories_for_section,
    section_allows_position,
    section_allows_quantity_weight,
    section_has_category_choices,
    specification_section_sort_index,
)

User = settings.AUTH_USER_MODEL
User = get_user_model()

_INVALID_DATE_MSG = "Укажите дату в формате ДД.ММ.ГГГГ (например, 01.07.2026)."


def _as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _normalize_model_dates(instance, field_names):
    normalized = {}
    errors = {}
    for name in field_names:
        raw = getattr(instance, name, None)
        coerced = _as_date(raw)
        if raw not in (None, "") and coerced is None:
            errors[name] = _INVALID_DATE_MSG
        else:
            normalized[name] = coerced
            if coerced is not None:
                setattr(instance, name, coerced)
    return normalized, errors


class technical_design(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class prelim_design(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class WorkingDocumentation(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class PilotSample(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class Procurement(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class ProductionLaunch(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class Production(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class Sales(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class Service(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class Patenting(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title


class ConformityAssessment(models.Model):
    title = models.CharField(max_length=255)

    def __str__(self): return self.title





class ProductGroup(models.Model):
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Наименование группы разработок",
    )
    designation = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Обозначение группы разработок",
    )
    main_purpose = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Основное назначение группы разработок",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_product_groups",
        verbose_name="Автор",
    )
    last_editor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_product_groups",
        verbose_name="Последний редактор",
    )
    date_of_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата и время создания",
    )
    date_of_change = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата и время последнего изменения",
    )

    class Meta:
        verbose_name = "Группа разработок"
        verbose_name_plural = "Группы разработок (модификаций)"
        ordering = ("name",)

    def __str__(self):
        return self.name


class ProductGroupDocument(models.Model):
    """Документы, привязанные к общей группе разработок (основной PDF / исходник)."""

    KIND_MAIN = "main"
    KIND_SOURCE = "source"
    KIND_CHOICES = [
        (KIND_MAIN, "Основной (PDF)"),
        (KIND_SOURCE, "Исходный (DOCX)"),
    ]

    product_group = models.ForeignKey(
        ProductGroup,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="Группа разработок",
    )
    title = models.CharField(
        max_length=500,
        verbose_name="Название и обозначение документа",
    )
    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES,
        default=KIND_MAIN,
        verbose_name="Вид документа",
    )
    file = models.FileField(
        upload_to="blog/productgroup/documents/%Y/%m/",
        verbose_name="Файл",
    )
    note = models.TextField(
        max_length=5000,
        blank=True,
        default="",
        verbose_name="Примечание",
    )

    class Meta:
        verbose_name = "Документ группы разработок"
        verbose_name_plural = "Документы группы разработок"
        ordering = ("pk",)

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        f = self.file
        if not f or not getattr(f, "name", None):
            return
        name = f.name.lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        if self.kind == self.KIND_MAIN and ext != "pdf":
            raise ValidationError({"file": "Для вида «Основной» допускается только PDF."})
        if self.kind == self.KIND_SOURCE and ext not in ("docx", "doc"):
            raise ValidationError(
                {"file": "Для вида «Исходный» загрузите DOCX или DOC."}
            )


class Post(models.Model):
    LITERA_CHOICES = [
        ('П', 'П'),
        ('Э', 'Э'),
        ('Т', 'Т'),
        ('О', 'О'),
        ('О1', 'О₁'),
        ('О2', 'О₂'),
        ('О3', 'О₃'),
        ('А', 'А'),
        ('Б', 'Б'),
        ('И', 'И'),
    ]

    TRL_CHOICES = [
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
        ('4', '4'),
        ('5', '5'),
        ('6', '6'),
        ('7', '7'),
        ('8', '8'),
        ('9', '9'),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Наименование изделия (продукта) краткое",
    )
    name_full = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Наименование изделия (продукта) полное",
    )
    desig_document_post = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name="Обозначение изделия (продукта)",
    )
    is_group_modification = models.BooleanField(
        default=False,
        verbose_name="Является исполнением (модификацией) группы изделий",
    )
    product_group = models.ForeignKey(
        "ProductGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
        verbose_name="Группа разработок",
    )
    group_modification_features = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Характерные особенности исполнения (модификация)",
    )
    main_purpose = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Основное назначение изделия (продукта)",
    )
    main_purpose_own = models.TextField(
        max_length=2000,
        blank=True,
        null=True,
        default="",
        verbose_name="Основное назначение изделия (продукта)",
    )
    order_article = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Запись при заказе (артикул)",
    )
    note = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Примечание",
    )
    group_documents = models.FileField(
        upload_to="blog/post/group_documents/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Общие документы группы изделий",
    )
    wa_code = models.CharField(
        max_length=3,
        blank=True,
        null=True,
        unique=True,
        editable=False,
        verbose_name="Буквенный код для рабочих заданий",
        help_text="Назначается автоматически при создании первого рабочего задания.",
    )
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_posts',
                               verbose_name="Автор")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='edited_posts',
                                    verbose_name="Последний редактор")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                            related_name='responsible_posts', verbose_name="Текущий ответственный")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    version = models.CharField(max_length=20, default='1', verbose_name="Версия")
    version_diff = models.TextField(max_length=1000, blank=True, default='Стартовая версия',
                                    verbose_name="Сравнение версий")
    litera = models.CharField(max_length=20, choices=LITERA_CHOICES, default='П',
                              verbose_name="Стадия разработки (литера)")
    trl = models.CharField(max_length=10, choices=TRL_CHOICES, default='1',
                           verbose_name="Уровень готовности технологий (TRL)")

    prelim_design = models.OneToOneField(prelim_design, on_delete=models.SET_NULL, null=True, blank=True,
                                         verbose_name="Эскизный проект")
    technical_design = models.OneToOneField(technical_design, on_delete=models.SET_NULL, null=True, blank=True,
                                            verbose_name="Технический проект")
    working_documentation = models.OneToOneField(WorkingDocumentation, on_delete=models.SET_NULL, null=True, blank=True,
                                                 verbose_name="Рабочая КД")
    pilot_samples = models.OneToOneField(PilotSample, on_delete=models.SET_NULL, null=True, blank=True,
                                         verbose_name="Опытные образцы")
    procurement = models.ManyToManyField(Procurement, blank=True, verbose_name="Закупки")
    production_launch = models.OneToOneField(ProductionLaunch, on_delete=models.SET_NULL, null=True, blank=True,
                                             verbose_name="Постановка на производство")
    production = models.OneToOneField(Production, on_delete=models.SET_NULL, null=True, blank=True,
                                      verbose_name="Производство")
    sales = models.OneToOneField(Sales, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Продажи")
    service = models.OneToOneField(Service, on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name="Сервисное обслуживание")
    patenting = models.ManyToManyField(Patenting, blank=True, verbose_name="Патентование")
    conformity_assessment = models.OneToOneField(ConformityAssessment, on_delete=models.SET_NULL, null=True, blank=True,
                                                 verbose_name="Подтверждение соответствия")

    in_production = models.BooleanField(
        default=False,
        verbose_name="Постановка на производство",
    )
    in_production_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата постановки на производство",
    )
    modification_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Код модификации изделия",
    )
    validity_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Срок действия",
    )
    develop_org = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Организация-разработчик",
    )
    manufacturer_org_post = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Организация-изготовитель",
    )
    technical_specifications_ref = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Технические условия (обозначение / ссылка)",
    )
    operating_manual_ref = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Руководство по эксплуатации (обозначение / ссылка)",
    )
    product_passport_ref = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Паспорт изделия (обозначение / ссылка)",
    )

    class Meta:
        verbose_name = "Разработка"
        verbose_name_plural = "Разработки (модификации)"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not (self.name_full or "").strip():
            self.name_full = None
        if not (self.desig_document_post or "").strip():
            self.desig_document_post = None
        if self.is_group_modification and not self.product_group_id:
            raise ValidationError({
                "product_group": "Выберите общую группу разработок или снимите галочку.",
            })
        if self.in_production and not self.in_production_date:
            raise ValidationError({
                "in_production_date": "Укажите дату постановки на производство.",
            })


class GeneralDrawingProduct(models.Model):

    INFO_FORMAT_CHOICES = [
        ('ДЭ', 'ДЭ'),
        ('ДБ', 'ДБ'),
    ]

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]


    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    category = models.CharField(max_length=50, default='ВО', verbose_name="Категория")
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='general_drawin_products')
    name = models.CharField(max_length=100, default='ПАК СПМ 2.13 Чертеж общего вида изделия', verbose_name="Наименование")
    desig_document_general_drawing_product = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", null=True)
    info_format = models.CharField(max_length=20, choices=INFO_FORMAT_CHOICES, verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='gd_created_by', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    change_number = models.CharField(max_length=20, default='Без изм.', verbose_name="Номер изменения")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='gd_edited_by', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='gd_responsible', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, blank=True, choices=PRIORITY_CHOICES, verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(max_length=1000, blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=20, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(max_length=1000,blank=True,default='',verbose_name="Связанные сопроводительные документы")
    pattern = models.FileField(upload_to='uploads/', blank = True,null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, blank=True, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, blank=True, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Чертеж общего вида изделия'
        verbose_name_plural = 'Чертежи общего вида изделия'

    def __str__(self):
        return self.name

    def __str__(self): return self.name


class ElectronicModelProduct(models.Model):
    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]

    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    INFO_FORMAT_CHOICES = [
        ('ДЭ', 'ДЭ'),
        ('ДБ', 'ДБ'),
    ]

    TRL_CHOICES = [
        ('1', '1'), ('2-', '2-'), ('2', '2'), ('3-', '3-'), ('3', '3'),
    ]

    category = models.CharField(max_length=50, default='ЭМИ', verbose_name="Категория")
    name = models.CharField(max_length=100, default='ПАК СПМ 2.13 Электронная модель изделия', verbose_name="Наименование")
    desig_document_electronic_model_product = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", default='1')
    info_format = models.CharField(max_length=20, choices= INFO_FORMAT_CHOICES, verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='Без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='electronicmodel_author', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='electronicmodel_last_editor', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='electronicmodel_responsible', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=20, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, choices=TRL_CHOICES, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.TextField(blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_docs = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")

    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Электронная модель изделия'
        verbose_name_plural = 'Электронные модели изделия'

    def __str__(self):
        return self.name


class GeneralElectricalDiagram(models.Model):
    INFO_FORMAT_CHOICES = [
        ('ДЭ', 'ДЭ'),
        ('ДБ', 'ДБ'),
    ]

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]


    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]

    category = models.CharField(max_length=50, default='Э6', verbose_name="Категория")
    name = models.CharField(max_length=100, default='ПАК СПМ 2.13 Схема электрическая общая', verbose_name="Наименование")
    desig_document = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", default='1')
    info_format = models.CharField(max_length=20, choices=INFO_FORMAT_CHOICES, default='ДЭ', verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='Без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Схема электрическая общая'
        verbose_name_plural = 'Схемы электрические общие'

    def __str__(self):
        return self.name


class SoftwareProduct(models.Model):
    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]

    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    category = models.CharField(max_length=50, default='ПО ПТ', verbose_name="Категория")
    name = models.CharField(max_length=100, default='ПАК СПМ 2.13  Программное обеспечение. Техническое предложение', verbose_name="Наименование")
    desig_document_software_product = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", default='1')
    info_format = models.CharField(max_length=30, default='ДЭ', verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, blank=True, choices=PRIORITY_CHOICES, verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Программное обеспечение Технического предложения'
        verbose_name_plural = 'Программные обеспечения Технического предложения'

    def __str__(self):
        return self.name


class ReportTechnicalProposal(models.Model):
    category = models.CharField(max_length=50, default="ПЗ ПТ", verbose_name="Категория")

    name = models.CharField(max_length=100, verbose_name="Наименование")

    INFO_FORMAT_CHOICES = [
        ("ДБ", "ДБ"),
        ("ДЭ", "ДЭ"),
    ]
    info_format = models.CharField(max_length=10, choices=INFO_FORMAT_CHOICES, default="ДЭ", blank=True, verbose_name="Формат представления информации")

    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank = True, related_name='+', verbose_name="Текущий ответственный")

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Загружаемый файл")

    DEVELOP_ORG_CHOICES = [
        ('ООО "СИСТЕМА"', 'ООО "СИСТЕМА"'),
    ]
    develop_org = models.CharField(max_length=100, choices=DEVELOP_ORG_CHOICES, default='ООО "СИСТЕМА"', blank=True, verbose_name="Организация-разработчик")

    LANGUAGE_CHOICES = [
        ('rus', 'rus'),
        ('eng', 'eng'),
    ]
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='rus', blank=True, verbose_name="Язык")

    uploaded_file = models.FileField(upload_to='uploads/', default=0, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Пояснительна записка Технического предложения'
        verbose_name_plural = 'Пояснительные записки Технического предложения'

    def __str__(self):
        return self.name


class ProtocolTechnicalProposal(models.Model):

    INFO_FORMAT_CHOICES = [
        ("ДБ", "ДБ"),
        ("ДЭ", "ДЭ"),
    ]

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]

    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]

    category = models.CharField(
        max_length=100,
        default="Протокол ПТ",
        verbose_name="Категория"
    )
    name = models.CharField(max_length=100, unique=True, verbose_name="Наименование")
    info_format = models.CharField(max_length=10, choices=INFO_FORMAT_CHOICES, default="ДЭ", blank=True, verbose_name="Формат представления информации")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, blank=True, choices=PRIORITY_CHOICES, verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = "Протокол. Техническое предложение"
        verbose_name_plural = "Протоколы. Технические предложения"

    def __str__(self):
        return f"{self.name} — {self.version}"


class GeneralDrawingUnit(models.Model):
    INFO_FORMAT_CHOICES = [
        ('ДБ', 'ДБ'),
        ('ДЭ', 'ДЭ'),
    ]
    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]
    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    TRL_CHOICES = [('1-', '1-'), ('2-', '2-'), ('2', '2'), ('3-', '3-'), ('3', '3')]
    LANGUAGE_CHOICES = [('rus', 'rus'), ('eng', 'eng')]
    ACCESS_LEVEL_CHOICES = [('О', 'общий'), ('К', 'конфиденциально'), ('С', 'секретно'), ('СС', 'совершенно секретно')]

    category = models.CharField(max_length=50, default='ВО СЕ', verbose_name="Категория")
    name = models.CharField(max_length=100, verbose_name="Наименование")
    desig_document_general_drawing_unit = models.CharField(max_length=50, unique=True, blank= False, null= False,verbose_name="Обозначение документа")
    info_format = models.CharField(max_length=20, choices=INFO_FORMAT_CHOICES, default='ДЭ', verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Чертеж общего вида сборочной единицы'
        verbose_name_plural = 'Чертежи общего вида сборочной еденицы'

    def __str__(self):
        return self.name


class ElectronicModelUnit(models.Model):
    INFO_FORMAT_CHOICES = [
        ('ДБ', 'ДБ'),
        ('ДЭ', 'ДЭ'),
    ]
    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]
    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    TRL_CHOICES = [('1-', '1-'), ('2-', '2-'), ('2', '2'), ('3-', '3-'), ('3', '3')]
    LANGUAGE_CHOICES = [('rus', 'rus'), ('eng', 'eng')]
    ACCESS_LEVEL_CHOICES = [('О', 'общий'), ('К', 'конфиденциально'), ('С', 'секретно'), ('СС', 'совершенно секретно')]

    category = models.CharField(max_length=50, default='ЭМ СЕ', verbose_name="Категория")
    name = models.CharField(max_length=100, default='Узел 1 Электронная модель сборочной единицы', verbose_name="Наименование")
    desig_document_electronic_model_unit = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа")
    info_format = models.CharField(max_length=20, choices=INFO_FORMAT_CHOICES, default='ДЭ', verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='Изм. 1', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Электронная модель сборочной единицы'
        verbose_name_plural = 'Электронные модели сборочной единицы'

    def __str__(self):
        return self.name


class DrawingPartUnit(models.Model):
    INFO_FORMAT_CHOICES = [
        ('ДБ', 'ДБ'),
        ('ДЭ', 'ДЭ'),
    ]
    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]

    category = models.CharField(max_length=20, default='ЧД СЕ', verbose_name="Категория")
    name = models.CharField(max_length=100, verbose_name="Наименование")
    desig_document_drawing_part_unit = models.CharField(max_length=50, unique=True, verbose_name="Обозначение изделия", default='1')
    info_format = models.CharField(max_length=10, choices=INFO_FORMAT_CHOICES, default='ДЭ', verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='Без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Чертеж детали сборочной единицы'
        verbose_name_plural = 'Чертежи детали сборочной единицы'

    def __str__(self):
        return self.name


class ElectronicModelPartUnit(models.Model):

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]
    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]

    INFO_FORMAT_CHOICES = [
        ('ДБ', 'ДБ'),
        ('ДЭ', 'ДЭ'),
    ]

    category = models.CharField(default='ЭМД СЕ', max_length=100, verbose_name="Категория")
    name = models.CharField(max_length=100, verbose_name="Наименование")
    desig_document_electronic_model_part_unit = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", default='1')
    info_format = models.CharField(max_length=50, choices= INFO_FORMAT_CHOICES, verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, blank=True, choices=PRIORITY_CHOICES, verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Электронная модель детали СЕ'
        verbose_name_plural = 'Электронные модели деталей СЕ'

    def __str__(self):
        return f"{self.desig_document_electronic_model_part_unit} — {self.name}"


class DrawingPartProduct(models.Model):
    INFO_FORMAT_CHOICES = [
        ("ДЭ", "ДЭ"),
        ("ДБ", "ДБ"),
    ]
    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]
    PRIORITY_CHOICES = [
        ("Срочно", "Срочно"),
        ("Высокий", "Высокий"),
        ("Средний", "Средний"),
        ("Низкий", "Низкий"),
    ]
    TRL_CHOICES = [
        ("1-", "1-"), ("2-", "2-"), ("2", "2"), ("3-", "3-"), ("3", "3"),
    ]
    ACCESS_LEVEL_CHOICES = [
        ("О", "Общий"),
        ("К", "Конфиденциально"),
        ("С", "Секретно"),
        ("СС", "Совершенно секретно"),
    ]

    category = models.CharField(max_length=50, default="ЧД ВО", verbose_name="Категория")
    name = models.CharField(max_length=100, unique=True, verbose_name="Наименование")
    desig_document_drawing_part_product = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", default='1')
    info_format = models.CharField(max_length=10, choices=INFO_FORMAT_CHOICES, default="ДЭ", verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='Без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Чертеж детали изделия'
        verbose_name_plural = 'Чертежи детали изделия'

    def __str__(self):
        return f"{self.desig_document_drawing_part_product} — {self.name}"


class ElectronicModelPartProduct(models.Model):

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
        ]
    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    INFO_FORMAT_CHOICES = [
        ("ДЭ", "ДЭ"),
        ("ДБ", "ДБ"),
    ]

    category = models.CharField(max_length=50, default="ЭМД ВО", verbose_name="Категория")
    name = models.CharField(max_length=100, verbose_name="Наименование")
    desig_document_electronic_model_part_product = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", default='1')
    info_format = models.CharField(max_length=20, choices= INFO_FORMAT_CHOICES, verbose_name="Формат представления информации")
    primary_use = models.CharField(max_length=100, default='СИ.40522001.000.13ВПТ', verbose_name="Первичное применение")
    change_number = models.CharField(max_length=20, default='без изм.', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, blank=True, choices=PRIORITY_CHOICES, verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    class Meta:
        verbose_name = 'Электронная модель детали изделия'
        verbose_name_plural = 'Электронные модели детали изделия'

    def __str__(self):
        return f"{self.desig_document_electronic_model_part_product} — {self.name}"


class AddReportTechnicalProposal(models.Model):
    category = models.CharField(max_length=50, default="ПЗ ПТ. Приложение", verbose_name="Категория")

    name = models.CharField(max_length=100, verbose_name="Наименование")

    INFO_FORMAT_CHOICES = [
        ("ДБ", "ДБ"),
        ("ДЭ", "ДЭ"),
    ]
    info_format = models.CharField(max_length=10, choices=INFO_FORMAT_CHOICES, default="ДЭ", blank=True, verbose_name="Формат представления информации")


    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве',  'В архиве')
    ]
    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]
    status = models.CharField(max_length=30, default='Зарегистрирован', verbose_name="Статус (состояние)")

    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    #litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    #trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    priority = models.CharField(max_length=30, blank=True, choices=PRIORITY_CHOICES, verbose_name="Приоритет в работе")

    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    #uploaded_file_1 = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    LANGUAGE_CHOICES = [
        ('rus', 'rus'),
        ('eng', 'eng'),
    ]
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='rus', verbose_name="Язык")

    class Meta:
        verbose_name = 'Приложение к пояснительной записке Технического предложения'
        verbose_name_plural = 'Приложения к пояснительным запискам Технического предложения'

    def __str__(self):
        return self.name or f"ПЗ ПТ. Приложение {self.id}"


class ListTechnicalProposal(models.Model):
    INFO_FORMAT_CHOICES = [
        ('ДБ', 'ДБ'),
        ('ДЭ', 'ДЭ'),
    ]

    STATUS_CHOICES = [
        ('Зарегистрирован', 'Зарегистрирован'),
        ('В разработке', 'В разработке'),
        ('На проверке', 'На проверке'),
        ('На утверждении', 'На утверждении'),
        ('Выпущен', 'Выпущен'),
        ('Заменен', 'Заменен'),
        ('Аннулирован', 'Аннулирован'),
        ('В архиве', 'В архиве')
    ]

    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]

    category = models.CharField(max_length=50, default='ВПТ', verbose_name="Категория")
    name = models.CharField(max_length=150, unique=True, verbose_name="Наименование")
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='list_technical_proposals')
    desig_document_list_technical_proposal = models.CharField(max_length=50, unique=True, verbose_name="Обозначение документа", default='1')
    info_format = models.CharField(max_length=20, choices=INFO_FORMAT_CHOICES, default='ДЭ', verbose_name="Формат представления информации")
    change_number = models.CharField(max_length=20, default='без изм', verbose_name="Номер изменения")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name="Текущий ответственный")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Зарегистрирован', verbose_name="Статус (состояние)")
    priority = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True, default='', verbose_name="Приоритет в работе")
    version = models.CharField(max_length=6, default='1', verbose_name="Версия")
    version_diff = models.TextField(blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=2, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, default='1-', verbose_name="Уровень готовности технологий (TRL)")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Срок действия")
    subscribers = models.CharField(max_length=200, blank=True, default='', verbose_name="Внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, default='', verbose_name='Связанные сопроводительные документы')
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, default='ООО "СИСТЕМА"', verbose_name="Организация-разработчик")
    language = models.CharField(max_length=10, default='rus', verbose_name="Язык")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    SEP = " — "

    def build_name(self) -> str:
        parent_part = (self.post.name if self.post_id else "").strip()
        category_part = (self.category or "").strip()
        parts = [p for p in (parent_part, category_part) if p]
        return self.SEP.join(parts)

    def save(self, *args, **kwargs):
        # всегда пересобираем name из post.name и category
        self.name = self.build_name()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Ведомость технического предложения'
        verbose_name_plural = 'Ведомости технического предложения'


class TechnicalProposalDocument(models.Model):
    """Техническое предложение (ПТ) — одна запись = один документ в рамках разработки."""

    DOCUMENT_KIND_CHOICES = [
        ("scheme", "Схема"),
        ("drawing_part", "Чертеж детали"),
        ("drawing_assembly", "Чертеж сборочной единицы"),
        ("model_part", "Электронная модель детали"),
        ("model_assembly", "Электронная модель сборочной единицы"),
        ("software", "Программное обеспечение"),
        ("protocol", "Протокол"),
        ("report", "Пояснительная записка"),
        ("addition", "Приложение"),
    ]

    STATUS_CHOICES = [
        ("В разработке", "В разработке"),
        ("Выпущен", "Выпущен"),
    ]

    LITERA_CHOICES = [
        ("П-", "П-"),
        ("П", "П"),
    ]

    TRL_CHOICES = [
        ("1-", "1-"),
        ("1", "1"),
        ("2-", "2-"),
        ("2", "2"),
        ("3-", "3-"),
        ("3", "3"),
    ]

    INFO_FORMAT_CHOICES = [
        ("ДЭ", "ДЭ"),
        ("ДБ", "ДБ"),
    ]

    post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="technical_proposal_entries",
        null=True,
        blank=True,
        verbose_name="Разработка (модификация)",
    )
    document_kind = models.CharField(
        max_length=32,
        choices=DOCUMENT_KIND_CHOICES,
        blank=True,
        default="",
        verbose_name="Вид документа ПТ",
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Категория (код вида документа)",
    )

    name = models.CharField(max_length=200, verbose_name="Наименование")
    desig_document = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Обозначение документа",
    )

    litera = models.CharField(
        max_length=20,
        choices=LITERA_CHOICES,
        default="П-",
        verbose_name="Стадия разработки (литера)",
    )
    trl = models.CharField(
        max_length=10,
        choices=TRL_CHOICES,
        default="1-",
        verbose_name="Уровень готовности технологий (TRL)",
    )

    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technical_proposal_created",
        verbose_name="Автор",
    )
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technical_proposal_edited",
        verbose_name="Последний редактор",
    )
    version = models.CharField(max_length=20, blank=True, default="1", verbose_name="Версия")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technical_proposal_responsible",
        verbose_name="Текущий ответственный",
    )

    info_format = models.CharField(
        max_length=2,
        choices=INFO_FORMAT_CHOICES,
        default="ДЭ",
        verbose_name="Вид носителя информации",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="В разработке",
        verbose_name="Статус (состояние)",
    )
    related_documents = models.TextField(
        max_length=1000,
        blank=True,
        default="",
        verbose_name="Связанные сопроводительные документы",
    )
    develop_org = models.ForeignKey(
        "RKDDeveloper",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Организация-разработчик",
    )

    document_uploaded_file = models.FileField(
        upload_to="blog/technical_proposal/documents/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Документ: итоговый",
    )
    document_source = models.FileField(
        upload_to="blog/technical_proposal/documents/source/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Документ: исходник",
    )
    approval_document = models.FileField(
        upload_to="blog/technical_proposal/approval/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
        verbose_name="Лист утверждения: итоговый (PDF)",
        help_text="Допустимый формат: PDF.",
    )
    approval_source = models.FileField(
        upload_to="blog/technical_proposal/approval/source/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["docx"])],
        verbose_name="Лист утверждения: исходник (DOCX)",
        help_text="Допустимый формат: DOCX.",
    )
    attestation_document = models.FileField(
        upload_to="blog/technical_proposal/attestation/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
        verbose_name="Удостоверяющий лист: итоговый (PDF)",
        help_text="Допустимый формат: PDF.",
    )
    attestation_source = models.FileField(
        upload_to="blog/technical_proposal/attestation/source/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["docx"])],
        verbose_name="Удостоверяющий лист: исходник (DOCX)",
        help_text="Допустимый формат: DOCX.",
    )

    checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technical_proposal_checked",
        verbose_name="Проверил / согласовал",
    )
    signature_checked = models.FileField(
        upload_to="blog/technical_proposal/signatures/checked/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Подпись проверки (файл)",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technical_proposal_approved",
        verbose_name="Утвердил",
    )
    signature_approved = models.FileField(
        upload_to="blog/technical_proposal/signatures/approved/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Подпись утверждения (файл)",
    )

    comment = models.TextField(max_length=1000, blank=True, default="", verbose_name="Комментарий")

    class Meta:
        verbose_name = "техническое предложение"
        verbose_name_plural = "Технические предложения"
        ordering = ("post_id", "document_kind", "pk")

    def __str__(self):
        return f"{self.desig_document} — {self.name}" if self.desig_document else (self.name or "ПТ")

    def clean(self):
        super().clean()
        if not (self.name or "").strip():
            raise ValidationError({"name": "Укажите наименование."})
        if not (self.desig_document or "").strip():
            raise ValidationError({"desig_document": "Укажите обозначение документа."})
        if not (self.document_kind or "").strip():
            raise ValidationError({"document_kind": "Укажите вид документа ПТ."})
        if (
            self.status
            and self.status != "В разработке"
            and not self.document_uploaded_file
            and not self.document_source
        ):
            raise ValidationError(
                {
                    "document_uploaded_file": (
                        "Загрузите документ (итоговый PDF или исходник DOCX) "
                        "для статуса «Выпущен»."
                    )
                }
            )
        if self.status == "Выпущен":
            if not self.checked_by:
                raise ValidationError({"checked_by": "Для статуса «Выпущен» укажите проверившего."})
            if not self.signature_checked:
                raise ValidationError({"signature_checked": "Для статуса «Выпущен» приложите подпись проверки."})


class TaskForDesignWork(models.Model):

    INFO_FORMAT_CHOICES = [
        ('ДБ', 'ДБ'),
        ('ДЭ', 'ДЭ'),
    ]

    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]

    name = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name="наименование")
    category = models.CharField(max_length=100, default="ТЗ ОКР", verbose_name="категория")
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='task_for_design_work', verbose_name="Связанная разработка/проект")
    info_format = models.CharField(max_length=100, choices=INFO_FORMAT_CHOICES, blank=True, null=True,
                                   verbose_name="формат предоставления информации")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_designtasks", verbose_name="автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="edited_designtasks",
                                    verbose_name="последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.CASCADE, related_name="responsible_designtasks",
                                            verbose_name="текущий ответственный")
    status = models.CharField(max_length=50, default="Зарегистрирован", verbose_name="статус")
    priority = models.CharField(max_length=50, blank=True, null=True, choices=PRIORITY_CHOICES, verbose_name="приоритет в работе")
    version = models.CharField(max_length=3, blank=True, null=True, verbose_name="версия")
    version_diff = models.TextField(max_length=1000, blank=True, null=True, verbose_name="разница версий")
    validity_date = models.DateField(blank=True, null=True, verbose_name="срок действия")
    subscribers = models.TextField(blank=True, null=True, verbose_name="внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, null=True, verbose_name="связанные сопроводительные документы")
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, blank=True, null=True, verbose_name="организация - разработчик")
    language = models.CharField(max_length=7, blank=True, null=True, verbose_name="язык")
    uploaded_file = models.FileField(upload_to='design_tasks/', blank=True, null=True, verbose_name="загружаемый файл")
    add_task_for_design_work = models.FileField(upload_to='design_tasks/add/', blank=True, null=True,
                                                verbose_name="приложение к ТЗ")
    plan_for_design_work = models.FileField(upload_to='design_tasks/plan/', blank=True, null=True,
                                            verbose_name="план работ по ТЗ")
    route = models.CharField(max_length=255, blank=True, null=True, verbose_name="Маршрут")

    class Meta:
        verbose_name = 'Техническое задание на ОКР'
        verbose_name_plural = 'Технические задания на ОКР'

    def save(self, *args, **kwargs):
        if self.post and not self.name:
            self.name = self.post.name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class RevisionTask(models.Model):

    INFO_FORMAT_CHOICES = [
        ('ДБ', 'ДБ'),
        ('ДЭ', 'ДЭ'),
    ]

    PRIORITY_CHOICES = [
        ('Срочно', 'Срочно'),
        ('Высокий', 'Высокий'),
        ('Средний', 'Средний'),
        ('Низкий', 'Низкий'),
    ]

    name = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name="наименование")
    category = models.CharField(max_length=100, default="ТЗ Д", verbose_name="категория")
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='revision_tasks', verbose_name="Связанная разработка/проект")
    info_format = models.CharField(max_length=100, choices=INFO_FORMAT_CHOICES, blank=True, null=True, verbose_name="формат")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_revisions", verbose_name="автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="edited_revisions",
                                    verbose_name="последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, on_delete=models.CASCADE, related_name="responsible_revisions",
                                            verbose_name="текущий ответственный")
    status = models.CharField(max_length=50, default="Зарегистрирован", verbose_name="статус")
    priority = models.CharField(max_length=50, blank=True, null=True, choices=PRIORITY_CHOICES, verbose_name="приоритет в работе")
    version = models.CharField(max_length=3, blank=True, null=True, default='1', verbose_name="версия")
    version_diff = models.TextField(max_length=1000, blank=True, null=True, default='стартовая версия', verbose_name="сравнение версий")
    validity_date = models.DateField(blank=True, null=True, verbose_name="срок действия")
    subscribers = models.TextField(blank=True, null=True, verbose_name="внешние и внутренние получатели")
    related_documents = models.TextField(blank=True, null=True, verbose_name="связанный сопроводительные документы")
    pattern = models.FileField(upload_to='uploads/', blank = True, null=True, verbose_name="Шаблон")
    develop_org = models.CharField(max_length=100, blank=True, null=True, verbose_name="организация - разработчик")
    language = models.CharField(max_length=7, blank=True, null=True, verbose_name="язык")
    uploaded_file = models.FileField(upload_to='revision_tasks/', blank=True, null=True, verbose_name="файл")
    add_task_for_revision = models.FileField(upload_to='revision_tasks/add/', blank=True, null=True,
                                             verbose_name="приложение к ТЗ")
    plan_for_revision = models.FileField(upload_to='revision_tasks/plan/', blank=True, null=True,
                                         verbose_name="план работ по ТЗ")
    route = models.CharField(max_length=255, blank=True, null=True, verbose_name="Маршрут")

    class Meta:
        verbose_name = 'Техническое задание на доработку'
        verbose_name_plural = 'Технические задания на доработку'

    def save(self, *args, **kwargs):
        if self.post and not self.name:
            self.name = f"{self.post.name} - Ревизия"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class WorkAssignment(models.Model):
    RESULT_CHOICES = [
        ('Выполнено в срок', 'Выполнено в срок'),
        ('Выполнено с переносом сроков', 'Выполнено с переносом сроков'),
        ('Выполнено частично', 'Выполнено частично'),
        ('Не выполнено', 'Не выполнено'),
    ]

    TEMP_STATUS_CHOICES = [
        ('assigned', 'Ожидает принятия'),
        ('in_progress', 'В работе'),
        ('reschedule_pending', 'Согласование переноса срока'),
        ('review', 'На проверке'),
        ('on_time', 'Выполнено в срок'),
        ('rescheduled', 'Выполнено с переносом сроков'),
        ('partial', 'Выполнено частично'),
        ('not_done', 'Не выполнено (Отменено)'),
    ]

    STATUS_ASSIGNED = 'assigned'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_REVIEW = 'review'
    STATUS_RESCHEDULE_PENDING = 'reschedule_pending'

    ACTIVE_STATUSES = ('assigned', 'in_progress', 'review', 'reschedule_pending')
    TERMINAL_STATUSES = ('on_time', 'rescheduled', 'partial', 'not_done')

    name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Наименование")
    wa_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Порядковый номер в рамках разработки",
    )
    category = models.CharField(max_length=100, default="РЗ", verbose_name="Категория")
    is_urgent = models.BooleanField(default=False, verbose_name="Срочно?")
    executor = models.ForeignKey(User, on_delete=models.CASCADE, null= True, related_name= "executed_workassignments", verbose_name="Исполнитель")
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='work_assignments', verbose_name="Связанная разработка/проект")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="edited_workassignments",
        verbose_name="Последний редактор"
    )
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    version = models.CharField(max_length=3, blank=True, null=True, verbose_name="Версия")
    task = models.TextField(
        verbose_name="Задача",
        help_text="Декомпозиция задачи: в разделе «ПОДЗАДАЧИ» (доступна через «Сохранить и продолжить редактировать»)",
    )
    acceptance_criteria = models.TextField(default='---', verbose_name="Критерий выполнения")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    deadline_version = models.PositiveIntegerField(default=0, verbose_name="Версия дедлайна")
    reschedule_count = models.PositiveIntegerField(default=0, verbose_name="Количество переносов")


    result = models.CharField(max_length=100, choices=RESULT_CHOICES, blank=True, null=True, verbose_name="Результат")
    result_description = models.TextField(max_length=5000, blank=True, null=True, verbose_name="Описание результата")
    comment = models.TextField(max_length=5000, blank=True, null=True, verbose_name="Комментарий автора")
    returned_for_rework = models.BooleanField(default=False, verbose_name="Возвращена на доработку")
    route = models.ForeignKey("Route", on_delete=models.CASCADE, related_name='routes', blank=True, null=True, verbose_name="Маршрут")

    target_deadline = models.DateField("Целевой срок выполнения", default=timezone.localdate, null=False, blank=False)
    hard_deadline = models.DateField("Дедлайн", null=True, blank=True)
    time_window_start = models.DateField("Временное окно: с", null=True, blank=True)
    time_window_end = models.DateField("Временное окно: по", null=True, blank=True)
    conditional_deadline = models.CharField("Условия/ограничения", max_length=1000, blank=True)

    reschedule_request_reason = models.TextField("Причина запроса переноса срока", blank=True, default="")
    reschedule_request_date = models.DateField("Желаемая дата выполнения", null=True, blank=True)

    version_diff = models.TextField(
        "Сравнение версий",
        blank=True,
        default="Стартовая версия",
    )
    control_status = models.CharField(
        "Статус выполнения / Результат",
        max_length=20,
        null=True,
        blank=True,
        choices=TEMP_STATUS_CHOICES,
    )
    control_date = models.DateTimeField("Дата фиксации статуса", null=True, blank=True)

    def clean(self):
        super().clean()

        dates, date_errors = _normalize_model_dates(
            self,
            ("target_deadline", "hard_deadline", "time_window_start", "time_window_end"),
        )
        if date_errors:
            raise ValidationError(date_errors)

        target = dates["target_deadline"]
        hard = dates["hard_deadline"]
        tw_start = dates["time_window_start"]
        tw_end = dates["time_window_end"]

        if tw_start and tw_end and tw_end < tw_start:
            raise ValidationError({
                "time_window_end": "Дата «по» не может быть раньше даты «с».",
            })

        if target and tw_end and tw_end > target:
            raise ValidationError({
                "time_window_end": "Конец временного окна не может быть позже целевого срока.",
            })

        if target and tw_start and tw_end and not (tw_start <= target <= tw_end):
            raise ValidationError({
                "target_deadline": "Целевой срок должен попадать в заданное временное окно.",
            })

        if hard and target and hard < target:
            raise ValidationError({
                "hard_deadline": "Абсолютный дедлайн не может быть раньше целевого срока.",
            })

    @property
    def effective_deadline(self):
        if self.hard_deadline and self.target_deadline:
            return min(self.target_deadline, self.hard_deadline)
        if self.target_deadline:
            return self.target_deadline
        if self.time_window_end:
            return self.time_window_end
        return None

    def is_active(self):
        return self.control_status not in self.TERMINAL_STATUSES

    def is_target_overdue(self, today=None):
        if not self.is_active():
            return False
        if not self.target_deadline:
            return False
        today = today or timezone.localdate()
        return today > self.target_deadline

    def is_hard_overdue(self, today=None):
        if not self.is_active():
            return False
        if not self.hard_deadline:
            return False
        today = today or timezone.localdate()
        return today > self.hard_deadline

    def is_overdue(self, today=None):
        if not self.is_active():
            return False
        if self.is_target_overdue(today):
            return True
        return self.is_hard_overdue(today)

    def mark_result_on_close(self):
        if self.result:
            return
        was_rescheduled = bool(self.reschedule_count)
        if not self.is_overdue() and not was_rescheduled:
            self.result = 'Выполнено в срок'
        elif not self.is_overdue() and was_rescheduled:
            self.result = 'Выполнено с переносом сроков'
        else:
            self.result = 'Не выполнено'

    def save(self, *args, **kwargs):
        if self.post and not self.name:
            self.name = self.post.name
        super().save(*args, **kwargs)

    @property
    def wa_full_code(self) -> str:
        code = getattr(self.post, "wa_code", None) if self.post_id else None
        if code and self.wa_number:
            return f"{code}-{self.wa_number}"
        return ""

    def __str__(self):
        return self.name or "Без названия"

    class Meta:
        verbose_name = 'Рабочее задание'
        verbose_name_plural = 'Рабочие задания'


class WorkAssignmentSubtask(models.Model):
    work_assignment = models.ForeignKey(
        "WorkAssignment",
        on_delete=models.CASCADE,
        related_name="subtasks",
        verbose_name="Рабочее задание",
    )
    subtask_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Порядковый номер в рамках РЗ",
    )
    category = models.CharField(max_length=100, default="Подзадача", verbose_name="Категория")
    executor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        related_name="subtask_executed_assignments",
        verbose_name="Исполнитель",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subtask_authored_assignments",
        verbose_name="Автор",
    )
    date_of_creation = models.DateTimeField(
        default=timezone.now, verbose_name="Дата и время создания"
    )
    last_editor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subtask_edited_assignments",
        verbose_name="Последний редактор",
    )
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subtask_responsible_assignments",
        verbose_name="Текущий ответственный",
    )
    version = models.CharField(max_length=3, blank=True, null=True, verbose_name="Версия")
    task = models.TextField(verbose_name="Задача")
    acceptance_criteria = models.TextField(default="---", verbose_name="Критерий выполнения")
    uploaded_file = models.FileField(
        upload_to="work_assignment_subtasks/", blank=True, verbose_name="Загружаемый файл"
    )
    deadline_version = models.PositiveIntegerField(default=0, verbose_name="Версия дедлайна")
    reschedule_count = models.PositiveIntegerField(default=0, verbose_name="Количество переносов")
    result = models.CharField(
        max_length=100,
        choices=WorkAssignment.RESULT_CHOICES,
        blank=True,
        null=True,
        verbose_name="Результат",
    )
    result_description = models.TextField(
        max_length=5000, blank=True, null=True, verbose_name="Описание результата"
    )
    target_deadline = models.DateField("Целевой срок выполнения", default=timezone.localdate)
    hard_deadline = models.DateField("Абсолютный дедлайн", null=True, blank=True)
    time_window_start = models.DateField("Временное окно: с", null=True, blank=True)
    time_window_end = models.DateField("Временное окно: по", null=True, blank=True)
    conditional_deadline = models.CharField("Условный дедлайн", max_length=1000, blank=True)
    control_status = models.CharField(
        "Статус выполнения / Результат",
        max_length=20,
        null=True,
        blank=True,
        choices=WorkAssignment.TEMP_STATUS_CHOICES,
    )
    control_date = models.DateField("Дата фиксации статуса", null=True, blank=True)
    comment = models.TextField(
        "Комментарий",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Подзадача рабочего задания"
        verbose_name_plural = "Подзадачи рабочих заданий"
        ordering = ("work_assignment_id", "subtask_number", "pk")

    @property
    def subtask_full_code(self) -> str:
        wa = self.work_assignment if self.work_assignment_id else None
        parent_code = getattr(wa, "wa_full_code", "") if wa else ""
        if parent_code and self.subtask_number:
            return f"{parent_code}.{self.subtask_number}"
        return ""

    def clean(self):
        super().clean()
        wa = self.work_assignment if self.work_assignment_id else None
        if wa is None:
            return

        snapshot = None
        if self.pk:
            try:
                snapshot = type(self).objects.values(
                    "target_deadline", "hard_deadline"
                ).get(pk=self.pk)
            except type(self).DoesNotExist:
                snapshot = None

        if self.target_deadline and wa.target_deadline:
            changed = snapshot is None or snapshot["target_deadline"] != self.target_deadline
            if changed and self.target_deadline > wa.target_deadline:
                wa_label = wa.wa_full_code or str(wa)
                raise ValidationError({
                    "target_deadline": (
                        f"Целевой срок подзадачи ({self.target_deadline:%d.%m.%Y}) не может быть позже "
                        f"целевого срока рабочего задания {wa_label} ({wa.target_deadline:%d.%m.%Y})."
                    )
                })

        if self.hard_deadline and wa.hard_deadline:
            changed = snapshot is None or snapshot["hard_deadline"] != self.hard_deadline
            if changed and self.hard_deadline > wa.hard_deadline:
                wa_label = wa.wa_full_code or str(wa)
                raise ValidationError({
                    "hard_deadline": (
                        f"Абсолютный дедлайн подзадачи ({self.hard_deadline:%d.%m.%Y}) не может быть позже "
                        f"абсолютного дедлайна рабочего задания {wa_label} ({wa.hard_deadline:%d.%m.%Y})."
                    )
                })

    def __str__(self):
        code = self.subtask_full_code
        head = (self.task or "").strip().replace("\n", " ")[:60]
        if code:
            return f"{code}: {head}" if head else code
        return head or f"Подзадача #{self.pk or 'новая'}"


class WorkAssignmentDeadlineChange(models.Model):
    assignment = models.ForeignKey(
        WorkAssignment,
        on_delete=models.CASCADE,
        related_name="deadline_changes",
        verbose_name="Рабочее задание",
    )

    # что было
    old_target_deadline = models.DateField(null=True, blank=True, verbose_name="старый целевой срок")
    old_hard_deadline   = models.DateField(null=True, blank=True, verbose_name="старый дедлайн")
    old_time_window_start = models.DateField(null=True, blank=True, verbose_name="старое временное окно с")
    old_time_window_end   = models.DateField(null=True, blank=True, verbose_name="старое временное окно по")

    # что стало
    new_target_deadline = models.DateField(null=True, blank=True, verbose_name="новый целевой срок")
    new_hard_deadline   = models.DateField(null=True, blank=True, verbose_name="новый дедлайн")
    new_time_window_start = models.DateField(null=True, blank=True, verbose_name="новое временное окно с")
    new_time_window_end   = models.DateField(null=True, blank=True, verbose_name="новое временное окно по")

    reason = models.CharField(max_length=255, verbose_name="причина")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        verbose_name="автор",
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name="дата и время изменения")

    # локальный порядковый номер переноса внутри assignment
    index = models.PositiveIntegerField(editable=False, null= True, verbose_name="№ переноса по заданию")

    class Meta:
        verbose_name = "Изменение дедлайна для рабочего задания"
        verbose_name_plural = "Изменения дедлайна для рабочих заданий"
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["assignment", "-changed_at"]),
            models.Index(fields=["assignment", "index"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "index"],
                name="uniq_deadline_change_index_per_assignment",
            )
        ]

    def save(self, *args, **kwargs):
        # присваиваем следующий локальный номер при первом сохранении
        if self.pk is None and not self.index:
            with transaction.atomic():
                last = (
                    WorkAssignmentDeadlineChange.objects
                    .filter(assignment=self.assignment)
                    .select_for_update()
                    .order_by("-index")
                    .first()
                )
                self.index = (0 if last is None or last.index is None else int(last.index)) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Перенос #{self.index}"

class Process(models.Model):
    class Kind(models.TextChoices):
        IT_REQ   = "it_requirements",   "Проверка IT требований"
        TECH_REQ = "tech_requirements", "Проверка технических требований"
        NORM     = "norm_control",      "Нормоконтроль"

    kind = models.CharField(
        max_length=32,
        choices=Kind.choices,
        unique=True,
        default=Kind.IT_REQ,
    )
    code = models.SlugField(max_length=64, unique=True, editable=False)
    name = models.CharField(max_length=255, unique=True, editable=False)

    def save(self, *args, **kwargs):
        # синхронизируем служебные поля с выбором kind
        self.code = self.kind
        self.name = self.get_kind_display()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Процесс"
        verbose_name_plural = "Процессы"

    def __str__(self):
        return self.name


class CheckDocumentWorkflow(models.Model):
    """
    Алгоритм проверки для конкретного документа.
    """

    YES_NO_CHOICES = (
        ("YES", "ДА"),
        ("NO", "НЕТ"),
    )

    RESOLUTION_CHOICES = (
        ("APPROVED", "СОГЛАСОВАНО"),
        ("REJECTED", "НЕ СОГЛАСОВАНО"),
    )

    # 1–7 аудит/версионирование
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_check_workflows")
    date_of_creation = models.DateTimeField(default=timezone.now, db_index=True)
    last_editor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="edited_check_workflows")
    date_of_change = models.DateTimeField(default=timezone.now)
    current_responsible = models.ForeignKey(User, on_delete=models.PROTECT, related_name="responsible_check_workflows")
    version = models.PositiveSmallIntegerField(null=True, blank=True)

    # 8 Тип/категория проверяемого документа
    types_check_document = models.CharField(
        max_length=100,
        blank=True,
        help_text="Напр.: ЭД, ПД, 3D-модель и т.д."
    )
    # 9 Обозначение/наименование документа
    desig_document_check_doc = models.CharField(max_length=100)
    name = models.CharField(max_length=100, null=True, blank=True)
    # 10 Загружаемый файл
    uploaded_file = models.FileField(upload_to="check_docs/", help_text="PDF с ЭЦП разработчика")

    # --- Блок «Проверка технических требований» ---
    check_technical_requirements = models.CharField(max_length=3, choices=YES_NO_CHOICES, blank=True)
    check_technical_requirements_responsible = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="check_technical_requirements_responsibles")
    check_technical_requirements_resolution = models.CharField(max_length=10, choices=RESOLUTION_CHOICES, blank=True)
    check_technical_requirements_comment = models.TextField(max_length=5000, blank=True)
    check_technical_requirements_date_of_resolution = models.DateTimeField(null=True, blank=True)
    check_technical_requirements_signature = models.BooleanField(default=False)
    check_technical_requirements_date_of_signature = models.DateTimeField(null=True, blank=True)

    # --- Блок «Проверка IT требований» ---
    check_it_requirements = models.CharField(max_length=3, choices=YES_NO_CHOICES, blank=True)
    check_it_requirements_responsible = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="check_it_requirements_responsibles")
    check_it_requirements_resolution = models.CharField(max_length=10, choices=RESOLUTION_CHOICES, blank=True)
    check_it_requirements_comment = models.TextField(max_length=5000, blank=True)
    check_it_requirements_date_of_resolution = models.DateTimeField(null=True, blank=True)
    check_it_requirements_signature = models.BooleanField(default=False)
    check_it_requirements_date_of_signature = models.DateTimeField(null=True, blank=True)

    # --- Блок «Проверка 3D-моделей» ---
    check_3D_model = models.CharField(max_length=3, choices=YES_NO_CHOICES, blank=True)
    check_3D_model_responsible = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="check_3D_model_responsibles")
    check_3D_model_resolution = models.CharField(max_length=10, choices=RESOLUTION_CHOICES, blank=True)
    check_3D_model_comment = models.TextField(max_length=5000, blank=True)
    check_3D_model_date_of_resolution = models.DateTimeField(null=True, blank=True)
    check_3D_model_signature = models.BooleanField(default=False)
    check_3D_model_date_of_signature = models.DateTimeField(null=True, blank=True)

    # --- Блок «Нормоконтроль» ---
    norm_control = models.CharField(max_length=3, choices=YES_NO_CHOICES, blank=True)
    norm_control_responsible = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="norm_control_responsibles")
    norm_control_resolution = models.CharField(max_length=10, choices=RESOLUTION_CHOICES, blank=True)
    norm_control_comment = models.TextField(max_length=5000, blank=True)
    norm_control_date_of_resolution = models.DateTimeField(null=True, blank=True)
    norm_control_signature = models.BooleanField(default=False)
    norm_control_date_of_signature = models.DateTimeField(null=True, blank=True)

    class ProcessSequence(models.IntegerChoices):
        IT_TECH_NORM = 1, "Проверка IT требований → Тех. требования → Нормоконтроль"
        _3D_TECH_NORM = 2, "Проверка 3D-моделей → Тех. требования → Нормоконтроль"
        TECH_NORM = 3, "Тех. требования → Нормоконтроль"
        _3D_NORM = 4, "Проверка 3D-моделей → Нормоконтроль"
        NORM_ONLY = 5, "Нормоконтроль"

    process_sequence = models.IntegerField(choices=ProcessSequence.choices)

    class Meta:
        verbose_name = "Проверка документа (workflow)"
        verbose_name_plural = "Проверки документа (workflow)"
        ordering = ("-date_of_creation",)

    def __str__(self):
        return f"Проверка: {self.desig_document_check_doc} (v{self.version or '-'})"

    def save(self, *args, **kwargs):
        self.date_of_change = timezone.now()
        super().save(*args, **kwargs)


class ApprovalDocumentWorkflow(models.Model):
    """Минимальная заглушка"""
    name = models.CharField(max_length=255)
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_approval_workflows")
    date_of_creation = models.DateTimeField(default=timezone.now)
    last_editor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="edited_approval_workflows")
    date_of_change = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        self.date_of_change = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Утверждение документа (workflow)"
        verbose_name_plural = "Утверждения документа (workflow)"

    def __str__(self):
        return self.name


class Route(models.Model):
    """Маршруты — набор алгоритмов / паттернов"""
    name = models.CharField(max_length=255, unique=True)
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_routes")
    date_of_creation = models.DateTimeField(default=timezone.now, db_index=True)
    last_editor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="edited_routes")
    date_of_change = models.DateTimeField(default=timezone.now)
    current_responsible = models.ForeignKey(User, on_delete=models.PROTECT, related_name="responsible_routes")
    version = models.PositiveSmallIntegerField(null=True, blank=True)
    version_diff = models.CharField(max_length=1000, blank=True)

    check_document = models.ForeignKey('CheckDocumentWorkflow', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='routes')
    approval_document = models.ForeignKey('ApprovalDocumentWorkflow', on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='routes')
    processes = models.ManyToManyField('Process', through='RouteProcess', blank=True)

    class AccessLevel(models.TextChoices):
        PUBLIC = "O", "общий (О)"
        CONFIDENTIAL = "K", "конфиденциально (К)"
        SECRET = "C", "секретно (С)"
        TOP_SECRET = "CC", "совершенно секретно (СС)"

    permissions_mask = models.PositiveSmallIntegerField(
        default=7,
        help_text="0..7 по таблице прав (визуализация). Значение по умолчанию: 7"
    )
    access_level = models.CharField(max_length=2, choices=AccessLevel.choices, default=AccessLevel.PUBLIC)

    class Meta:
        verbose_name = "Маршрут"
        verbose_name_plural = "Маршруты"
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.date_of_change = timezone.now()
        super().save(*args, **kwargs)


class RouteProcess(models.Model):
    """Сквозная таблица, чтобы упорядочить процессы в маршруте"""
    route = models.ForeignKey('Route', on_delete=models.CASCADE)
    process = models.ForeignKey('Process', on_delete=models.PROTECT)
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = (('route', 'process'), ('route', 'order'))
        ordering = ('route', 'order')

    def __str__(self):
        return f"{self.route} → {self.process} ({self.order})"

class Attachment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True)
    object_id    = models.PositiveIntegerField(blank=True, null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    file = models.FileField(upload_to="attachments/")
    kind = models.CharField(max_length=20, blank=True, default="")

    def __str__(self):
        return self.file.name.rsplit("/", 1)[-1] if self.file else f"Вложение {self.pk}"


class RKDDeveloper(models.Model):
    """Общий справочник для РКД (как «Организация-разработчик»)
    и для отгрузок (как «Изготовитель/Поставщик»)."""

    name = models.CharField(max_length=200, unique=True, verbose_name="Название")
    inn = models.CharField(
        max_length=12,
        blank=True,
        default="",
        verbose_name="ИНН",
        help_text="Только цифры, не более 12 символов.",
        validators=[
            RegexValidator(
                regex=r"^\d{0,12}$",
                message="ИНН должен содержать только цифры (не более 12).",
            ),
        ],
    )
    charter = models.FileField(
        upload_to="rkd_developer/charter/",
        blank=True,
        null=True,
        verbose_name="Устав",
    )
    requisites = models.FileField(
        upload_to="rkd_developer/requisites/",
        blank=True,
        null=True,
        verbose_name="Реквизиты",
    )

    class Meta:
        verbose_name = "Организация-разработчик/изготовитель"
        verbose_name_plural = "Организации-разработчики/изготовители"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.inn:
            self.inn = self.inn.strip()
            if not self.inn.isdigit():
                raise ValidationError({"inn": "ИНН должен содержать только цифры."})
            if len(self.inn) > 12:
                raise ValidationError({"inn": "ИНН не должен превышать 12 цифр."})


class RKDDeveloperAdditionalFile(models.Model):
    """Несколько дополнительных файлов на одну организацию-разработчик/изготовитель."""

    developer = models.ForeignKey(
        RKDDeveloper,
        on_delete=models.CASCADE,
        related_name="additional_files",
        verbose_name="Организация",
    )
    file = models.FileField(
        upload_to="rkd_developer/additional/",
        verbose_name="Файл",
    )

    class Meta:
        verbose_name = "Дополнительный файл организации"
        verbose_name_plural = "Дополнительные файлы организации"

    def __str__(self):
        return self.file.name if self.file else str(self.pk)


class UniversalRKD(models.Model):
    POSITION_DASH = "-"
    STATUS_CHOICES = [
        ("Зарегистрирован", "Зарегистрирован"),
        ("В разработке", "В разработке"),
        ("На проверке", "На проверке"),
        ("На утверждении", "На утверждении"),
        ("Выпущен", "Выпущен"),
        ("Заменен", "Заменен"),
        ("Аннулирован", "Аннулирован"),
        ("В архиве", "В архиве"),
    ]

    INFO_FORMAT_CHOICES = [
        ("ДЭ", "ДЭ"),
        ("ДБ", "ДБ"),
    ]

    SHEET_SIZE_CHOICES = [
        ("А0", "А0"),
        ("А1", "А1"),
        ("А5", "А5"),
        ("А4", "А4"),
        ("БЧ", "БЧ"),
        ("А3", "А3"),
        ("А2", "А2"),
        ("2D", "2D"),
        ("3D", "3D"),
    ]

    LITERA_CHOICES = [
        ("o_minus", "О-"),
        ("o", "О"),
        ("o1", "О₁"),
        ("o2", "О₂"),
        ("o3", "О₃"),
        ("a", "А"),
        ("i", "И"),
        ("b", "Б"),
    ]

    TRL_CHOICES = [
        ("7-", "7-"),
        ("7", "7"),
        ("8-", "8-"),
        ("8", "8"),
        ("9-", "9-"),
        ("9", "9"),
    ]

    LANGUAGE_CHOICES = [
        ("rus", "rus"),
        ("eng", "eng"),
        ("tur", "tur"),
        ("chi", "chi"),
    ]

    post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="universal_rkd_entries",
        null=True,
        blank=True,
        verbose_name="Разработка (модификация)",
    )
    specification_section = models.CharField(
        max_length=32,
        choices=SPECIFICATION_SECTION_CHOICES,
        verbose_name="Раздел спецификации",
    )
    section_sort_index = models.PositiveSmallIntegerField(
        editable=False,
        default=0,
        verbose_name="Порядок раздела (служебное)",
    )
    category = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name="Категория (код вида документа)",
    )
    order_in_section = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок в разделе",
        help_text="Для ручной сортировки позиций внутри одного раздела и одной разработки.",
    )

    name = models.CharField(max_length=100, verbose_name="Наименование")
    desig_document = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name="Обозначение документа",
    )
    primary_use = models.CharField(max_length=100, blank=True, default="", verbose_name="Первичное применение")

    change_number = models.CharField(max_length=8, verbose_name="Номер изменения")
    litera = models.CharField(
        max_length=16,
        choices=LITERA_CHOICES,
        default="o",
        verbose_name="Стадия разработки (литера)",
    )
    trl = models.CharField(
        max_length=3,
        choices=TRL_CHOICES,
        default="7",
        verbose_name="Уровень готовности технологий (TRL)",
    )

    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="universal_rkd_created",
        verbose_name="Автор",
    )
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="universal_rkd_edited",
        verbose_name="Последний редактор",
    )
    version = models.CharField(max_length=3, default="1", verbose_name="Версия")
    version_diff = models.TextField(
        blank=True,
        default="Стартовая версия",
        verbose_name="Сравнение версий",
    )
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="universal_rkd_responsible",
        verbose_name="Текущий ответственный",
    )

    sheet_size = models.CharField(
        max_length=5,
        choices=SHEET_SIZE_CHOICES,
        default="А4",
        verbose_name="Формат (листа)",
    )
    position = models.CharField(
        max_length=5,
        blank=True,
        default="",
        verbose_name="Позиция",
    )
    info_format = models.CharField(
        max_length=2,
        choices=INFO_FORMAT_CHOICES,
        default="ДЭ",
        verbose_name="Вид носителя информации",
    )
    validity_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата планового пересмотра",
    )
    revision_criteria = models.TextField(
        max_length=1000,
        blank=True,
        default="",
        verbose_name="Критерии пересмотра",
    )
    review_reminder_days = models.PositiveSmallIntegerField(
        default=60,
        verbose_name="Оповещение о пересмотре (дней):",
        help_text="Укажите, за сколько дней до даты планового пересмотра показывать предупреждение в журнале.",
    )
    language = models.CharField(
        max_length=3,
        choices=LANGUAGE_CHOICES,
        default="rus",
        verbose_name="Язык",
    )
    internal_recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="universal_rkd_internal_recipient",
        verbose_name="Внутренние получатели",
    )
    external_recipients = models.ManyToManyField(
        "crm.Customer",
        blank=True,
        related_name="universal_rkd_external_recipient",
        verbose_name="Внешние получатели",
    )
    related_documents = models.TextField(max_length=1000, blank=True, default="", verbose_name="Связанные сопроводительные документы")
    develop_org = models.ForeignKey(
        RKDDeveloper,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Организация-разработчик",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="Зарегистрирован",
        verbose_name="Статус (состояние)",
    )
    document_uploaded_file = models.FileField(
        upload_to="blog/universal_rkd/documents/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Документ: итоговый",
    )
    document_source = models.FileField(
        upload_to="blog/universal_rkd/documents/source/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Документ: исходник",
    )
    approval_document = models.FileField(
        upload_to="blog/universal_rkd/approval/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
        verbose_name="Лист утверждения: итоговый (PDF)",
        help_text="Допустимый формат: PDF.",
    )
    approval_source = models.FileField(
        upload_to="blog/universal_rkd/approval/source/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["docx"])],
        verbose_name="Лист утверждения: исходник (DOCX)",
        help_text="Допустимый формат: DOCX.",
    )
    attestation_document = models.FileField(
        upload_to="blog/universal_rkd/attestation/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
        verbose_name="Удостоверяющий лист: итоговый (PDF)",
        help_text="Допустимый формат: PDF.",
    )
    attestation_source = models.FileField(
        upload_to="blog/universal_rkd/attestation/source/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["docx"])],
        verbose_name="Удостоверяющий лист: исходник (DOCX)",
        help_text="Допустимый формат: DOCX.",
    )
    acquaintance_document = models.FileField(
        upload_to="blog/universal_rkd/acquaintance/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
        verbose_name="Лист ознакомления (PDF)",
        help_text="Формируется автоматически при подписании шагов «Ознакомление».",
    )

    checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="universal_rkd_checked",
        verbose_name="Проверил (схемотехнические требования)",
    )
    signature_checked = models.FileField(
        upload_to="blog/universal_rkd/signatures/checked/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Подпись (схемотехника)",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="universal_rkd_approved",
        verbose_name="Утвердил",
    )
    signature_approved = models.FileField(
        upload_to="blog/universal_rkd/signatures/approved/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Подпись утверждения (файл)",
    )

    quantity = models.CharField(max_length=10, blank=True, default="", verbose_name="Количество", help_text="на изделие / узел")
    note = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Примечание",
        help_text="Заполняет разработчик документа.",
    )
    weight = models.CharField(max_length=10, blank=True, default="", verbose_name="Масса")
    comment = models.TextField(max_length=1000, blank=True, default="", verbose_name="Комментарий")

    class Meta:
        verbose_name = "РКД разработки (модификации)"
        verbose_name_plural = "РКД разработки (модификации)"
        ordering = ("post_id", "section_sort_index", "order_in_section", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("post", "name"),
                name="blog_universalrkd_unique_name_per_post",
            ),
        ]

    def __str__(self):
        return f"{self.desig_document} — {self.name}"

    def clean(self):
        super().clean()
        if not (self.name or "").strip():
            raise ValidationError({"name": "Укажите наименование."})
        if not (self.desig_document or "").strip():
            raise ValidationError({"desig_document": "Укажите обозначение документа."})

        dg = (self.desig_document or "").strip()
        qs_des = UniversalRKD.objects.filter(desig_document=dg)
        if self.pk:
            qs_des = qs_des.exclude(pk=self.pk)
        if qs_des.exists():
            raise ValidationError(
                {
                    "desig_document": (
                        "РКД с таким обозначением документа уже существует. "
                        "Обозначение должно быть уникальным."
                    )
                }
            )

        if self.post_id:
            nm = (self.name or "").strip()
            qs_name = UniversalRKD.objects.filter(post_id=self.post_id, name=nm)
            if self.pk:
                qs_name = qs_name.exclude(pk=self.pk)
            if qs_name.exists():
                raise ValidationError(
                    {
                        "name": "В этой разработке уже есть позиция журнала с таким наименованием."
                    }
                )

        section = self.specification_section or ""
        allowed = allowed_categories_for_section(section)
        if not section_has_category_choices(section):
            self.category = ""
        else:
            if not (self.category or "").strip():
                raise ValidationError(
                    {"category": "Укажите категорию (код вида документа)."}
                )
            if self.category not in allowed:
                raise ValidationError(
                    {
                        "category": (
                            f"Код «{self.category}» недопустим для раздела "
                            f"«{self.get_specification_section_display()}»."
                        )
                    }
                )
        if not section_allows_quantity_weight(section):
            self.quantity = "-"
            self.weight = "-"
        if not section_allows_position(section):
            self.position = self.POSITION_DASH
        else:
            self.position = (self.position or "").strip()
            if not self.position:
                raise ValidationError({"position": "Укажите позицию."})
            if self.post_id:
                qs_pos = UniversalRKD.objects.filter(
                    post_id=self.post_id,
                    position=self.position,
                )
                if self.pk:
                    qs_pos = qs_pos.exclude(pk=self.pk)
                if qs_pos.exists():
                    raise ValidationError(
                        {
                            "position": (
                                "В этой разработке уже есть позиция журнала "
                                "с таким номером."
                            )
                        }
                    )
        if (
            self.status
            and self.status != "Зарегистрирован"
            and not self.document_uploaded_file
            and not self.document_source
        ):
            raise ValidationError(
                {
                    "document_uploaded_file": (
                        "Загрузите документ (итоговый PDF или исходник DOCX) "
                        "для статуса, отличного от «Зарегистрирован»."
                    )
                }
            )
        if self.status == "Выпущен":
            if not self.checked_by:
                raise ValidationError({"checked_by": "Для статуса «Выпущен» укажите проверившего."})
            if not self.signature_checked:
                raise ValidationError({"signature_checked": "Для статуса «Выпущен» приложите подпись проверки."})

        has_approval = bool(self.approval_document) or bool(self.approval_source)
        has_attestation = bool(self.attestation_document) or bool(self.attestation_source)
        if has_approval and has_attestation:
            mutual_error = (
                "К документу можно прикрепить только что-то одно: «Лист утверждения» или "
                "«Удостоверяющий лист». Удалите файлы из ненужного блока."
            )
            errors = {}
            if self.approval_document:
                errors["approval_document"] = mutual_error
            if self.approval_source:
                errors["approval_source"] = mutual_error
            if self.attestation_document:
                errors["attestation_document"] = mutual_error
            if self.attestation_source:
                errors["attestation_source"] = mutual_error
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.post_id:
            post = self.post
            if not (self.desig_document or "").strip() and post.desig_document_post:
                self.desig_document = (post.desig_document_post or "")[:50]
            if not (self.name or "").strip() and post.name:
                self.name = post.name[:100]
        self.section_sort_index = specification_section_sort_index(self.specification_section)
        if self.pk is None and self.order_in_section == 0:
            agg = UniversalRKD.objects.filter(
                post_id=self.post_id,
                specification_section=self.specification_section,
            ).aggregate(m=Max("order_in_section"))
            max_o = agg["m"] or 0
            self.order_in_section = max_o + 1
        super().save(*args, **kwargs)


class UniversalRKDSignature(models.Model):
    """Подписи к документу РКД (проверил / согласовал / утвердил)."""

    ROLE_CHOICES = [
        ("designer", "Разработал"),
        ("scheme", "Проверил (схемотехнические требования)"),
        ("it", "Проверил IT (требования, связанные с клиент-серверным ПО)"),
        ("3d", "Проверил 3D (требования, связанные с 3D-печатью)"),
        ("metro", "Проверил (метрологический контроль)"),
        ("tk", "Т. контроль (технологический контроль)"),
        ("lead", "Проверил (руководитель разработки)"),
        ("nk", "Н. контроль (нормоконтроль)"),
        ("agreed", "Согласовал"),
        ("approved", "Утвердил"),
    ]

    rkd = models.ForeignKey(
        UniversalRKD,
        on_delete=models.CASCADE,
        related_name="signatures",
        verbose_name="Документ РКД",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        verbose_name="Роль",
    )
    signed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rkd_signatures",
        verbose_name="Кто подписал",
    )
    signature_file = models.FileField(
        upload_to="blog/universal_rkd/signatures/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Файл подписи",
    )
    signed_at = models.DateField("Дата подписания", null=True, blank=True)
    cert_cn = models.CharField("ФИО из сертификата ЭЦП", max_length=500, blank=True)
    cert_issuer = models.CharField("Удостоверяющий центр (УЦ)", max_length=500, blank=True)

    class Meta:
        verbose_name = "Подпись документа"
        verbose_name_plural = "Подписи документа"
        ordering = ("role",)

    def __str__(self):
        return f"{self.get_role_display()} — {self.signed_by or '—'}"


class UniversalRKDAcknowledgment(models.Model):
    """Строка листа ознакомления по шагу маршрута с ЭЦП."""

    rkd = models.ForeignKey(
        UniversalRKD,
        on_delete=models.CASCADE,
        related_name="acknowledgments",
        verbose_name="Документ РКД",
    )
    process = models.ForeignKey(
        "approvals.ApprovalProcess",
        on_delete=models.CASCADE,
        related_name="acknowledgments",
        verbose_name="Согласование",
    )
    task = models.OneToOneField(
        "approvals.ApprovalTask",
        on_delete=models.CASCADE,
        related_name="acknowledgment",
        verbose_name="Задача",
    )
    department = models.ForeignKey(
        "approvals.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Роль",
    )
    position = models.CharField("Отдел", max_length=150, blank=True)
    signed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rkd_acknowledgments",
        verbose_name="Подписант",
    )
    signed_at = models.DateField("Дата", null=True, blank=True)
    cert_cn = models.CharField("ФИО из сертификата ЭЦП", max_length=500, blank=True)
    cert_issuer = models.CharField("Удостоверяющий центр (УЦ)", max_length=500, blank=True)
    step_order = models.PositiveSmallIntegerField("Порядок в маршруте", default=0)

    class Meta:
        verbose_name = "Ознакомление (лист)"
        verbose_name_plural = "Ознакомления (лист)"
        ordering = ("step_order", "pk")

    def __str__(self):
        return f"{self.position or self.department or '—'} — {self.signed_by or '—'}"


class Shipment(models.Model):
    """Отгрузки изделий в рамках разработки (модификации)."""

    post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="shipments",
        verbose_name="Разработка (модификация)",
    )
    serial_number = models.CharField(max_length=20, verbose_name="Заводской номер")
    manufacture_date = models.DateField(verbose_name="Дата изготовления")
    product_passport = models.FileField(
        upload_to="blog/shipment/passport/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Паспорт/Формуляр",
    )
    manufacturer_org = models.ForeignKey(
        "RKDDeveloper",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shipments_manufacturer",
        verbose_name="Изготовитель",
    )
    supplier_org = models.ForeignKey(
        "RKDDeveloper",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shipments_supplier",
        verbose_name="Поставщик",
    )
    shipment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата отгрузки",
    )
    buyer = models.ForeignKey(
        "crm.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_buyers",
        verbose_name="Покупатель",
    )
    recipient = models.ForeignKey(
        "crm.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments",
        verbose_name="Грузополучатель",
    )
    completeness = models.TextField(
        max_length=5000,
        blank=True,
        default="",
        verbose_name="Комплектность",
    )
    note = models.TextField(
        max_length=1000,
        blank=True,
        default="",
        verbose_name="Примечание",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_created",
        verbose_name="Создатель",
    )
    date_of_creation = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата и время создания",
    )
    last_editor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_edited",
        verbose_name="Последний редактор",
    )
    date_of_change = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата и время последнего изменения",
    )
    current_responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_responsible",
        verbose_name="Текущий ответственный",
    )

    class Meta:
        verbose_name = "Изделие к отгрузке"
        verbose_name_plural = "Изделия к отгрузке"
        ordering = ("post", "manufacture_date", "serial_number", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("post", "serial_number"),
                name="blog_shipment_unique_serial_per_post",
            ),
        ]

    def __str__(self):
        return f"{self.serial_number} — {self.post}"

    def clean(self):
        super().clean()
        if self.serial_number is not None:
            self.serial_number = self.serial_number.strip()

        if self.post_id and self.serial_number:
            qs = Shipment.objects.filter(
                post_id=self.post_id,
                serial_number=self.serial_number,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                p = Post.objects.filter(pk=self.post_id).only("name").first()
                post_title = p.name if p else "—"
                raise ValidationError(
                    {
                        "serial_number": (
                            f"В отгрузке по разработке «{post_title}» такой заводской номер уже существует."
                        ),
                    }
                )

        if (
            self.shipment_date
            and self.manufacture_date
            and self.shipment_date < self.manufacture_date
        ):
            raise ValidationError(
                {
                    "shipment_date": (
                        "Дата отгрузки не может быть раньше даты изготовления."
                    ),
                }
            )


class ShipmentAdditionalFile(models.Model):
    """Дополнительные файлы к отгрузке (несколько штук)."""

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="additional_files",
        verbose_name="Отгрузка",
    )
    file = models.FileField(
        upload_to="blog/shipment/additional/%Y/%m/",
        verbose_name="Файл",
    )

    class Meta:
        verbose_name = "Дополнительный файл отгрузки"
        verbose_name_plural = "Дополнительные файлы отгрузки"

    def __str__(self):
        return self.file.name if self.file else str(self.pk)



#Протоколы ПСИ СПМ ИБП
class PSIDocument(models.Model):
    # --- Основная информация ---

    # СВЯЗЬ С ОРГАНИЗАЦИЕЙ-РАЗРАБОТЧИКОМ (для логотипа и названия)
    developer_org = models.ForeignKey(
        'RKDDeveloper',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='psi_documents',
        verbose_name="Организация-разработчик/изготовитель"
    )
    # СВЯЗЬ С ИЗДЕЛИЕМ К ОТГРУЗКЕ (заводской номер)
    shipment = models.ForeignKey(
        'Shipment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='psi_documents',
        verbose_name="Изделие к отгрузке"
    )
    # СВЯЗЬ С РАЗРАБОТКОЙ (модификацией)
    post = models.ForeignKey(
        'Post',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='psi_documents',
        verbose_name="Разработка (модификация)"
    )
    test_date = models.DateField("Дата испытания / изготовления")
    fw_version = models.CharField("Версия программы управления ИБП", max_length=50)

    # --- Варианты выбора для статусов ---
    STATUS_CHOICES = [
        ('соответствует', 'Соответствует'),
        ('не соответствует', 'Не соответствует'),
        ('нет данных', 'Нет данных'),
    ]
    SHIPMENT_CHOICES = [
        ('готов к отгрузке', 'Готов к отгрузке'),
        ('не готов', 'Не готов')
    ]
    ELECTRO_CHOICES = [
        ('≥ 1 МОм', '≥ 1 МОм'),
        ('отклонение', 'Отклонение'),
        ('нет данных', 'Нет данных')
    ]
    TEMPERATURE_CHOICES = [
        ('норма (15 °С ... 35 °С)', 'Норма (15 °С ... 35 °С)'),
        ('отклонение', 'Отклонение'),
        ('нет данных', 'Нет данных')
    ]
    HUMIDITY_CHOICES = [
        ('норма (30 % ... 60 %)', 'норма (30 % ... 60 %)'),
        ('отклонение', 'Отклонение'),
        ('нет данных', 'Нет данных')
    ]
    PRESSURE_CHOICES = [
        ('норма (84 кПа ... 106,7 кПа)', 'норма (84 кПа ... 106,7 кПа)'),
        ('отклонение', 'Отклонение'),
        ('нет данных', 'Нет данных')
    ]

    # --- Общие проверки ---
    visual_check = models.CharField("1 Проверка соответствия КД и проверка внешнего вида (1.1.1, 1.4.2 ТУ, 5.3 ПМ)",
                                    max_length=20, choices=STATUS_CHOICES, default='нет данных')
    marking_check = models.CharField("2 Проверка содержания маркировки (1.10.1 ТУ, 5.1 ПМ)",
                                     max_length=20, choices=STATUS_CHOICES, default='нет данных')
    insulation_res = models.CharField("3 Проверка электрического сопротивления изоляции (2.5 ТУ, 5.6 ПМ)",
                                      max_length=20, choices=STATUS_CHOICES, default='нет данных')
    insulation_res_value = models.DecimalField(
        "Фактическое значение сопротивления изоляции, МОм",
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Введите измеренное значение в МОм. Статус устанавливается автоматически: при ≥ 1 МОм - Соответствует; при < 1 МОм - Не соответствует. "
    )

    insulation_strength = models.CharField("4 Проверка электрической прочности изоляции (2.6 ТУ, 5.7 ПМ)", max_length=20, choices=STATUS_CHOICES, default='нет данных')

    # --- Проверка функционирования (5.6) ---
    func_power_on = models.CharField("5.1 Проверка включения", max_length=20, choices=STATUS_CHOICES, default='нет данных')
    func_display = models.CharField("5.2 Проверка индикации", max_length=20, choices=STATUS_CHOICES, default='нет данных')
    func_navigation = models.CharField("5.3 Проверка навигации по информационным страницам", max_length=20, choices=STATUS_CHOICES, default='нет данных')
    func_battery_mode = models.CharField("5.4 Проверка работы от аккумуляторных батарей (АБ)", max_length=20, choices=STATUS_CHOICES, default='нет данных')
    func_bypass = models.CharField("5.5 Проверка режима «байпас»", max_length=20, choices=STATUS_CHOICES, default='нет данных')
    func_audio = models.CharField("5.6 Проверка интерфейсов SNMP и UART (Использовать web-приложение для мониторинга ИБП СПМ)", max_length=20, choices=STATUS_CHOICES, default='нет данных')
    # НОВОЕ ПОЛЕ: файл для 5.6
    interface_file = models.FileField(
        upload_to="psi_interfaces_files/",
        blank=True,
        null=True,
        verbose_name="Загружаемый файл (SNMP/UART)",
        help_text="Прикрепите файл с результатами проверки интерфейсов SNMP и UART"
    )
    # НОВОЕ ПОЛЕ: примечание для 5.6 (2000 знаков)
    interface_note = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Примечание (п. 5.6)",
        help_text="Мотивы несоответствия (заполняется, если по п. 5.6 выбрано «Не соответствует»)"
    )

    func_settings = models.CharField("5.7 Проверка отключения звукового сигнала", max_length=20, choices=STATUS_CHOICES, default='нет данных')
    func_terminal = models.CharField("5.8 Проверка настроек", max_length=20, choices=STATUS_CHOICES, default='нет данных')

    # --- Заключение ---
    conclusion = models.CharField("Заключение", max_length=50, choices=SHIPMENT_CHOICES, default="нет данных")
    comment = models.TextField("Комментарий", blank=True)

    # --- Условия испытаний (Метеоусловия) ---
    inspector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="psi_inspector", verbose_name="Представитель ОТК",)

    #связь с помещением
    workshop = models.ForeignKey('enterprise_asset_management.ProductionArea', on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='psi_documents',
        verbose_name="Производственная площадка (Цех)")

    remark = models.TextField("Комментарий", blank=True)
    temperature = models.CharField("Температура", choices=TEMPERATURE_CHOICES, max_length=50, default="+22°C")
    humidity = models.CharField("Влажность", choices=HUMIDITY_CHOICES, max_length=50, default="45%")
    pressure = models.CharField("Давление", choices=PRESSURE_CHOICES, max_length=50, default="750 мм рт. ст.")

    created_at = models.DateTimeField('Создан', auto_now_add=True)

    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="psi_document_created",
        verbose_name="Автор",
    )
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="psi_document_edited",
        verbose_name="Последний редактор",
    )
    version = models.CharField(max_length=3, default="1", verbose_name="Версия")
    version_diff = models.TextField(
        blank=True,
        default="Стартовая версия",
        verbose_name="Сравнение версий",
    )
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="psi_document_responsible",
        verbose_name="Текущий ответственный",
    )

    class Meta:
        verbose_name = "ПСИ ИБП СПМ"
        verbose_name_plural = "ПСИ ИБП СПМ"

    def __str__(self):
        # Пытаемся получить серийный номер из связанной модели Shipment
        serial = self.shipment.serial_number if self.shipment else "[не указан]"

        # Пытаемся получить название модели из связанной разработки (Post)
        model_name = self.post.name if self.post else "Модель не указана"

        return f"Протокол {serial} ({model_name})"

    def clean(self):
        """Валидация модели"""
        #from django.core.exceptions import ValidationError

        # ИЗМЕНЕНИЕ 5: Если файл не прикреплен - автомат-ки "НЕ соответ"
        if not self.interface_file:
            self.func_audio = 'не соответствует'

    def all_checks_passed(self):
        """True только если ВСЕ проверки в статусе 'соответствует'
        (нет ни одного 'не соответствует' или 'нет данных')."""
        checks = (
            self.visual_check, self.marking_check,
            self.insulation_res, self.insulation_strength,
            self.func_power_on, self.func_display, self.func_navigation,
            self.func_battery_mode, self.func_bypass, self.func_audio,
            self.func_settings, self.func_terminal,
        )
        return all(status == 'соответствует' for status in checks)

    def save(self, *args, **kwargs):

            # 5.6: если файл интерфейсов не прикреплён — статус "не соответствует"
        if not self.interface_file:
            self.func_audio = 'не соответствует'

            # 3: статус сопротивления изоляции определяется автоматически по
            #     фактическому значению (порог 1 МОм):
            #       нет значения      -> "нет данных"
            #       значение < 1 МОм  -> "не соответствует"
            #       значение >= 1 МОм -> "соответствует"
        if self.insulation_res_value is None:
            self.insulation_res = 'нет данных'
        elif self.insulation_res_value < 1:
            self.insulation_res = 'не соответствует'
        else:
                self.insulation_res = 'соответствует'

            # Заключение: если хотя бы одна проверка "не соответствует" или "нет данных" —
            # изделие не готово к отгрузке.
        if self.all_checks_passed():
            self.conclusion = 'готов к отгрузке'
        else:
            self.conclusion = 'не готов'

            # Вызываем финальное сохранение со всеми обновленными полями
        super().save(*args, **kwargs)

    def get_inspector_display(self):
        """Возвращает полное ФИО испытателя на русском (Фамилия Имя Отчество)."""
        if not self.inspector:
            return "—"
        user = self.inspector
        last = user.last_name or ''
        first = user.first_name or ''
        patronymic = ''
        if hasattr(user, 'profile') and user.profile.patronymic:
            patronymic = user.profile.patronymic
        parts = [p for p in [last, first, patronymic] if p]
        return ' '.join(parts) if parts else user.username

    def get_inspector_ecp(self):
        """Возвращает строку ECP для PDF — заглушка подписи."""
        return "ЭЦП"

    def get_workshop_display(self):
        """Возвращает цех"""
        return self.workshop if self.workshop else "—"

    def clean(self):
        super().clean()

        # Проверяем только при СОЗДАНИИ нового документа ПСИ
        if not self.pk and self.shipment_id:
            # Проверяем, существует ли уже ПСИ для этого изделия
            exists = PSIDocument.objects.filter(shipment=self.shipment.id).exists()
            if exists:
                raise ValidationError({
                    'shipment': (
                        f"Для изделия «{self.shipment}» уже создан документ ПСИ. "
                        f"Повторное создание ПСИ запрещено. Вы можете отредактировать существующий."
                    )
                })

class GeneratedDocument(models.Model):
    # Вместо старого source теперь привязка к PSIDocument
    psi_source = models.ForeignKey(PSIDocument, on_delete=models.CASCADE, related_name='pdfs', verbose_name="Протокол-источник",null=True, blank=True)
    file = models.FileField("Готовый PDF", upload_to='generated_pdfs/')
    version = models.PositiveIntegerField("Версия")
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Сгенерированный PDF"
        verbose_name_plural = "Сгенерированные PDF"

class DocumentHistory(models.Model):
    # Привязка к новой модели
    psi_source = models.ForeignKey(PSIDocument, on_delete=models.CASCADE, related_name='history', verbose_name="Протокол",null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Пользователь")
    action = models.CharField("Действие", max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)


# ПСИ ПАК СПМ
class PAKDocument(models.Model):
    """Протокол приёмо-сдаточных испытаний ПАК СПМ."""

    STATUS_CHOICES = [
        ('соответствует', 'Соответствует'),
        ('не соответствует', 'Не соответствует'),
        ('нет данных', 'Нет данных'),
    ]
    SHIPMENT_CHOICES = [
        ('готов к отгрузке', 'Готов к отгрузке'),
        ('не готов', 'Не готов'),
    ]
    TEMPERATURE_CHOICES = [
        ('норма (15 °С ... 35 °С)', 'Норма (15 °С ... 35 °С)'),
        ('отклонение', 'Отклонение'),
        ('нет данных', 'Нет данных')
    ]
    HUMIDITY_CHOICES = [
        ('норма (30 % ... 60 %)', 'норма (30 % ... 60 %)'),
        ('отклонение', 'Отклонение'),
        ('нет данных', 'Нет данных')
    ]
    PRESSURE_CHOICES = [
        ('норма (84 кПа ... 106,7 кПа)', 'норма (84 кПа ... 106,7 кПа)'),
        ('отклонение', 'Отклонение'),
        ('нет данных', 'Нет данных')
    ]

    # --- Связи (как у ИБП: номер/зав.№ берутся из shipment) ---
    shipment = models.ForeignKey(
        'Shipment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pak_documents', verbose_name='Изделие к отгрузке'
    )
    post = models.ForeignKey(
        'Post', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pak_documents', verbose_name='Модификация ПАК СПМ'
    )
    developer_org = models.ForeignKey(
        'RKDDeveloper', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pak_documents', verbose_name='Организация-разработчик'
    )

    # --- Основная информация ---
    fw_version = models.CharField('Версия ПО', max_length=50, blank=True, default='')
    test_date_start = models.DateField('Дата начала проведения испытаний')
    test_date_end = models.DateField('Дата окончания испытаний', null=True, blank=True)

    # --- Проверки (Таблица 1) ---
    check_marking = models.CharField(
        '1 Проверка содержания маркировки (1.5.2 ТУ, 3.1 ПМ)',
        max_length=20, choices=STATUS_CHOICES
    )
    check_kd_appearance = models.CharField(
        '2 Проверка соответствия ПАК СПМ КД и внешнего вида (1.1.1, 1.1.9 ТУ, 3.2 ПМ)',
        max_length=20, choices=STATUS_CHOICES
    )
    check_server_link = models.CharField(
        '3 Проверка обеспечения связи с сервером (1.1.5, 1.1.4 ТУ, 3.3 ПМ)',
        max_length=20, choices=STATUS_CHOICES
    )
    check_alarm = models.CharField(
        '4 Проверка обнаружения и регистрации аварии (1.1.2, 1.1.4 ТУ, 3.4 ПМ)',
        max_length=20, choices=STATUS_CHOICES
    )
    # Пункт 4: файл с логами от прибора + примечание
    alarm_log_file = models.FileField(
        'Файл с логами (п. 4)', upload_to='pak_documents/alarm_logs/%Y/%m/%d/',
        null=True, blank=True
    )
    alarm_note = models.TextField(
        'Примечание (п. 4)', blank=True, default='',
        help_text='Комментарий по проверке обнаружения/регистрации аварии'
    )
    check_battery_status = models.CharField(
        '5 Проверка контроля и передачи статуса батареи (1.1.7 ТУ, 3.5 ПМ)',
        max_length=20, choices=STATUS_CHOICES
    )
    check_radio_settings = models.CharField(
        '6 Проверка обеспечения изменения настроек по радиоканалу ближней связи (1.1.6 ТУ, 3.6 ПМ)',
        max_length=20, choices=STATUS_CHOICES
    )
    check_long_run = models.CharField(
        '7 Проверка длительной работы ПАК СПМ (3.7 ПМ)',
        max_length=20, choices=STATUS_CHOICES
    )

    # --- Заключение ---
    conclusion = models.CharField(
        'Заключение', max_length=20, choices=SHIPMENT_CHOICES
    )
    comment = models.TextField('Комментарий', blank=True, default='')

    # --- ОТК ---
    inspector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="pak_inspector", verbose_name="Представитель ОТК",)

    # связь с помещением
    workshop = models.ForeignKey('enterprise_asset_management.ProductionArea', on_delete=models.SET_NULL,
                                 null=True,
                                 blank=True,
                                 related_name='pak_documents',
                                 verbose_name="Производственная площадка (Цех)")

    remark = models.TextField("Комментарий", blank=True)
    temperature = models.CharField("Температура", choices=TEMPERATURE_CHOICES, max_length=50, default="+22°C")
    humidity = models.CharField("Влажность", choices=HUMIDITY_CHOICES, max_length=50, default="45%")
    pressure = models.CharField("Давление", choices=PRESSURE_CHOICES, max_length=50, default="750 мм рт. ст.")

    created_at = models.DateTimeField('Создан', auto_now_add=True)

    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_pak_created",
        verbose_name="Автор",
    )
    date_of_creation = models.DateTimeField(auto_now=True, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_pak_documents",
        verbose_name="Последний редактор",
    )
    version = models.CharField(max_length=3, default="1", verbose_name="Версия")
    version_diff = models.TextField(
        blank=True,
        default="Стартовая версия",
        verbose_name="Сравнение версий",
    )
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pak_document_responsible",
        verbose_name="Текущий ответственный",
    )

    class Meta:
        verbose_name = 'ПСИ ПАК СПМ'
        verbose_name_plural = 'ПСИ ПАК СПМ'
        ordering = ['-created_at']

    def __str__(self):
        serial = self.shipment.serial_number if self.shipment else '—'
        return f'Протокол ПАК СПМ {serial}'

    def clean(self):
        """Валидация модели"""
        # п. 4: если файл с логами не прикреплён — статус автоматически "нет данных".
        # Требование примечания при "не соответствует" проверяется в форме (PAKDocumentForm).
        if not self.alarm_log_file:
            self.check_alarm = 'нет данных'

    def all_checks_passed(self):
        """True, только если ВСЕ проверки в статусе 'соответствует'
        (нет ни одного 'не соответствует' или 'нет данных')."""
        checks = (
            self.check_marking,
            self.check_kd_appearance,
            self.check_server_link,
            self.check_alarm,
            self.check_battery_status,
            self.check_radio_settings,
            self.check_long_run,
        )
        return all(status == 'соответствует' for status in checks)

    def save(self, *args, **kwargs):
        # п. 4 если файл интерфейсов не прикреплён — статус "не соответствует"
        if not self.alarm_log_file:
            self.check_alarm = 'не соответствует'

        # Заключение определяется автоматически по результатам проверок:
        # любое 'не соответствует' или 'нет данных' -> не готов к отгрузке.

        if self.all_checks_passed():
            self.conclusion = 'готов к отгрузке'
        else:
            self.conclusion = 'не готов'
        super().save(*args, **kwargs)


class PAKGeneratedDocument(models.Model):
    """Сгенерированный PDF протокола ПАК СПМ."""
    pak_source = models.ForeignKey(
        PAKDocument, on_delete=models.CASCADE, related_name='pdfs',
        verbose_name='Протокол-источник', null=True, blank=True
    )
    file = models.FileField('Готовый PDF', upload_to='pak_generated_pdfs/')
    version = models.PositiveIntegerField('Версия')
    generated_at = models.DateTimeField('Сгенерирован', auto_now_add=True)

    class Meta:
        verbose_name = 'Сгенерированный PDF (ПАК СПМ)'
        verbose_name_plural = 'Сгенерированные PDF (ПАК СПМ)'
        ordering = ['-version']

    def __str__(self):
        return f'PDF ПАК СПМ v{self.version}'


class PAKDocumentHistory(models.Model):
    """История изменений протокола ПАК СПМ."""
    pak_source = models.ForeignKey(
        PAKDocument, on_delete=models.CASCADE, related_name='history',
        verbose_name='Протокол', null=True, blank=True
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='pak_document_history', verbose_name='Пользователь'
    )
    action = models.CharField('Действие', max_length=255)
    timestamp = models.DateTimeField('Время', auto_now_add=True)

    class Meta:
        verbose_name = 'История протокола ПАК СПМ'
        verbose_name_plural = 'История протоколов ПАК СПМ'
        ordering = ['-timestamp']