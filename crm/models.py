import re
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


def validate_file_size(value):
    """Ограничение файла 20 МБ"""
    limit = 20 * 1024 * 1024
    if value.size > limit:
        raise ValidationError('Размер одного файла не должен превышать 20 МБ')


def validate_customer_inn(value):
    if value in (None, ""):
        return
    s = str(value).strip()
    if not s:
        return
    if not re.fullmatch(r"\d{1,12}", s):
        raise ValidationError(
            "В поле ИНН допускаются только цифры, не более 12."
        )


def _next_registration_dated_prefix_monthly_suffix(
    model_cls, ref_date, kind: str, exclude_pk=None
) -> str:
    prefix = f"{kind}-{ref_date:%y-%m}-"
    qs = model_cls.objects.filter(registration_number__startswith=prefix).exclude(
        registration_number=""
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    max_n = 0
    plen = len(prefix)
    for rn in qs.values_list("registration_number", flat=True):
        if not rn or len(rn) <= plen:
            continue
        tail = rn[plen:]
        try:
            max_n = max(max_n, int(tail))
        except ValueError:
            continue
    num = max_n + 1
    return f"{prefix}{num:02d}"


class Notifications(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Автор')
    title = models.CharField(max_length=200, blank=True, null=True, verbose_name='Заголовок')
    text = models.TextField(blank=True, null=True, verbose_name='Текст')
    created_date = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name='Дата создания')
    published_date = models.DateTimeField(blank=True, null=True, verbose_name='Дата публикации')

    def publish(self):
        self.published_date = timezone.now()
        self.save()

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_date']


class Customer(models.Model):
    name_of_company = models.CharField(max_length=255, verbose_name='Название компании', default='Без названия')
    iin = models.CharField(
        max_length=12,
        blank=True,
        null=True,
        verbose_name='ИНН',
        validators=[validate_customer_inn],
    )
    revenue_for_last_year = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Выручка за последний год', help_text='Миллиард рублей')
    length_of_electrical_network_km = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, verbose_name='Длина сетей, км')
    quantity_of_technical_transformer_pcs = models.PositiveIntegerField(blank=True, null=True, verbose_name='Количество ТП, шт')
    address = models.TextField(blank=True, null=True, verbose_name='Адрес')
    name_of_company_ci = models.CharField(
        max_length=255, editable=False, db_index=True, default=""
    )

    def save(self, *args, **kwargs):
        if self.iin is not None:
            self.iin = str(self.iin).strip() or None
        # Unicode case folding — лучше, чем .lower() для всех языков
        self.name_of_company_ci = (self.name_of_company or "").casefold()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        inn = self.iin
        if not inn:
            return
        qs = Customer.objects.filter(iin=inn)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                {
                    "iin": "Контрагент с таким ИНН уже есть. Укажите другой ИНН или откройте существующую карточку.",
                }
            )

    def __str__(self):
        return self.name_of_company

    class Meta:
        verbose_name = 'Контрагент'
        verbose_name_plural = 'Контрагенты'
        ordering = ['name_of_company']

    def support_tickets_link(self):
        """Возвращает ссылку на обращения контрагента для отображения в админке"""
        if hasattr(self, 'support_tickets'):
            return self.support_tickets.count()
        return 0

    support_tickets_link.short_description = 'Обращения'

class Decision_maker(models.Model):
    class TypeOfFunction(models.IntegerChoices):
        DIRECTOR = 0, 'директор'
        CHIEF_ENGINEER = 1, 'главный инженер'
        TECHNICAL_SPECIALIST = 2, 'технический специалист'
        OWNER = 3, 'собственник'

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE,  blank=True, null=True,related_name='decision_makers', verbose_name='Контрагент')
    full_name = models.CharField(max_length=255, verbose_name='ФИО')
    city_of_location = models.CharField(max_length=100, blank=True, null=True,verbose_name='Город местонахождения')
    function = models.IntegerField(choices=TypeOfFunction.choices, default=TypeOfFunction.DIRECTOR, blank=True, null=True, verbose_name='Роль')
    phone_number = models.CharField(max_length=20, blank=True, null=True, verbose_name='Телефон')
    extension = models.CharField(max_length=10, blank=True, null=True, verbose_name='Добавочный номер')
    email = models.EmailField(max_length=54, blank=True, null=True, verbose_name='Почта')
    telegram = models.CharField(max_length=50, blank=True, null=True, verbose_name='Телеграм')
    description_and_impression = models.TextField(blank=True, null=True, verbose_name='Описание и впечатления')

    def __str__(self):
        ext = f" доб.{self.extension}" if self.extension else ""
        return f"{self.full_name} ({self.customer}) {self.phone_number}{ext}"

    class Meta:
        verbose_name = 'ЛПР'
        verbose_name_plural = 'ЛПР'
        ordering = ['full_name', 'customer']


class Product(models.Model):
    name_of_product = models.CharField(max_length=255, verbose_name='Название')
    end_customer_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Цена для конечного заказчика')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')

    def __str__(self):
        return self.name_of_product

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Продукты'
        ordering = ['name_of_product']


class Deal(models.Model):
    SELECTION = [
        ('подготовлен_звонок', 'Подготовлен звонок'),
        ('сделан_звонок', 'Сделан звонок'),
        ('назначена_встреча', 'Назначена встреча'),
        ('прошла_встреча', 'Прошла встреча'),
        ('достигнута_договоренность', 'Достигнута договоренность'),
        ('готовится_договор', 'Готовится договор'),
        ('заключен_договор', 'Заключен договор'),
        ('исполнена_поставка', 'Исполнена поставка'),
        ('выполнен_монтаж', 'Выполнен монтаж'),
        ('идет_гарантийный_срок', 'Идет гарантийный срок'),
        ('послегарантийная_работа', 'Послегарантийная работа'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='сделки', blank=True, null=True, verbose_name='Контрагент')
    start_date = models.DateField(blank=True, null=True, verbose_name='Дата начала')
    date_of_last_change = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name='Дата последнего изменения')
    date_of_next_activity = models.DateField(blank=True, null=True, verbose_name='Дата следующей активности')
    status = models.CharField(max_length=50, choices=SELECTION, blank=True, null=True, verbose_name='Состояние')
    post = models.ForeignKey(
        'blog.Post',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Разработка (модификация/проект)',
        related_name='deals',
    )
    deal_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name='Сумма сделки')
    quantity_of_all_product = models.PositiveIntegerField(default=1, blank=True, null=True, verbose_name='Количество всех продуктов, шт')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')
    shipping_address = models.TextField(verbose_name='Адрес отгрузки', blank=True, null=True)
    responsible_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Ответственный менеджер')

    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deal_author', verbose_name='Автор',
    )
    last_editor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deal_last_editor', verbose_name='Последний редактор',
    )
    date_of_creation = models.DateTimeField('Дата и время создания', default=timezone.now)

    def __str__(self):
        return f"Сделка #{self.id} - {self.customer.name_of_company}"

    class Meta:
        verbose_name = 'Сделка'
        verbose_name_plural = 'Сделки'
        ordering = ['-start_date']


class Deal_stage(models.Model):
    SELECTION = Deal.SELECTION  # Используем те же варианты, что и для Сделки

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='этапы_сделки', blank=True, null=True, verbose_name='Сделка')
    start_date_step = models.DateField(blank=True, null=True, verbose_name='Дата начала этапа')
    end_date_step = models.DateField(blank=True, null=True, verbose_name='Дата конца этапа')
    status = models.CharField(max_length=50, choices=SELECTION, blank=True, null=True, verbose_name='Состояние')
    description_of_task_at_stage = models.TextField(blank=True, null=True, verbose_name='Описание задач на этап')
    description_of_what_has_been_achieved_at_a_stage = models.TextField(blank=True, null=True, verbose_name='Описание достигнутого на этапе')
    description_of_tasks_for_our_specialists = models.TextField(blank=True, null=True, verbose_name='Описание задач для наших специалистов')
    our_specialists_involved = models.ManyToManyField(User, related_name='этапы_сделки', blank=True, default=0, verbose_name='Привлекаемые наши специалисты')

    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deal_stage_author', verbose_name='Автор',
    )
    current_responsible = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deal_stage_responsible', verbose_name='Текущий ответственный',
    )
    last_editor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deal_stage_last_editor', verbose_name='Последний редактор',
    )
    date_of_creation = models.DateTimeField('Дата и время создания', default=timezone.now)
    date_of_change = models.DateTimeField('Дата и время последнего изменения', auto_now=True)

    def __str__(self):
        return f"Этап {self.get_status_display()} для сделки #{self.deal.id}"

    class Meta:
        verbose_name = 'Этап сделки'
        verbose_name_plural = 'Этапы сделки'
        ordering = ['start_date_step']

class Call(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Контрагент')
    decision_maker = models.ForeignKey(Decision_maker, on_delete=models.CASCADE, blank=True, null=True, verbose_name='ЛПР')
    responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Ответственный')
    planned_date = models.DateField(blank=True, null=True, verbose_name='Плановая дата')
    call_goal = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Описание цели звонка')
    call_result = models.TextField(max_length=2000, blank=True, null=True, verbose_name='Описание результата')
    deal = models.ForeignKey(Deal, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Сделка (если есть)')

    def __str__(self):
        return f"Звонок по {self.customer.name_of_company} от {self.planned_date}"

    class Meta:
        verbose_name = 'Звонок'
        verbose_name_plural = 'Звонки'
        ordering = ['-planned_date']


RECEIPT_METHOD_CHOICES = [
    ('registered_mail', 'Эл. почта'),
    ('courier', 'Курьерская доставка'),
    ('mail', 'Почта'),
    ('personal', 'Личная передача'),
    ('portal', 'Портал Госуслуг'),
    ('', '---'),
]

SEND_METHOD_CHOICES = [
    ('email', 'Эл. почта'),
    ('fax', 'Факс-документ'),
    ('personal', 'Личная передача'),
    ('mail', 'Почта'),
    ('express', 'Курьер-документ'),
    ('', '---'),
]

RECEIPT_VERIFICATION_CHOICES = [
    ("auto_email", "Автоподтверждение в почте"),
    ("call", "Подтверждено звонком"),
    ("message", "Подтверждено сообщением"),
    ("", "—"),
]


class IncomingLetter(models.Model):
    """Входящее письмо."""
    registration_number = models.CharField(
        'Внутренний регистрационный номер',
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
    )
    registration_number_reassigned = models.BooleanField(
        'Номер пересчитан после смены даты получения',
        default=False,
        editable=False,
    )
    sender_identification = models.CharField(
        'Исходящий номер отправителя',
        max_length=50,
        unique=True,
    )
    sender = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='incoming_letters',
        verbose_name='Отправитель (название организации)',
    )
    sender_signature = models.ForeignKey(
        Decision_maker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_letters_signed',
        verbose_name='Подписант (должность, ФИО)',
    )
    letter_date = models.DateField('Дата письма')
    date_of_receipt = models.DateTimeField('Дата получения')
    urgent = models.BooleanField('Срочно', default=False)
    receipt_method = models.CharField(
        'Способ получения',
        max_length=20,
        choices=RECEIPT_METHOD_CHOICES,
        default='registered_mail',
        blank=True,
    )
    subject = models.CharField('Тема', max_length=200)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='incoming_letter_author',
        verbose_name='Создатель (автор)',
    )
    date_of_creation = models.DateTimeField('Дата и время создания', default=timezone.now)
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='incoming_letter_last_editor',
        verbose_name='Последний редактор',
    )
    date_of_change = models.DateTimeField('Дата и время последнего изменения', auto_now=True)
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='incoming_letter_responsible',
        verbose_name='Текущий ответственный',
    )
    version = models.CharField('Версия', max_length=3, default='1', blank=True)
    document_uploaded_file = models.FileField(
        'Документ (загружаемый файл)',
        upload_to='crm/incoming_letters/%Y/%m/',
        blank=True,
        null=True,
        validators=[validate_file_size],
    )
    comment = models.CharField('Комментарий', max_length=1000, blank=True)

    class Meta:
        verbose_name = 'Входящее письмо'
        verbose_name_plural = 'Письма — Входящие'
        ordering = ['-date_of_receipt']

    def save(self, *args, **kwargs):
        if not self.registration_number:
            ref_date = self.date_of_receipt.date() if self.date_of_receipt else timezone.localdate()
            self.registration_number = _next_registration_dated_prefix_monthly_suffix(
                IncomingLetter, ref_date, "ВХ", exclude_pk=self.pk
            )
        super().save(*args, **kwargs)

    def __str__(self):
        sender_number = self.sender_identification or "—"
        internal_number = self.registration_number or "—"
        return f"{sender_number} · {internal_number} · {self.sender}"


class OutgoingLetter(models.Model):
    """Исходящее письмо."""
    registration_number = models.CharField(
        'Регистрационный номер',
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
    )
    registration_number_reassigned = models.BooleanField(
        'Номер пересчитан после смены даты письма',
        default=False,
        editable=False,
    )
    recipient = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='outgoing_letters',
        verbose_name='Получатель (название организации)',
    )
    person_recipient = models.ForeignKey(
        Decision_maker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='outgoing_letters_addressed',
        verbose_name='Кому адресовано (должность, ФИО)',
    )
    letter_date = models.DateField('Дата письма')
    date_of_send = models.DateTimeField('Дата отправки', null=True, blank=True)
    urgent = models.BooleanField('Срочно', default=False)
    subject = models.CharField('Тема', max_length=200)
    sender_identification = models.CharField(
        'Идентификация отправителя (на бланке)',
        max_length=50,
        blank=True,
    )
    reply_to = models.ForeignKey(
        "IncomingLetter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name="Ответ на № (исх. номер отправителя)",
    )
    sender_signature = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='outgoing_letter_signed',
        verbose_name='Подписант (должность, ФИО)',
        default=1,
    )
    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='outgoing_letter_executor',
        verbose_name='Исполнитель',
        default=1,
    )
    send_method = models.CharField(
        'Способ отправки',
        max_length=20,
        choices=SEND_METHOD_CHOICES,
        default='email',
        blank=True,
    )
    receipt_verification = models.CharField(
        "Отметка о получении",
        max_length=20,
        choices=RECEIPT_VERIFICATION_CHOICES,
        blank=True,
        default="",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='outgoing_letter_author',
        verbose_name='Создатель (автор)',
    )
    date_of_creation = models.DateTimeField('Дата и время создания', default=timezone.now)
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='outgoing_letter_last_editor',
        verbose_name='Последний редактор',
    )
    date_of_change = models.DateTimeField('Дата и время последнего изменения', auto_now=True)
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='outgoing_letter_responsible',
        verbose_name='Текущий ответственный',
    )
    version = models.CharField('Версия', max_length=3, default='1', blank=True)
    document_uploaded_file = models.FileField(
        'Письмо (загружаемый файл)',
        upload_to='crm/outgoing_letters/%Y/%m/',
        blank=True,
        null=True,
        validators=[validate_file_size],
    )
    app_uploaded_file = models.FileField(
        'Приложение (загружаемый файл)',
        upload_to='crm/outgoing_letters_app/%Y/%m/',
        blank=True,
        null=True,
        validators=[validate_file_size],
    )
    comment = models.CharField('Комментарий', max_length=1000, blank=True)

    class Meta:
        verbose_name = 'Исходящее письмо'
        verbose_name_plural = 'Письма — Исходящие'
        ordering = ['-letter_date', '-date_of_send']

    def save(self, *args, **kwargs):
        if not self.registration_number:
            ref_date = self.letter_date if self.letter_date else timezone.localdate()
            self.registration_number = _next_registration_dated_prefix_monthly_suffix(
                OutgoingLetter, ref_date, "ИСХ", exclude_pk=self.pk
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.registration_number or '—'} — {self.recipient}"


class Company_branch(models.Model):
    name_of_company = models.CharField(max_length=255, verbose_name='Название компании', null=False, blank=False, default='Без названия')
    revenue_for_last_year = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True,verbose_name='Выручка за последний год', help_text='Миллиард рублей')
    length_of_electrical_network_km = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, verbose_name='Длина сетей, км')
    quantity_of_technical_transformer_pcs = models.PositiveIntegerField(blank=True, null=True, verbose_name='Количество ТП, шт')
    address = models.TextField(blank=True, null=True, verbose_name='Адрес')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='branches', blank=True, null=True, verbose_name='Родительский контрагент')

    def __str__(self):
        return self.name_of_company

    class Meta:
        verbose_name = 'Филиал'
        verbose_name_plural = 'Филиал'
        ordering = ['name_of_company']


class Meeting(models.Model):
    class MeetingStatus(models.TextChoices):
        TO_ASSIGN = 'назначить', 'Назначить'
        ASSIGNED = 'назначена', 'Назначена'
        HELD = 'проведена', 'Проведена'
        CANCELED = 'отменена', 'Отменена'

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name='Контрагент', null=True, blank=True)
    decision_maker = models.ForeignKey(
        Decision_maker, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='ЛПР'
    )
    responsible_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                         verbose_name='Ответственный')

    # Разделяем на дату и время
    meeting_date = models.DateField(verbose_name='Дата встречи', blank=True, null=True)
    meeting_time = models.TimeField(verbose_name='Время встречи', blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=MeetingStatus.choices,
        default=MeetingStatus.TO_ASSIGN,
        verbose_name='Статус'
    )
    goal_description = models.TextField(max_length=3500, verbose_name='Описание цели', blank=True, null=True)
    result_description = models.TextField(max_length=3500, verbose_name='Описание результата', blank=True, null=True)

    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='meeting_author', verbose_name='Автор',
    )
    last_editor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='meeting_last_editor', verbose_name='Последний редактор',
    )
    date_of_creation = models.DateTimeField('Дата и время создания', default=timezone.now)
    date_of_change = models.DateTimeField('Дата и время последнего изменения', auto_now=True)

    def save(self, *args, **kwargs):
        # Автоподстановка ЛПР по контрагенту
        if self.customer and not self.decision_maker:
            self.decision_maker = getattr(self.customer, 'decision_maker', None)
        super().save(*args, **kwargs)

    def __str__(self):
        customer_name = str(self.customer) if self.customer else "Неизвестный контрагент"

        if self.meeting_date and self.meeting_time:
            date_time_str = f"{self.meeting_date:%d.%m.%Y} {self.meeting_time}"
        elif self.meeting_date:
            date_time_str = f"{self.meeting_date:%d.%m.%Y}"
        else:
            date_time_str = "дата не указана"

        return f"Встреча с {customer_name} ({date_time_str})"

    class Meta:
        verbose_name = 'Встреча'
        verbose_name_plural = 'Встречи'
        ordering = ['meeting_date', 'meeting_time']


class MeetingFile(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='files', verbose_name='Встреча')
    file = models.FileField(
        upload_to='meeting_files/%Y/%m/%d/',
        verbose_name='Файл',
        validators=[validate_file_size]  # Используем существующий валидатор
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name='Описание файла')

    def __str__(self):
        return f"Файл {self.file.name} для встречи #{self.meeting.id}"

    class Meta:
        verbose_name = 'Файл встречи'
        verbose_name_plural = 'Файлы встречи'
        ordering = ['-uploaded_at']


def default_intake_date():
    return timezone.localdate()


# Обращения техподдержки
class SupportTicket(models.Model):
    STATUS_NEW = 'new'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_WAITING = 'waiting'
    STATUS_RESOLVED = 'resolved'

    STATUS_CHOICES = [
        (STATUS_NEW, 'Новое'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_WAITING, 'Ожидает ответа заказчика'),
        (STATUS_RESOLVED, 'Решена/Закрыта'),
    ]

    CATEGORY_QUESTION_CONSULT = 'question_consult'
    CATEGORY_ERROR_PROBLEM = 'error_problem'
    CATEGORY_IMPROVEMENT = 'improvement'

    CATEGORY_CHOICES = [
        (CATEGORY_QUESTION_CONSULT, 'Вопрос/Консультация'),
        (CATEGORY_ERROR_PROBLEM, 'Ошибка/Проблема'),
        (CATEGORY_IMPROVEMENT, 'Запрос на улучшение'),
    ]

    INTAKE_MESSENGER = 'messenger'
    INTAKE_EMAIL = 'email'
    INTAKE_MAIL = 'mail'
    INTAKE_MANAGEMENT = 'management'
    INTAKE_PHONE_SUPPORT = 'phone_support'
    INTAKE_PHONE = 'phone'
    INTAKE_IN_PERSON = 'in_person'
    INTAKE_OTHER = 'other'

    INTAKE_CHANNEL_CHOICES = [
        (INTAKE_MESSENGER, 'Мессенджер'),
        (INTAKE_EMAIL, 'Электронная почта'),
        (INTAKE_MAIL, 'Почта (бумажное письмо)'),
        (INTAKE_MANAGEMENT, 'Руководство'),
        (INTAKE_PHONE_SUPPORT, 'Телефон тех. поддержки'),
        (INTAKE_PHONE, 'Телефон (прочее)'),
        (INTAKE_IN_PERSON, 'Личное обращение'),
        (INTAKE_OTHER, 'Прочее'),
    ]

    CLAIM_VERBAL = 'verbal'
    CLAIM_OFFICIAL = 'official'

    CLAIM_TYPE_CHOICES = [
        ('', '—'),
        (CLAIM_VERBAL, 'Устная'),
        (CLAIM_OFFICIAL, 'Официальная'),
    ]

    created_date = models.DateField(
        default=default_intake_date,
        verbose_name='Дата поступления',
    )
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        verbose_name='Контрагент',
        related_name='support_tickets',
    )
    post = models.ForeignKey(
        'blog.Post',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Разработка (модификация/проект)',
        related_name='support_tickets',
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        verbose_name='Категория',
        default=CATEGORY_QUESTION_CONSULT,
    )
    problem = models.TextField(verbose_name='Проблема')
    description = models.TextField(verbose_name='Описание (ход решения)', blank=True)
    intake_channel = models.CharField(
        max_length=20,
        choices=INTAKE_CHANNEL_CHOICES,
        verbose_name='Как поступило',
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        verbose_name='Статус',
    )
    resolution = models.TextField(
        verbose_name='Решение проблемы / причины её возникновения',
        blank=True,
    )
    claim_type = models.CharField(
        max_length=10,
        choices=CLAIM_TYPE_CHOICES,
        blank=True,
        default='',
        verbose_name='Претензия',
    )
    claim_letter = models.ForeignKey(
        'IncomingLetter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Письмо / рекламация (претензия)',
        related_name='support_tickets',
    )
    status_changed_date = models.DateTimeField(auto_now=True, verbose_name='Дата изменения статуса')

    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tickets',
        verbose_name='Автор',
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
        verbose_name='Текущий ответственный',
    )

    def clean(self):
        super().clean()
        if self.status == self.STATUS_RESOLVED and not (self.resolution or '').strip():
            raise ValidationError({
                'resolution': 'Заполните решение проблемы при статусе «Решена/Закрыта».',
            })
        if self.claim_type == self.CLAIM_OFFICIAL and not self.claim_letter:
            raise ValidationError({
                'claim_letter': 'Для официальной претензии приложите письмо или рекламацию.',
            })

    def save(self, *args, **kwargs):
        if self.pk:
            original = SupportTicket.objects.get(pk=self.pk)
            if original.status != self.status:
                self.status_changed_date = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Обращение #{self.id} - {self.problem[:80]}"

    class Meta:
        verbose_name = 'Обращение'
        verbose_name_plural = 'Обращения'
        ordering = ['-created_date', '-pk']


# Комментарии к заявкам
class TicketComment(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='comments', verbose_name='Обращение')
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Автор')
    text = models.TextField(verbose_name='Комментарий')
    created_date = models.DateTimeField(default=timezone.now, verbose_name='Дата создания')
    file = models.FileField(upload_to='ticket_comments/%Y/%m/%d/', blank=True, null=True,
                            verbose_name='Файл', validators=[validate_file_size])

    def __str__(self):
        return f"Комментарий к #{self.ticket.id} от {self.author.username}"

    class Meta:
        verbose_name = 'Запись взаимодействия'
        verbose_name_plural = 'Взаимодействие по обработке обращений'
        ordering = ['created_date']

