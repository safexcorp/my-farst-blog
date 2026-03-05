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