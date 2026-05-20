from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

User = get_user_model()


def validate_file_size(value):
    """Ограничение файла 50 МБ"""
    limit = 50 * 1024 * 1024  # 50 MB
    if value.size > limit:
        raise ValidationError('Размер файла не должен превышать 50 МБ')


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
        help_text='Имя пользователя системы (ссылка на User)'
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
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 10. Дата и время создания
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now,
        help_text='Формат: YYYY-MM-DD HH:MI:SS'
    )

    # 11. Последний редактор
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='last_edited_shared_repository',
        verbose_name='Последний редактор',
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 12. Дата и время последнего изменения
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True,
        help_text='Формат: YYYY-MM-DD HH:MI:SS'
    )

    # 13. Текущий ответственный
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_shared_repository',
        verbose_name='Текущий ответственный',
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 14. Версия
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1',
        help_text='Цифры, 3 символа max. Значение по умолчанию: 1'
    )

    # 15. Загружаемый файл
    uploaded_file = models.FileField(
        upload_to='shared_repository/documents/%Y/%m/%d/',
        verbose_name='Загружаемый файл',
        validators=[validate_file_size],
        help_text='Подгружаем только один файл'
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
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 8. Дата и время создания
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now,
        help_text='YYYY-MM-DD HH:MI:SS'
    )

    # 9. Последний редактор
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='edited_knowledge_base',
        verbose_name='Последний редактор',
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 10. Дата и время последнего изменения
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True,
        help_text='YYYY-MM-DD HH:MI:SS'
    )

    # 11. Текущий ответственный
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_knowledge_base',
        verbose_name='Текущий ответственный',
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 12. Версия
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1',
        help_text='Цифры, 3 символа max. Значение по умолчанию: 1'
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
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 10. Дата и время создания
    date_of_creation = models.DateTimeField(
        verbose_name='Дата и время создания',
        default=timezone.now,
        help_text='YYYY-MM-DD HH:MI:SS'
    )

    # 11. Последний редактор
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='edited_qms_documents',
        verbose_name='Последний редактор',
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 12. Дата и время последнего изменения
    date_of_change = models.DateTimeField(
        verbose_name='Дата и время последнего изменения',
        auto_now=True,
        help_text='YYYY-MM-DD HH:MI:SS'
    )

    # 13. Текущий ответственный
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='responsible_qms_documents',
        verbose_name='Текущий ответственный',
        help_text='Имя пользователя системы (ссылка на User)'
    )

    # 14. Версия
    version = models.CharField(
        max_length=3,
        verbose_name='Версия',
        default='1',
        help_text='Цифры, 3 символа max. Значение по умолчанию: 1'
    )

    # 15. Загружаемый файл (основной документ)
    uploaded_file = models.FileField(
        upload_to='qms_documents/documents/%Y/%m/%d/',
        verbose_name='Загружаемый файл',
        validators=[validate_file_size],
        help_text='Основной файл документа (только один файл)'
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
        help_text='YYYY-MM-DD. За 60 дней до этой даты появится предупреждение'
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

class PSIDocument(models.Model):
    # --- Основная информация ---
    serial_number = models.CharField("Заводской номер", max_length=100, default='2000002026')
    test_date = models.DateField("Дата испытания / изготовления")
    model_name = models.CharField("Модель", max_length=200, default='ИБП СПМ 1.2000-3U')
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
    visual_check = models.CharField("Проверка соответствия КД и внешнего вида (5.3)",
                                    max_length=20, choices=STATUS_CHOICES, default='соответствует')
    marking_check = models.CharField("Проверка содержания маркировки",
                                     max_length=20, choices=STATUS_CHOICES, default='соответствует')
    insulation_res = models.CharField("Проверка электрического сопротивления изоляции (5.7)",
                                      max_length=20, choices=ELECTRO_CHOICES, default='соответствует')
    insulation_strength = models.CharField("Проверка электрической прочности изоляции (5.8)",
                                           max_length=20, choices=STATUS_CHOICES, default='соответствует')

    # --- Проверка функционирования (5.6) ---
    func_power_on = models.CharField("5.6.1 Проверка включения", choices=STATUS_CHOICES)
    func_display = models.CharField("5.6.2 Проверка индикации", choices=STATUS_CHOICES)
    func_navigation = models.CharField("5.6.3 Проверка навигации по страницам", choices=STATUS_CHOICES)
    func_battery_mode = models.CharField("5.6.4 Проверка работы в автономном режиме", choices=STATUS_CHOICES)
    func_bypass = models.CharField("5.6.5 Проверка режима «байпас»", choices=STATUS_CHOICES)
    func_audio = models.CharField("5.6.6 Проверка отключения звукового сигнала", choices=STATUS_CHOICES)
    func_settings = models.CharField("5.6.7 Проверка режима настроек", choices=STATUS_CHOICES)
    func_terminal = models.CharField("5.6.8 Проверка обмена данными с терминалом", choices=STATUS_CHOICES)

    # --- Заключение ---
    completeness = models.CharField("Проверка комплектности", max_length=200)
    conclusion = models.TextField("Заключение", choices=SHIPMENT_CHOICES, default="Устройство признано годным к эксплуатации")
    comment = models.TextField("Комментарий", blank=True)

    # --- Условия испытаний (Метеоусловия) ---
    inspector = models.CharField("Испытатель / ОТК", max_length=150)
    workshop = models.CharField("Цех", max_length=100, default="№1018")
    temperature = models.CharField("Температура", choices=TEMPERATURE_CHOICES, max_length=50, default="+22°C")
    humidity = models.CharField("Влажность", choices=HUMIDITY_CHOICES, max_length=50, default="45%")
    pressure = models.CharField("Давление", choices=PRESSURE_CHOICES, max_length=50, default="750 мм рт. ст.")
    remark = models.TextField("Комментарий", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Протокол ПСИ"
        verbose_name_plural = "Протоколы ПСИ"

    def __str__(self):
        return f"Протокол {self.serial_number} ({self.model_name})"

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