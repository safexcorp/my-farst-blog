from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from .helpers import (
    SPECIFICATION_SECTION_CHOICES,
    allowed_categories_for_section,
    section_has_category_choices,
    specification_section_sort_index,
)

User = settings.AUTH_USER_MODEL
User = get_user_model()


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





# Модель Post
class Post(models.Model):
    LITERA_CHOICES = [
        ('П-', 'П-'),
        ('П', 'П'),
    ]

    TRL_CHOICES = [
        ('1-', '1-'),
        ('1', '1'),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name="Наименование")
    desig_document_post = models.CharField(max_length=50, null=True, verbose_name="Обозначение изделия")
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
    litera = models.CharField(max_length=20, choices=LITERA_CHOICES, default='П-',
                              verbose_name="Стадия разработки (литера)")
    trl = models.CharField(max_length=10, choices=TRL_CHOICES, default='1-',
                           verbose_name="Уровень готовности технологий (TRL)")

    technical_proposal = models.OneToOneField('TechnicalProposal', on_delete=models.SET_NULL, blank=True, null=True,
                                              related_name='Post', verbose_name='Техническое предложение')
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
        verbose_name_plural = "Разработки"

    def __str__(self):
        return self.name


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


# Модель TechnicalProposal
class TechnicalProposal(models.Model):
    LITERA_CHOICES = [
        ('П-', 'П-'),
        ('П', 'П'),
    ]

    TRL_CHOICES = [
        ('1-', '1-'),
        ('1', '1'),
    ]
    name = models.CharField(max_length=200, unique=True, verbose_name="Категория")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(User, related_name='tp_last_edited_by', on_delete=models.SET_NULL, null=True, verbose_name="Последний редактор")
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(User, related_name='tp_current_responsible', on_delete=models.SET_NULL, null=True, verbose_name="Текущий ответственный")
    version = models.CharField(max_length=20, blank=True, default='1', verbose_name="Версия")
    version_diff = models.TextField(max_length=1000, blank=True, default='Стартовая версия', verbose_name="Сравнение версий")
    litera = models.CharField(max_length=20, choices=LITERA_CHOICES, default='П-', verbose_name="Стадия разработки  (Литера)")
    trl = models.CharField(max_length=10, choices=TRL_CHOICES, default='1-', verbose_name="Уровень готовности технологий (TRL)")

    list_technical_proposal = models.OneToOneField(ListTechnicalProposal, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ведомость технического предложения")
    general_drawing_product = models.OneToOneField(GeneralDrawingProduct, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Чертеж общего вида изделия")
    electronic_model_product = models.OneToOneField(ElectronicModelProduct, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Электронная модель изделия ")
    general_electrical_diagram = models.OneToOneField(GeneralElectricalDiagram, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Схема электрическая общая")
    software_product = models.OneToOneField(SoftwareProduct, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Программное обеспечение Технического предложения")
    report_technical_proposal = models.OneToOneField(ReportTechnicalProposal, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Пояснительная записка ПЗ ПТ")
    protocol_technical_proposal = models.OneToOneField(ProtocolTechnicalProposal, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Протокол. Техническое предложение")

    general_drawing_unit = models.ManyToManyField(GeneralDrawingUnit, blank=True, verbose_name="Чертеж общего вида сборочной единицы")
    electronic_model_unit = models.ManyToManyField(ElectronicModelUnit, blank=True, verbose_name="Электронная модель сборочной единицы")
    drawing_part_unit = models.ManyToManyField(DrawingPartUnit, blank=True, verbose_name="Чертеж детали сборочной единицы")
    electronic_model_part_unit = models.ManyToManyField(ElectronicModelPartUnit, blank=True, verbose_name="Электронная модель детали сборочной единицы")
    drawing_part_product = models.ManyToManyField(DrawingPartProduct, blank=True, verbose_name="Чертеж детали изделия")
    electronic_model_part_product =  models.ManyToManyField(ElectronicModelPartProduct, blank=True, verbose_name="Электронная модель детали изделия")
    add_report_technical_proposal = models.ManyToManyField(AddReportTechnicalProposal, blank=True, verbose_name="ПЗ ПТ Приложение")

    class Meta:
        verbose_name = "Техническое предложение"
        verbose_name_plural = "Технические предложения"

    def __str__(self): return self.name


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
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='task_for_design_work', verbose_name="Связанная разработка")
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
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='revision_tasks', verbose_name="Связанная разработка")
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
        ('done', 'Выполнено'),
        ('changed', 'Срок выполнения изменен'),
        ('canceled', 'Задание отменено'),
    ]

    # базовые поля
    name = models.CharField(max_length=100, unique=True, blank=True, null=True, verbose_name="Наименование")
    category = models.CharField(max_length=100, default="РЗ", verbose_name="Категория")
    executor = models.ForeignKey(User, on_delete=models.CASCADE, null= True, related_name= "executed_workassignments", verbose_name="Исполнитель")
    task = models.CharField('Задача', max_length=255, blank=True)
    post = models.ForeignKey('Post', on_delete=models.CASCADE, null=True, blank=True, related_name='work_assignments', verbose_name="Связанная разработка")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Автор")
    date_of_creation = models.DateTimeField(default=timezone.now, verbose_name="Дата и время создания")
    last_editor = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="edited_workassignments",
        verbose_name="Последний редактор"
    )
    date_of_change = models.DateTimeField(auto_now=True, verbose_name="Дата и время последнего изменения")
    current_responsible = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="responsible_workassignments",
        verbose_name="Текущий ответственный"
    )
    version = models.CharField(max_length=3, blank=True, null=True, verbose_name="Версия")
    task = models.TextField(verbose_name="Задача")
    acceptance_criteria = models.TextField(default='---', verbose_name="Критерий выполнения")
    uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Загружаемый файл")

    deadline_version = models.PositiveIntegerField(default=0, verbose_name="Версия дедлайна")
    reschedule_count = models.PositiveIntegerField(default=0, verbose_name="Количество переносов")


    result = models.CharField(max_length=100, choices=RESULT_CHOICES, blank=True, null=True, verbose_name="Результат")
    result_description = models.TextField(max_length=5000, blank=True, null=True, verbose_name="Описание результата")
    route = models.ForeignKey("Route", on_delete=models.CASCADE, related_name='routes', blank=True, null=True, verbose_name="Маршрут")

    target_deadline = models.DateField("Целевой срок выполнения", default=timezone.now, null=False, blank=False)
    hard_deadline = models.DateField("Абсолютный дедлайн", null=True, blank=True)
    time_window_start = models.DateField("Временное окно: с", null=True, blank=True)
    time_window_end = models.DateField("Временное окно: по", null=True, blank=True)
    conditional_deadline = models.CharField("Условный дедлайн", max_length=1000, blank=True)
    #uploaded_file = models.FileField(upload_to='uploads/', blank = True, verbose_name="Приложение к РЗ")

    control_status = models.CharField(
        "Контроль срока — статус",
        max_length=20,
        null=True,
        blank=True,
        choices=TEMP_STATUS_CHOICES,
    )
    control_date = models.DateField("Контроль срока — дата", null=True, blank=True)

   #def _build_name(self) -> str:
    #    sep = " — "  # любой разделитель
     #   technical_assignment_part = (self.technical_assignment.name if self.technical_assignment_id else "").strip()
#
 #       # Нормализуем и режем вторую часть до 50 символов без троеточия
  #      task_clean = " ".join((self.task or "").split())
   #     # чтобы не переполнить name, сначала считаем доступную длину под вторую часть
    #    max_len = self._meta.get_field('name').max_length
     #   allowed_for_task = max(0, min(50, max_len - len(sep) - len(technical_assignment_part)))
      #  task_part = Truncator(task_clean).chars(allowed_for_task, truncate='')

       # return f"{technical_assignment_part}{sep}{task_part}" if task_part else technical_assignment_part"""

    def clean(self):
        super().clean()
        if self.hard_deadline and self.target_deadline:
            if self.hard_deadline < self.target_deadline:
                raise ValidationError({
                    "hard_deadline": _(
                        "Абсолютный дедлайн не может быть раньше целевого."
                    )
                })

        if self.time_window_end and self.target_deadline:
            if self.time_window_end > self.target_deadline:
                raise ValidationError({
                    "time_window_end": _(
                        "Конец временного окна не может быть позже целевого дедлайна."
                    )
                })

            def save(self, *args, **kwargs):
                self.full_clean()
                return super().save(*args, **kwargs)
    class Meta:
        verbose_name = 'Рабочее задание'
        verbose_name_plural = 'Рабочие задания'

    #def save(self, *args, **kwargs):
     #   self.name = self._build_name()
      #  super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # проверка окна
        if self.time_window_start and self.time_window_end:
            if self.time_window_end < self.time_window_start:
                raise ValidationError({'time_window_end': 'Дата «по» не может быть раньше даты «с».'})

    def clean(self):
        super().clean()
        if self.time_window_start and self.time_window_end and self.time_window_end < self.time_window_start:
            raise ValidationError({'time_window_end': 'Дата «по» не может быть раньше даты «с».'})
        if self.target_deadline and self.time_window_start and self.time_window_end:
            if not (self.time_window_start <= self.target_deadline <= self.time_window_end):
                raise ValidationError({'target_deadline': 'Целевой срок должен попадать в заданное окно.'})
        if self.hard_deadline and self.target_deadline and self.target_deadline > self.hard_deadline:
            raise ValidationError({'target_deadline': 'Целевой срок не может быть позже абсолютного дедлайна.'})

    @property
    def effective_deadline(self):
        if self.hard_deadline and self.target_deadline:
            return min(self.target_deadline, self.hard_deadline)
        if self.target_deadline:
            return self.target_deadline
        if self.time_window_end:
            return self.time_window_end
        return self.deadline

    def is_active(self):
        return self.control_status not in ('canceled',)

    def is_overdue(self, today=None):
        if not self.is_active():
            return False
        d = self.effective_deadline
        if not d:
            return False
        today = today or timezone.localdate()
        return today > d

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

    def __str__(self):
        return self.name or "Без названия"

class WorkAssignmentDeadlineChange(models.Model):
    assignment = models.ForeignKey(
        WorkAssignment,
        on_delete=models.CASCADE,
        related_name="deadline_changes",
        verbose_name="Рабочее задание",
    )

    # что было
    old_target_deadline = models.DateField(null=True, blank=True, verbose_name="старый целевой дедлайн")
    old_hard_deadline   = models.DateField(null=True, blank=True, verbose_name="старый абсолютный дедлайн")
    old_time_window_start = models.DateField(null=True, blank=True, verbose_name="старое временное окно с")
    old_time_window_end   = models.DateField(null=True, blank=True, verbose_name="старое временное окно по")

    # что стало
    new_target_deadline = models.DateField(null=True, blank=True, verbose_name="новый целевой дедлайн")
    new_hard_deadline   = models.DateField(null=True, blank=True, verbose_name="новый абсолютный дедлайн")
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


class RKDDeveloper(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name="Название")
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
    additional_data = models.FileField(
        upload_to="rkd_developer/additional/",
        blank=True,
        null=True,
        verbose_name="Дополнительные данные",
    )

    class Meta:
        verbose_name = "Организация-разработчик"
        verbose_name_plural = "Организации-разработчики"

    def __str__(self):
        return self.name


class UniversalRKD(models.Model):
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
    desig_document = models.CharField(max_length=50, verbose_name="Обозначение документа")
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
        blank=True,
        null=True,
        verbose_name="Документ (загружаемый файл)",
    )
    approval_document = models.FileField(
        upload_to="blog/universal_rkd/approval/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Лист утверждения",
    )
    attestation_document = models.FileField(
        upload_to="blog/universal_rkd/attestation/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Удостоверяющий лист",
    )

    checked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="universal_rkd_checked",
        verbose_name="Проверил / согласовал",
    )
    signature_checked = models.FileField(
        upload_to="blog/universal_rkd/signatures/checked/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Подпись проверки (файл)",
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
        blank=True,
        null=True,
        verbose_name="Подпись утверждения (файл)",
    )

    quantity = models.CharField(max_length=10, blank=True, default="", verbose_name="Количество")
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
        verbose_name = "РКД"
        verbose_name_plural = "РКД"
        ordering = ("post_id", "section_sort_index", "order_in_section", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("post", "desig_document"),
                name="blog_universalrkd_unique_desig_per_post",
            ),
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
            dg = (self.desig_document or "").strip()
            qs_des = UniversalRKD.objects.filter(post_id=self.post_id, desig_document=dg)
            if self.pk:
                qs_des = qs_des.exclude(pk=self.pk)
            if qs_des.exists():
                raise ValidationError(
                    {
                        "desig_document": "В этой разработке уже есть позиция с таким обозначением документа."
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
        if self.status and self.status != "Зарегистрирован" and not self.document_uploaded_file:
            raise ValidationError(
                {"document_uploaded_file": "Загрузите документ для статуса, отличного от «Зарегистрирован»."}
            )
        if self.status == "Выпущен":
            if not self.checked_by:
                raise ValidationError({"checked_by": "Для статуса «Выпущен» укажите проверившего."})
            if not self.signature_checked:
                raise ValidationError({"signature_checked": "Для статуса «Выпущен» приложите подпись проверки."})
        if self.validity_date and (not self.signature_checked or not self.signature_approved):
            raise ValidationError(
                {
                    "validity_date": (
                        "Дату планового пересмотра можно указать только при наличии подписей проверки и утверждения."
                    ),
                }
            )

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
        verbose_name="Паспорт",
    )
    shipment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата отгрузки",
    )
    recipient = models.ForeignKey(
        "crm.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments",
        verbose_name="Получатель",
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
        verbose_name = "Отгрузка"
        verbose_name_plural = "Отгрузки"
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