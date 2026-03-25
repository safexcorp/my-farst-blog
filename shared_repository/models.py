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
        verbose_name='Категория (код вида документа)',
        choices=CATEGORY_CHOICES,
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

    # 8. Подпись ознакомления
    #signature_accept = models.FileField(
     #   upload_to='shared_repository/signatures/accept/%Y/%m/%d/',
      #  verbose_name='Подпись ознакомления',
       # blank=True,
        #null=True,
        #validators=[validate_file_size],
        #help_text='Файл ЭЦП'
    #)

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
    related_documents = models.TextField(
        max_length=1000,
        verbose_name='Связанные документы',
        blank=True,
        null=True,
        help_text='Документы и/или гиперссылки, на которые ссылается данный документ'
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