from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator

User = get_user_model()


def validate_file_size(value):
    """Ограничение файла 50 МБ"""
    limit = 50 * 1024 * 1024  # 50 MB
    if value.size > limit:
        raise ValidationError('Размер файла не должен превышать 50 МБ')


def validate_avatar_size(value):
    """Ограничение аватарки 5 МБ"""
    limit = 5 * 1024 * 1024  # 5 MB
    if value.size > limit:
        raise ValidationError('Размер фото не должен превышать 5 МБ')


class SharedRepository(models.Model):

    id = models.AutoField(
        primary_key=True,
        verbose_name='Уникальный идентификатор'
    )

    # 2. Категория
    CATEGORY_CHOICES = [
        ('ОД', 'ОД'),
    ]

    category = models.CharField(
        max_length=10,
        verbose_name='Категория (Код вида документа)',
        choices=CATEGORY_CHOICES,
        blank=True, null=True,
        default='ОД',
        help_text='Значение по умолчанию "ОД"'
    )

    # 3. Название документа
    document_title = models.CharField(
        max_length=100,
        verbose_name='Название документа',
        unique=True,
        help_text='Все текстовые символы - 100 символов max'
    )

    # 4. Утвердил
    approval = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='approved_shared_repository',
        verbose_name='Утвердил',
        blank=True,
        null=True,
    )

    # 5. Подпись
    signature_approval = models.FileField(
        upload_to='shared_repository/signatures/approval/%Y/%m/%d/',
        verbose_name='Подпись (загружаемый файл)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Возможность подгрузить только один файл ЭЦП'
    )

    # 6. Дата утверждения
    date_approval = models.DateField(
        verbose_name='Дата утверждения',
        blank=True,
        null=True,
        help_text='Дата утверждения документа'
    )

    # 7. Ознакомление
    ACCEPT_CHOICES = [
        ('ЭЦП', 'ЭЦП'),
        ('---', '---'),
    ]

    accept = models.CharField(
        max_length=10,
        verbose_name='Ознакомление',
        choices=ACCEPT_CHOICES,
        blank=True,
        null=True,
        default='---',
        help_text='ЭЦП'
    )

    # 9. Создатель
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='authored_shared_repository',
        verbose_name='Создатель (автор)',
    )

    # 10. Дата и время создания
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now,
    )

    # 11. Последний редактор
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='last_edited_shared_repository',
        verbose_name='Последний редактор',
    )

    # 12. Дата и время последнего изменения
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True,
    )

    # 13. Текущий ответственный
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_shared_repository',
        verbose_name='Текущий ответственный',
    )

    # 14. Версия
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1',
    )

    # 15. Загружаемый файл
    uploaded_file = models.FileField(
        upload_to='shared_repository/documents/%Y/%m/%d/',
        verbose_name='Загружаемый файл',
        validators=[validate_file_size],
        help_text='Подгружаем только один файл'
    )

    approval_document = models.FileField(
        upload_to='shared_repository/approval/%Y/%m/',
        verbose_name='Лист утверждения (PDF)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Формируется автоматически при согласовании по маршруту.',
    )
    acquaintance_document = models.FileField(
        upload_to='shared_repository/acquaintance/%Y/%m/',
        verbose_name='Лист ознакомления (PDF)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Формируется автоматически при ознакомлении по маршруту.',
    )

    # 16. Назначение документа
    document_purpose = models.TextField(
        max_length=5000,
        verbose_name='Назначение документа',
        blank=True,
        null=True,
        help_text='Все текстовые символы - 5000 символов max'
    )

    related_documents = models.ManyToManyField(
        'QMSDocument',
        verbose_name='документы СМК',
        blank=True,
        help_text='Выбор из списка документов СМК. Можно выбрать несколько'
    )

    related_sharedrepository = models.ManyToManyField(
        'SharedRepository',
        verbose_name='отдельные документы',
        blank=True,
        help_text='Выбор из списка отдельных документов. Можно выбрать несколько'
    )

    # 17. Примечание документа
    note = models.TextField(
        max_length=5000,
        verbose_name='Примечание',
        blank=True,
        null=True,
        help_text='Дополнительные заметки и комментарии'
    )

    class Meta:
        verbose_name = 'Отдельный документ'
        verbose_name_plural = 'Отдельные документы'
        ordering = ['-date_of_creation']

    def __str__(self):
        return f"{self.document_title} (v{self.version})"

    def save(self, *args, **kwargs):
        """Автоматическая установка полей при сохранении"""
        if not self.pk:  # Если это новый документ
            # Автор = текущий ответственный = последний редактор
            # (устанавливается в админке или вьюхе)
            pass

        # Проверяем версию - должна содержать только цифры
        if self.version:
            self.version = ''.join(filter(str.isdigit, self.version))[:3]

        super().save(*args, **kwargs)

    def clean(self):
        """Валидация модели"""
        # Проверка версии - только цифры
        if self.version and not self.version.isdigit():
            raise ValidationError({
                'version': 'Версия должна содержать только цифры'
            })

        # Проверка длины версии
        if len(self.version) > 3:
            raise ValidationError({
                'version': 'Версия не должна превышать 3 символов'
            })

    # Дополнительная модель для множественных подписей ознакомления
class IndependentDocumentAcceptSignature(models.Model):
    """Множественные подписи ознакомления для SharedRepository"""
    document = models.ForeignKey(
        SharedRepository,
        on_delete=models.CASCADE,
        related_name='accept_signatures',
        verbose_name='Документ'
    )
    signature_file = models.FileField(
        upload_to='independent_documents/signatures/accept/%Y/%m/%d/',
        verbose_name='Файл подписи',
        validators=[validate_file_size],
        help_text='Файл ЭЦП ознакомления'
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата загрузки'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Загрузил'
    )

    class Meta:
        verbose_name = 'Подпись ознакомления'
        verbose_name_plural = 'Подписи ознакомления'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Подпись для {self.document.document_title}"


#База знаний
class KnowledgeBase(models.Model):

    # 1. Уникальный идентификатор
    id = models.AutoField(
        primary_key=True,
        verbose_name='Уникальный идентификатор'
    )

    # 2. Категория (код вида документа / записи)
    CATEGORY_CHOICES = [
        ('ДБЗ', 'ДБЗ - Документ базы знаний'),
    ]

    category = models.CharField(
        max_length=10,
        verbose_name='Категория (код вида документа/записи)',
        choices=CATEGORY_CHOICES,
        default='ДБЗ',
        help_text='Значение по умолчанию "ДБЗ"'
    )

    # 3. Название
    title = models.CharField(
        max_length=100,
        verbose_name='Название',
        unique=True,
        help_text='Словосочетание из нескольких слов (5-10) для краткой характеристики информации'
    )

    # 4. Группа знаний
    KNOWLEDGE_GROUP_CHOICES = [
        ('employee_experience', 'Опыт сотрудников (лучшая практика / образец)'),
        ('lesson_consumer', 'Выученный урок (связь с потребителем)'),
        ('lesson_design', 'Выученный урок (проектирование и разработка)'),
        ('lesson_production', 'Выученный урок (производство)'),
        ('scientific', 'Научный материал'),
        ('methodical', 'Методический материал'),
        ('reference', 'Справочный материал'),
    ]

    knowledge_group = models.CharField(
        max_length=30,
        verbose_name='Группа знаний',
        choices=KNOWLEDGE_GROUP_CHOICES,
        blank=True,
        null=True,
        help_text='Выбор из предопределенного списка'
    )

    # 5. Обращение / потребитель
    consumer_customer = models.ForeignKey(
         'crm.Customer',
         on_delete=models.PROTECT,
         verbose_name='Потребитель (контрагент)',
         related_name='knowledge_base_consumer',
         blank=True,
         null=True,
     )
    consumer_ticket = models.ForeignKey(
         'crm.SupportTicket',
         on_delete=models.SET_NULL,
         verbose_name='Обращение',
         related_name='knowledge_base_tickets',
         blank=True,
         null=True,
     )

    # 6. Применение знаний / практик (множественный выбор пользователей)
    knowledge_apply = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name='Применение знаний / практик',
        related_name='knowledge_base_applied',
        blank=True,
        help_text='Может быть выбрано несколько пользователей'
    )

    # 7. Создатель (автор)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_knowledge_base',
        verbose_name='Создатель (автор)',
    )

    # 8. Дата и время создания
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now,
    )

    # 9. Последний редактор
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='edited_knowledge_base',
        verbose_name='Последний редактор',
    )

    # 10. Дата и время последнего изменения
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True,
    )

    # 11. Текущий ответственный
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_knowledge_base',
        verbose_name='Текущий ответственный',
    )

    # 12. Версия
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1',
    )

    # 13. Содержание документа
    document_contents = models.TextField(
        max_length=5000,
        verbose_name='Содержание документа',
        blank=True,
        null=True,
        help_text='Что содержится в документе, для кого предназначен и т.д.'
    )

    # 14. Примечание
    note = models.TextField(
        max_length=2000,
        verbose_name='Примечание',
        blank=True,
        null=True,
        help_text='Дополнительная информация, условия'
    )

    class Meta:
        verbose_name = 'Запись базы знаний'
        verbose_name_plural = 'База знаний'
        ordering = ['-date_of_creation']

    def __str__(self):
        return f"{self.title} (v{self.version})"

    def save(self, *args, **kwargs):
        """Автоматическая установка полей при сохранении"""
        if not self.pk:  # Если это новый документ
            # Убеждаемся, что категория установлена
            if not self.category:
                self.category = 'ДБЗ'
        super().save(*args, **kwargs)

    def clean(self):
        """Валидация модели"""
        # Условие: если выбрана группа "Выученный урок (связь с потребителем)",
        # то обязательно нужно указать consumer_customer и consumer_ticket
        if self.knowledge_group == 'lesson_consumer':
            if not self.consumer_customer:
                raise ValidationError({
                    'knowledge_group': 'Для группы знаний "Выученный урок (связь с потребителем)" обязательно выбрать "Потребитель (контрагент)"'
                })
            if not self.consumer_ticket:
                raise ValidationError({
                    'knowledge_group': 'Для группы знаний "Выученный урок (связь с потребителем)" обязательно выбрать "Обращение"'
                })
        else:
            # Для других групп знаний поля могут быть пустыми
            pass

        # Проверка версии (оставляем существующую)
        if self.version and not self.version.isdigit():
            raise ValidationError({
                'version': 'Версия должна содержать только цифры'
            })
        if len(self.version) > 3:
            raise ValidationError({
                'version': 'Версия не должна превышать 3 символов'
            })


class KnowledgeBaseFile(models.Model):
    """
    Модель для множественных файлов базы знаний
    """
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='attached_files',
        verbose_name='Запись базы знаний'
    )

    file = models.FileField(
        upload_to='knowledge_base/%Y/%m/%d/',
        verbose_name='Файл',
        validators=[validate_file_size],
        help_text='Инструкции, скриншоты, подробное решение, примеры конфигов и т.п.'
    )

    description = models.CharField(
        max_length=200,
        verbose_name='Описание',
        blank=True,
        null=True,
        help_text='Краткое описание файла'
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата загрузки'
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Загрузил'
    )

    class Meta:
        verbose_name = 'Файл базы знаний'
        verbose_name_plural = 'Файлы базы знаний'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Файл для {self.knowledge_base.title}"


class QMSDocument(models.Model):
    """
    Модель "Документы СМК" (Система менеджмента качества)
    """

    # 1. Уникальный идентификатор
    id = models.AutoField(
        primary_key=True,
        verbose_name='Уникальный идентификатор'
    )

    # 2. Категория (код вида документа)
    CATEGORY_CHOICES = [
        ('РД СМК', 'РД СМК - Руководящий документ'),
        ('МУ СМК', 'МУ СМК - Методические указания'),
        ('---', '---'),
    ]

    category = models.CharField(
        max_length=10,
        verbose_name='Категория (код вида документа)',
        choices=CATEGORY_CHOICES,
        default='---',
        help_text='Выбор из предопределенного списка: РД СМК, МУ СМК, ---'
    )

    # 3. Название документа
    document_title = models.CharField(
        max_length=100,
        verbose_name='Название документа',
        unique=True,
        help_text='Все текстовые символы - 100 символов max'
    )

    # 4. Номер изменения
    change_number = models.CharField(
        max_length=8,
        verbose_name='Номер изменения',
        default='без изм.',
        help_text='8 символов max. По умолчанию "без изм."'
    )

    # 5. Утвердил
    approval = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='approved_qms_documents',
        verbose_name='Утвердил',
        blank=True,
        null=True,
        help_text='Выбор из списка пользователей'
    )

    # 6. Подпись (загружаемый файл) - ЭЦП утверждения
    approval_signature = models.FileField(
        upload_to='qms_documents/signatures/approval/%Y/%m/%d/',
        verbose_name='Подпись утверждения',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Файл ЭЦП утверждения (только один файл)'
    )

    # 7. Дата утверждения
    date_approval = models.DateField(
        verbose_name='Дата утверждения',
        blank=True,
        null=True,
        help_text='YYYY-MM-DD'
    )

    # 8. Ознакомление (выбор статуса)
    ACCEPT_CHOICES = [
        ('---', '---'),
        ('ЭЦП', 'ЭЦП'),
    ]

    accept = models.CharField(
        max_length=10,
        verbose_name='Ознакомление',
        choices=ACCEPT_CHOICES,
        blank=True,
        null=True,
        default='---',
        help_text='Выбор из списка: ---, ЭЦП'
    )

    # 9. Создатель (автор)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_qms_documents',
        verbose_name='Создатель (автор)',
    )

    # 10. Дата и время создания
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now,
    )

    # 11. Последний редактор
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='edited_qms_documents',
        verbose_name='Последний редактор',
    )

    # 12. Дата и время последнего изменения
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True,
    )

    # 13. Текущий ответственный
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_qms_documents',
        verbose_name='Текущий ответственный',
    )

    # 14. Версия
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1',
    )

    # 15. Загружаемый файл (основной документ)
    uploaded_file = models.FileField(
        upload_to='qms_documents/documents/%Y/%m/%d/',
        verbose_name='Загружаемый файл',
        validators=[validate_file_size],
        help_text='Основной файл документа (только один файл)'
    )

    approval_document = models.FileField(
        upload_to='qms_documents/approval/%Y/%m/',
        verbose_name='Лист утверждения (PDF)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Формируется автоматически при согласовании по маршруту.',
    )
    acquaintance_document = models.FileField(
        upload_to='qms_documents/acquaintance/%Y/%m/',
        verbose_name='Лист ознакомления (PDF)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Формируется автоматически при ознакомлении по маршруту.',
    )

    # 16. Назначение документа
    document_purpose = models.TextField(
        max_length=5000,
        verbose_name='Назначение документа',
        blank=True,
        null=True,
        help_text='Для чего (для какой деятельности), для кого предназначен документ и т.д.'
    )

    # 17. Дата планового пересмотра (было validity_date)
    review_date = models.DateField(
        verbose_name='Дата планового пересмотра',
        blank=True,
        null=True,
        help_text='За 60 дней до этой даты появится предупреждение'
    )

    # 18. Связанные документы
    related_documents = models.ManyToManyField(
        'SharedRepository',
        verbose_name='отдельные документы',
        blank=True,
        help_text='Выбор из списка отдельных документов. Можно выбрать несколько'
    )

    related_qms_documents = models.ManyToManyField(
        'QMSDocument',
        verbose_name='документы СМК',
        blank=True,
        help_text='Выбор из списка документов СМК. Можно выбрать несколько'
    )

    # 19. Примечание
    note = models.TextField(
        max_length=2000,
        verbose_name='Примечание',
        blank=True,
        null=True,
        help_text='Дополнительная информация'
    )

    class Meta:
        verbose_name = 'Документ СМК'
        verbose_name_plural = 'Документы СМК'
        ordering = ['-date_of_creation']

    def __str__(self):
        return f"{self.document_title} (v{self.version})"

    def save(self, *args, **kwargs):
        """Автоматическая установка полей при сохранении"""
        if not self.pk:  # Если это новый документ
            # Убеждаемся, что номер изменения установлен
            if not self.change_number:
                self.change_number = 'без изм.'
        super().save(*args, **kwargs)

    def is_review_approaching(self):
        """Проверка, приближается ли Дата планового пересмотра (менее 60 дней)"""
        if not self.review_date:
            return False
        from django.utils import timezone
        today = timezone.now().date()
        days_until = (self.review_date - today).days
        return 0 <= days_until <= 60  # Если до 60 дней включительно

    def is_review_overdue(self):
        """Проверка, просрочен ли Дата планового пересмотра"""
        if not self.review_date:
            return False
        from django.utils import timezone
        return self.review_date < timezone.now().date()


class QMSDocumentAcceptSignature(models.Model):
    """
    Модель для множественных подписей ознакомления (ЭЦП)
    """
    document = models.ForeignKey(
        QMSDocument,
        on_delete=models.CASCADE,
        related_name='accept_signatures',
        verbose_name='Документ СМК'
    )

    signature_file = models.FileField(
        upload_to='qms_documents/signatures/accept/%Y/%m/%d/',
        verbose_name='Файл подписи ознакомления',
        validators=[validate_file_size],
        help_text='Файл ЭЦП ознакомления'
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата загрузки'
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Загрузил'
    )

    class Meta:
        verbose_name = 'Подпись ознакомления'
        verbose_name_plural = 'Подписи ознакомления'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Подпись для {self.document.document_title}"


class AdministrativeOrder(models.Model):
    """Модель Приказы"""

    # Предприятие
    ENTERPRISE_CHOICES = [
        ('OOO_SISTEMA', 'ООО "СИСТЕМА"'),
        ('OOO_KOMPLEKS', 'ООО "КОМПЛЕКС"'),
    ]

    # Область применения
    SCOPE_CHOICES = [
        ('main', 'Основная деятельность'),
        ('administrative', 'Административно-хозяйственная деятельность'),
    ]

    # Статус
    STATUS_CHOICES = [
        ('active', 'Действует'),
        ('archived', 'Архив'),
    ]

    # Ознакомление
    ACCEPT_CHOICES = [
        ('---', '---'),
        ('ЭЦП', 'ЭЦП'),
    ]

    # Основные поля
    id = models.AutoField(primary_key=True, verbose_name='Уникальный идентификатор')
    enterprise = models.CharField(
        max_length=20,
        verbose_name='Предприятие',
        choices=ENTERPRISE_CHOICES,
        default='OOO_SISTEMA',
        help_text='Выбор из предопределенного списка'
    )
    registration_number = models.CharField(
        max_length=20,
        verbose_name='Регистрационный номер',
        unique=True,
        blank=True,
        help_text='Формируем порядковый номер в рамках текущего года и индекс предприятия (С или К), (Пример:1-2026/С)'
    )
    order_date = models.DateField(
        verbose_name='Дата приказа',
        help_text='YYYY-MM-DD'
    )
    approval = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='approved_orders',
        verbose_name='Утвердил',
        blank=True,
        null=True,
        help_text='Выбор из списка пользователей'
    )
    signature_approval = models.FileField(
        upload_to='administrative_orders/signatures/approval/%Y/%m/%d/',
        verbose_name='Подпись (загружаемый файл)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Файл ЭЦП утверждения (только один файл)'
    )
    subject = models.CharField(
        max_length=200,
        verbose_name='Тема',
        help_text='Заполняется по данным из текста документа, 200 символов мах'
    )
    accept = models.CharField(
        max_length=10,
        verbose_name='Ознакомление',
        choices=ACCEPT_CHOICES,
        default='---',
        blank=True,
        null=True
    )
    scope = models.CharField(
        max_length=20,
        verbose_name='Область применения',
        choices=SCOPE_CHOICES,
        default='main',
        help_text='Основная деятельность или Административно-хозяйственная деятельность'
    )
    status = models.CharField(
        max_length=10,
        verbose_name='Статус',
        choices=STATUS_CHOICES,
        default='active'
    )
    validity_date = models.DateField(
        verbose_name='Дата планового пересмотра',
        blank=True,
        null=True,
        help_text='Обязательно, если статус "Действует". За 30 дней появится предупреждение'
    )
    note = models.TextField(
        max_length=2000,
        verbose_name='Примечание',
        blank=True,
        null=True
    )

    # Файлы
    uploaded_file = models.FileField(
        upload_to='administrative_orders/documents/%Y/%m/%d/',
        verbose_name='Загружаемый файл',
        validators=[validate_file_size],
        help_text='Основной файл приказа (только один файл)'
    )
    approval_document = models.FileField(
        upload_to='administrative_orders/approval/%Y/%m/',
        verbose_name='Лист утверждения (PDF)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Формируется автоматически при согласовании по маршруту.',
    )
    acquaintance_document = models.FileField(
        upload_to='administrative_orders/acquaintance/%Y/%m/',
        verbose_name='Лист ознакомления (PDF)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Формируется автоматически при ознакомлении по маршруту.',
    )
    app_uploaded_file = models.FileField(
        upload_to='administrative_orders/applications/%Y/%m/%d/',
        verbose_name='Приложение (загружаемый файл / файлы)',
        blank=True,
        null=True,
        validators=[validate_file_size],
        help_text='Файлы приложения'
    )

    # Системные поля
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='authored_orders',
        verbose_name='Создатель (автор)',
        null = True,
        blank = True
    )
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now
    )
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='edited_orders',
        verbose_name='Последний редактор',
        null=True,
        blank=True
    )
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True
    )
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_orders',
        verbose_name='Текущий ответственный',
        null=True,
        blank=True
    )
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1'
    )

    class Meta:
        verbose_name = 'Приказ'
        verbose_name_plural = 'Приказы'
        ordering = ['-order_date']

    def __str__(self):
        return f"{self.registration_number} - {self.subject[:50]}"

    def clean(self):
        """Валидация модели"""
        from django.utils import timezone
        today = timezone.now().date()

        # 1. Дата приказа — только прошедшая дата
        if self.order_date and self.order_date > today:
            raise ValidationError({
                'order_date': 'Дата приказа должна быть строго раньше сегодняшнего дня.'
            })

        # 2. Если статус "Действует", дата пересмотра ОБЯЗАТЕЛЬНА (ЭТА ПРОВЕРКА ВНЕ БЛОКА!)
        if self.status == 'active' and not self.validity_date:
            raise ValidationError({
                'validity_date': 'При статусе "Действует" обязательно указать дату планового пересмотра!'
            })

        # 3. Если дата пересмотра указана — проверяем её
        if self.validity_date:
            if self.validity_date < today:
                raise ValidationError({
                    'validity_date': 'Дата планового пересмотра должна быть строго позже сегодняшнего дня.'
                })

            if self.order_date and self.validity_date <= self.order_date:
                raise ValidationError({
                    'validity_date': 'Дата планового пересмотра должна быть позже даты приказа!'
                })

    def save(self, *args, **kwargs):
        """Автоматическое формирование регистрационного номера"""
        if not self.registration_number:
            from datetime import date
            today = date.today()
            year = today.year

            # Определяем индекс предприятия
            enterprise_index = 'С' if self.enterprise == 'OOO_SISTEMA' else 'К'

            # Получаем последний номер в текущем году
            last_order = AdministrativeOrder.objects.filter(
                registration_number__endswith=f"-{year}/{enterprise_index}"
            ).order_by('-id').first()

            if last_order and last_order.registration_number:
                try:
                    last_num = int(last_order.registration_number.split('-')[0])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1

            self.registration_number = f"{new_num}-{year}/{enterprise_index}"

        super().save(*args, **kwargs)

    def is_validity_approaching(self):
        """Проверка приближения срока пересмотра (30 дней)"""
        if not self.validity_date or self.status != 'active':
            return False
        from django.utils import timezone
        days_until = (self.validity_date - timezone.now().date()).days
        return 0 <= days_until <= 30


class AdministrativeOrderAcceptSignature(models.Model):
    """Множественные подписи ознакомления для приказов"""
    order = models.ForeignKey(
        AdministrativeOrder,
        on_delete=models.CASCADE,
        related_name='accept_signatures',
        verbose_name='Приказ'
    )
    signature_file = models.FileField(
        upload_to='administrative_orders/signatures/accept/%Y/%m/%d/',
        verbose_name='Файл подписи ознакомления',
        validators=[validate_file_size],
        help_text='Файл ЭЦП ознакомления'
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата загрузки'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Загрузил'
    )

    class Meta:
        verbose_name = 'Подпись ознакомления'
        verbose_name_plural = 'Подписи ознакомления (приказы)'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Подпись для {self.order.registration_number}"


class DocumentTemplate(models.Model):
    """Модель Шаблоны документов"""

    id = models.AutoField(primary_key=True, verbose_name='Уникальный идентификатор')
    document_template = models.CharField(
        max_length=100,
        verbose_name='Шаблон документа (наименование)',
        unique=True,
        help_text='Все текстовые символы - 100 символов max'
    )

    # Файлы
    uploaded_file = models.FileField(
        upload_to='templates/documents/%Y/%m/%d/',
        verbose_name='Загружаемый файл шаблона',
        validators=[validate_file_size],
        help_text='Основной файл шаблона (только один файл)'
    )
    #app_uploaded_file = models.FileField(
        #upload_to='templates/applications/%Y/%m/%d/',
        #verbose_name='Шаблон',
        #blank=True,
        #null=True,
        #validators=[validate_file_size],
        #help_text='Файл шаблона'
    #)

    # Дополнительные поля
    validity_date = models.DateField(
        verbose_name='Дата планового пересмотра',
        blank=True,
        null=True,
        help_text='За 30 дней до даты появится предупреждение'
    )
    document_purpose = models.TextField(
        max_length=5000,
        verbose_name='Назначение документа',
        blank=True,
        null=True,
        help_text='Для чего, для кого предназначен документ'
    )
    note = models.TextField(
        max_length=2000,
        verbose_name='Примечание',
        blank=True,
        null=True
    )

    # Системные поля
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='authored_templates',
        verbose_name='Создатель (автор)'
    )
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now
    )
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='edited_templates',
        verbose_name='Последний редактор'
    )
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True
    )
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_templates',
        verbose_name='Текущий ответственный'
    )
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1'
    )

    class Meta:
        verbose_name = 'Шаблон'
        verbose_name_plural = 'Шаблоны'
        ordering = ['-date_of_creation']

    def __str__(self):
        return f"{self.document_template} (v{self.version})"

    def clean(self):
        """Валидация модели"""
        # Проверка даты пересмотра
        if self.validity_date:
            from django.utils import timezone
            today = timezone.now().date()

            # Нельзя ставить прошедшую дату
            if self.validity_date < today:
                raise ValidationError({
                    'validity_date': 'Дата пересмотра не может быть раньше сегодняшнего дня!'
                })

    def is_validity_approaching(self):
        """Проверка приближения срока пересмотра (30 дней)"""
        if not self.validity_date:
            return False
        from django.utils import timezone
        days_until = (self.validity_date - timezone.now().date()).days
        return 0 <= days_until <= 30


class DocumentTemplateAcceptSignature(models.Model):
    """Множественные примеры оформления документа"""
    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.CASCADE,
        related_name='accept_signatures',
        verbose_name='Пример оформления документа'
    )
    signature_file = models.FileField(
        upload_to='templates/signatures/accept/%Y/%m/%d/',
        verbose_name='Пример оформления документа',
        validators=[validate_file_size],
        help_text='Пример оформления документа'
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата загрузки'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Загрузил'
    )

    class Meta:
        verbose_name = 'Пример оформления документа'
        verbose_name_plural = 'Пример оформления документа'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Файлы для {self.template.document_template}"


# Модель для расширения стандартного пользователя Django

class Department(models.Model):
    """Организационный отдел (подразделение) компании.

    Используется как справочник: в профиле сотрудника выбирается из списка,
    а в маршрутах ознакомления можно разослать документ всему отделу разом.
    """
    name = models.CharField('Название отдела', max_length=150, unique=True)
    is_active = models.BooleanField('Активен', default=True)

    class Meta:
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'
        ordering = ('name',)

    def __str__(self):
        return self.name


class EmployeeProfile(models.Model):
    ORG_LEVEL_TOP_MANAGER = 'top_manager'
    ORG_LEVEL_LINE_MANAGER = 'line_manager'
    ORG_LEVEL_EXECUTOR = 'executor'
    ORG_LEVEL_CHOICES = [
        (ORG_LEVEL_TOP_MANAGER, 'Топ-менеджер'),
        (ORG_LEVEL_LINE_MANAGER, 'Линейный менеджер'),
        (ORG_LEVEL_EXECUTOR, 'Исполнитель'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Пользователь'
    )
    patronymic = models.CharField('Отчество', max_length=100, blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    birth_date = models.DateField('Дата рождения', null=True, blank=True)
    avatar = models.ImageField(
        'Фото',
        upload_to='avatars/%Y/%m/',
        null=True,
        blank=True,
        validators=[validate_avatar_size],
    )
    org_department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name='Структурное подразделение (Отдел)',
    )
    org_level = models.CharField(
        'Уровень в структуре организации',
        max_length=20,
        choices=ORG_LEVEL_CHOICES,
        default=ORG_LEVEL_EXECUTOR,
    )
    position = models.CharField('Должность', max_length=100, blank=True)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates',
        verbose_name='Непосредственное подчинение'
    )
    roles_responsibilities = models.TextField('Роли / обязанности', blank=True)

    class Meta:
        verbose_name = 'Профиль сотрудника'
        verbose_name_plural = 'Профили сотрудников'

    def full_name(self):
        """ФИО в порядке Фамилия Имя Отчество, с запасным вариантом — username."""
        parts = [p for p in [self.user.last_name, self.user.first_name, self.patronymic] if p]
        return ' '.join(parts) if parts else self.user.username

    def phones(self):
        return self.contacts.filter(kind=ContactEntry.KIND_PHONE)

    def emails(self):
        return self.contacts.filter(kind=ContactEntry.KIND_EMAIL)

    def __str__(self):
        return f"Профиль: {self.full_name()}"


class ContactEntry(models.Model):
    """Дополнительный телефон или email сотрудника (сверх основных полей профиля)."""
    KIND_PHONE = 'phone'
    KIND_EMAIL = 'email'
    KIND_CHOICES = [
        (KIND_PHONE, 'Телефон'),
        (KIND_EMAIL, 'Email'),
    ]

    profile = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name='contacts',
        verbose_name='Профиль сотрудника',
    )
    kind = models.CharField('Тип', max_length=10, choices=KIND_CHOICES)
    value = models.CharField('Значение', max_length=254)
    note = models.CharField('Примечание', max_length=100, blank=True)

    class Meta:
        verbose_name = 'Доп. контакт сотрудника'
        verbose_name_plural = 'Доп. контакты сотрудников'
        ordering = ['kind', 'id']

    def __str__(self):
        return f"{self.get_kind_display()}: {self.value}"
