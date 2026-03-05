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
    iin = models.CharField(max_length=12, blank=True, null=True, verbose_name='ИНН')
    revenue_for_last_year = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name='Выручка за последний год', help_text='Миллиард рублей')
    length_of_electrical_network_km = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, verbose_name='Длина сетей, км')
    quantity_of_technical_transformer_pcs = models.PositiveIntegerField(blank=True, null=True, verbose_name='Количество ТП, шт')
    address = models.TextField(blank=True, null=True, verbose_name='Адрес')
    name_of_company_ci = models.CharField(
        max_length=255, editable=False, db_index=True, default=""
    )

    def save(self, *args, **kwargs):
        # Unicode case folding — лучше, чем .lower() для всех языков
        self.name_of_company_ci = (self.name_of_company or "").casefold()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name_of_company

    class Meta:
        verbose_name = 'Заказчик'
        verbose_name_plural = 'Заказчики'
        ordering = ['name_of_company']


class Decision_maker(models.Model):
    class TypeOfFunction(models.IntegerChoices):
        DIRECTOR = 0, 'директор'
        CHIEF_ENGINEER = 1, 'главный инженер'
        TECHNICAL_SPECIALIST = 2, 'технический специалист'
        OWNER = 3, 'собственник'

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE,  blank=True, null=True,related_name='decision_makers', verbose_name='Заказчик')
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

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='сделки', blank=True, null=True, verbose_name='Заказчик')
    start_date = models.DateField(blank=True, null=True, verbose_name='Дата начала')
    date_of_last_change = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name='Дата последнего изменения')
    date_of_next_activity = models.DateField(blank=True, null=True, verbose_name='Дата следующей активности')
    status = models.CharField(max_length=50, choices=SELECTION, blank=True, null=True, verbose_name='Состояние')
    name_of_product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Продукт')
    deal_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name='Сумма сделки')
    quantity_of_all_product = models.PositiveIntegerField(default=1, blank=True, null=True, verbose_name='Количество всех продуктов, шт')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')
    shipping_address = models.TextField(verbose_name='Адрес отгрузки', blank=True, null=True)
    responsible_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Ответственный менеджер')

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

    def __str__(self):
        return f"Этап {self.get_status_display()} для сделки #{self.deal.id}"

    class Meta:
        verbose_name = 'Этап сделки'
        verbose_name_plural = 'Этапы сделки'
        ordering = ['start_date_step']

class Call(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Заказчик')
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


class Letter(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Заказчик')
    decision_maker = models.ForeignKey(Decision_maker, on_delete=models.CASCADE, blank=True, null=True, verbose_name='ЛПР')
    responsible = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Ответственный')
    planned_date = models.DateField(blank=True, null=True, verbose_name='Плановая дата')
    letter_file = models.FileField(upload_to='letters/', blank=True, null=True, verbose_name='Тело письма')
    incoming_number = models.CharField(max_length=50, blank=True, null=True, verbose_name='Входящий номер заказчика')
    incoming_date = models.DateField(blank=True, null=True, verbose_name='Входящая дата заказчика')
    responsible_person_from_customer = models.CharField(max_length=100, blank=True, null=True, verbose_name='Ответственный от заказчика')
    deal = models.ForeignKey(Deal, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Сделка')

    def __str__(self):
        return f"Письмо №{self.incoming_number} от {self.customer.name_of_company}"

    class Meta:
        verbose_name = 'Письмо'
        verbose_name_plural = 'Письма'
        ordering = ['-planned_date']


class Company_branch(models.Model):
    name_of_company = models.CharField(max_length=255, verbose_name='Название компании', null=False, blank=False, default='Без названия')
    revenue_for_last_year = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True,verbose_name='Выручка за последний год', help_text='Миллиард рублей')
    length_of_electrical_network_km = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, verbose_name='Длина сетей, км')
    quantity_of_technical_transformer_pcs = models.PositiveIntegerField(blank=True, null=True, verbose_name='Количество ТП, шт')
    address = models.TextField(blank=True, null=True, verbose_name='Адрес')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='branches', blank=True, null=True, verbose_name='Родительский заказчик')

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

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name='Заказчик', null=True, blank=True)
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

    def save(self, *args, **kwargs):
        # Автоподстановка ЛПР по заказчику
        if self.customer and not self.decision_maker:
            self.decision_maker = getattr(self.customer, 'decision_maker', None)
        super().save(*args, **kwargs)

    def __str__(self):
        customer_name = str(self.customer) if self.customer else "Неизвестный заказчик"

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


# Обращения техподдержки
class SupportTicket(models.Model):
    STATUS_NEW = 'new'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_WAITING = 'waiting'
    STATUS_RESOLVED = 'resolved'

    STATUS_CHOICES = [
        (STATUS_NEW, 'Новая'),
        (STATUS_IN_PROGRESS, 'В работе'),
        (STATUS_WAITING, 'Ожидает ответа заказчика'),
        (STATUS_RESOLVED, 'Решена/Закрыта'),
    ]

    CATEGORY_CHOICES = [
        ('question', 'Вопрос'),
        ('error', 'Ошибка'),
        ('consultation', 'Консультация'),
        ('improvement', 'Запрос на улучшение'),
    ]

    # Основные поля
    created_date = models.DateTimeField(default=timezone.now, verbose_name='Дата поступления')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, verbose_name='Заказчик')
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Продукт')


    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        verbose_name='Категория',
        default='question'
    )

    problem = models.CharField(max_length=200, verbose_name='Проблема')
    description = models.TextField(verbose_name='Описание (ход решения)', blank=True)

    # Статус и даты
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, verbose_name='Статус')
    status_changed_date = models.DateTimeField(auto_now=True, verbose_name='Дата изменения статуса')

    # Пользователи
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   related_name='created_tickets', verbose_name='Создал')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='assigned_tickets', verbose_name='Назначенный агент')

    def save(self, *args, **kwargs):
        """Автоматическое обновление даты изменения статуса"""
        if self.pk:
            original = SupportTicket.objects.get(pk=self.pk)
            if original.status != self.status:
                self.status_changed_date = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Обращение #{self.id} - {self.problem}"

    class Meta:
        verbose_name = 'Обращение'
        verbose_name_plural = 'Обращения'
        ordering = ['-created_date']


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
        verbose_name = 'Комментарий обращения'
        verbose_name_plural = 'Комментарии обращений'
        ordering = ['created_date']

