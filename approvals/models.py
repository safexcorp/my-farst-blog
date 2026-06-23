from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# Роли подписи —
SIGNATURE_ROLE_CHOICES = [
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


class Department(models.Model):
    name = models.CharField("Название роли", max_length=150, unique=True)
    code = models.CharField("Код", max_length=20, blank=True)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Роль"
        verbose_name_plural = "Роли"
        ordering = ("name",)

    def __str__(self):
        return self.name


class DepartmentMember(models.Model):
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE,
        related_name="members", verbose_name="Роль",
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="department_memberships", verbose_name="Сотрудник",
    )
    is_main = models.BooleanField("Главный (ответственный)", default=False)
    order = models.PositiveSmallIntegerField(
        "Очередь замещения", default=1,
        help_text="0 — главный; 1, 2, … — заместители по порядку вступления.",
    )

    class Meta:
        verbose_name = "Сотрудник роли"
        verbose_name_plural = "Сотрудники ролей"
        unique_together = ("department", "user")
        ordering = ("department", "-is_main", "order")

    def __str__(self):
        member = "главный" if self.is_main else f"зам. №{self.order}"
        return f"{self.user} — {self.department} ({member})"


class Vacation(models.Model):
    TYPE_VACATION = "vacation"
    TYPE_SICK = "sick"
    TYPE_UNPAID = "unpaid"
    TYPE_BUSINESS_TRIP = "trip"
    TYPE_DAY_OFF = "day_off"
    TYPE_STUDY = "study"
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_VACATION, "Отпуск (ежегодный)"),
        (TYPE_UNPAID, "Отпуск без сохранения (БС)"),
        (TYPE_SICK, "Больничный"),
        (TYPE_BUSINESS_TRIP, "Командировка"),
        (TYPE_DAY_OFF, "Отгул"),
        (TYPE_STUDY, "Учебный отпуск"),
        (TYPE_OTHER, "Другое"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="vacations", verbose_name="Сотрудник",
    )
    absence_type = models.CharField(
        "Тип отсутствия", max_length=20,
        choices=TYPE_CHOICES, default=TYPE_VACATION,
    )
    start_date = models.DateField("С")
    end_date = models.DateField("По")
    reason = models.CharField(
        "Причина / комментарий", max_length=255, blank=True,
        help_text="Обязательно для типа «Другое». Для остальных типов — по желанию.",
    )

    class Meta:
        verbose_name = "Отпуск / отсутствие"
        verbose_name_plural = "Отпуска / отсутствия"
        ordering = ("-start_date",)

    def __str__(self):
        return (
            f"{self.user}: {self.get_absence_type_display()} "
            f"{self.start_date:%d.%m.%Y}–{self.end_date:%d.%m.%Y}"
        )

    @property
    def days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    def is_active_on(self, on_date):
        if not (self.start_date and self.end_date):
            return False
        return self.start_date <= on_date <= self.end_date

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Дата «По» не может быть раньше «С»."})
        if self.absence_type == self.TYPE_OTHER and not (self.reason or "").strip():
            raise ValidationError({
                "reason": "Для типа «Другое» укажите причину отсутствия.",
            })


class ApprovalRoute(models.Model):
    KIND_APPROVAL = "approval"
    KIND_ACK = "acknowledgment"
    KIND_CHOICES = [
        (KIND_APPROVAL, "Согласование"),
        (KIND_ACK, "Ознакомление"),
    ]

    name = models.CharField("Название маршрута", max_length=255, unique=True)
    description = models.CharField("Описание", max_length=500, blank=True)
    kind = models.CharField(
        "Тип маршрута", max_length=20,
        choices=KIND_CHOICES, default=KIND_APPROVAL,
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Маршрут согласования"
        verbose_name_plural = "Маршруты согласования"
        ordering = ("name",)

    def __str__(self):
        return self.name


class AcknowledgmentRoute(ApprovalRoute):
    """Прокси-модель для маршрутов ознакомления — отдельный раздел в админке."""

    class Meta:
        proxy = True
        verbose_name = "Маршрут ознакомления"
        verbose_name_plural = "Маршруты ознакомления"


class ApprovalRouteStep(models.Model):
    ACTION_ACK = "acknowledge"
    ACTION_SIGN = "sign"
    ACTION_CHOICES = [
        (ACTION_ACK, "Ознакомление"),
        (ACTION_SIGN, "Согласование / Подпись"),
    ]

    TARGET_ROLE = "role"
    TARGET_DEPARTMENT = "department"
    TARGET_ALL = "all"
    TARGET_HEADS = "heads"
    TARGET_CHOICES = [
        (TARGET_ROLE, "По роли"),
        (TARGET_DEPARTMENT, "Весь отдел"),
        (TARGET_ALL, "Все сотрудники"),
        (TARGET_HEADS, "Все руководители отделов"),
    ]

    route = models.ForeignKey(
        ApprovalRoute, on_delete=models.CASCADE,
        related_name="steps", verbose_name="Маршрут",
    )
    order = models.PositiveSmallIntegerField("Порядок", default=1)
    target_type = models.CharField(
        "Кому", max_length=12,
        choices=TARGET_CHOICES, default=TARGET_ROLE,
        help_text="По роли — один ответственный по очереди; "
                  "остальные варианты рассылают всем разом (для ознакомления).",
    )
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE,
        related_name="route_steps", verbose_name="Роль",
        null=True, blank=True,
    )
    org_department = models.ForeignKey(
        "shared_repository.Department",
        on_delete=models.CASCADE,
        related_name="route_steps",
        verbose_name="Отдел",
        null=True, blank=True,
    )
    action_type = models.CharField(
        "Тип действия", max_length=12,
        choices=ACTION_CHOICES, default=ACTION_SIGN,
    )

    class Meta:
        verbose_name = "Шаг маршрута"
        verbose_name_plural = "Шаги маршрута"
        unique_together = ("route", "order")
        ordering = ("route", "order")

    def __str__(self):
        return f"{self.order}. {self.target_label}"

    @property
    def target_label(self):
        if self.target_type == self.TARGET_ALL:
            return "Все сотрудники"
        if self.target_type == self.TARGET_HEADS:
            return "Все руководители отделов"
        if self.target_type == self.TARGET_DEPARTMENT:
            return f"Отдел «{self.org_department}»" if self.org_department_id else "Отдел (не указан)"
        return f"Роль «{self.department}»" if self.department_id else "Роль (не указана)"

    def clean(self):
        super().clean()
        if self.target_type == self.TARGET_ROLE and not self.department_id:
            raise ValidationError({"department": "Выберите роль для этого шага."})
        if self.target_type == self.TARGET_DEPARTMENT and not self.org_department_id:
            raise ValidationError({"org_department": "Выберите отдел для этого шага."})


class ApprovalProcess(models.Model):
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_APPROVED = "approved"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "В процессе"),
        (STATUS_APPROVED, "Согласован"),
        (STATUS_CANCELLED, "Отменён"),
    ]

    rkd = models.ForeignKey(
        "blog.UniversalRKD", on_delete=models.CASCADE,
        related_name="approval_processes", verbose_name="Документ РКД",
        null=True, blank=True,
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Тип документа",
        null=True,
        blank=True,
    )
    object_id = models.PositiveIntegerField("ID документа", null=True, blank=True)
    document = GenericForeignKey("content_type", "object_id")
    route = models.ForeignKey(
        ApprovalRoute, on_delete=models.CASCADE,
        related_name="processes", verbose_name="Маршрут",
    )
    status = models.CharField(
        "Статус", max_length=20,
        choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS,
    )
    current_order = models.PositiveSmallIntegerField("Текущий шаг", default=1)
    started_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="started_approvals", verbose_name="Кто запустил",
    )
    created_at = models.DateTimeField("Создан", default=timezone.now)
    finished_at = models.DateTimeField("Завершён", null=True, blank=True)

    class Meta:
        verbose_name = "Согласование/Ознакомление с документом"
        verbose_name_plural = "Согласования/Ознакомления с документами"
        ordering = ("-created_at",)

    def __str__(self):
        from .document_types import get_document_from_process
        doc = get_document_from_process(self)
        return f"Согласование «{doc or '—'}» ({self.get_status_display()})"

    def get_document(self):
        from .document_types import get_document_from_process
        return get_document_from_process(self)


class ApprovalTask(models.Model):
    KIND_REVIEW = "review"
    KIND_FIX = "fix"
    KIND_CHOICES = [
        (KIND_REVIEW, "Проверка / подписание"),
        (KIND_FIX, "Доработка автором"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Ожидает"),
        (STATUS_APPROVED, "Согласовано"),
        (STATUS_REJECTED, "Отклонено (замечание)"),
        (STATUS_DONE, "Отправлено на доработку"),
        (STATUS_CANCELLED, "Отменено"),
    ]

    process = models.ForeignKey(
        ApprovalProcess, on_delete=models.CASCADE,
        related_name="tasks", verbose_name="Согласование",
    )
    step = models.ForeignKey(
        ApprovalRouteStep, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tasks", verbose_name="Шаг маршрута",
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tasks", verbose_name="Роль",
    )
    kind = models.CharField(
        "Тип задачи", max_length=10,
        choices=KIND_CHOICES, default=KIND_REVIEW,
    )
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approval_tasks", verbose_name="Назначено",
    )
    status = models.CharField(
        "Статус", max_length=12,
        choices=STATUS_CHOICES, default=STATUS_PENDING,
    )
    is_recheck = models.BooleanField("Повторная проверка", default=False)
    comment = models.TextField("Замечание / комментарий", blank=True)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="children", verbose_name="Связанная задача",
    )
    signer_cn = models.CharField("ФИО из сертификата ЭЦП", max_length=500, null=True, blank=True)
    signer_cert_serial = models.CharField("Серийный № сертификата", max_length=200, null=True, blank=True)
    signer_cert_valid_to = models.CharField("Сертификат действителен до", max_length=50, null=True, blank=True)
    signer_cert_issuer = models.CharField("Удостоверяющий центр (УЦ)", max_length=500, null=True, blank=True)
    signature_b64 = models.TextField("Файл ЭЦП (base64 CAdES)", null=True, blank=True)
    signature_file = models.FileField(
        "Файл подписи (.sig)",
        upload_to="approvals/signatures/%Y/%m/",
        max_length=500,
        null=True,
        blank=True,
    )
    signed_payload = models.TextField("Метаданные подписанного файла", null=True, blank=True)

    created_at = models.DateTimeField("Создана", default=timezone.now)
    viewed_at = models.DateTimeField("Просмотрена", null=True, blank=True)
    resolved_at = models.DateTimeField("Завершена", null=True, blank=True)

    class Meta:
        verbose_name = "Задача согласования"
        verbose_name_plural = "Мои задачи на согласование"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.get_kind_display()} — {self.process.get_document() or '—'}"

    @property
    def target_label(self):
        if self.department_id:
            return str(self.department)
        if self.step_id:
            return self.step.target_label
        return "—"

    @property
    def is_active(self):
        return self.status == self.STATUS_PENDING


class Notification(models.Model):
    KIND_SIGN = "sign"
    KIND_ACK = "ack"
    KIND_FIX = "fix"
    KIND_WORK = "work"
    KIND_INFO = "info"
    KIND_CHOICES = [
        (KIND_SIGN, "На согласование / подпись"),
        (KIND_ACK, "На ознакомление"),
        (KIND_FIX, "На доработку"),
        (KIND_WORK, "Рабочее задание"),
        (KIND_INFO, "Информация"),
    ]

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="approval_notifications", verbose_name="Получатель",
    )
    title = models.CharField("Заголовок", max_length=255)
    text = models.TextField("Текст", blank=True)
    url = models.CharField("Ссылка", max_length=500, blank=True)
    kind = models.CharField(
        "Тип", max_length=10, choices=KIND_CHOICES, default=KIND_INFO,
    )
    is_read = models.BooleanField("Прочитано", default=False)
    created_at = models.DateTimeField("Создано", default=timezone.now)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления (согласование)"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.recipient}: {self.title}"


class ApprovalSheetRecord(models.Model):
    """Строка листа утверждения / ознакомления для документов (кроме РКД)."""

    SHEET_APPROVAL = "approval"
    SHEET_ACQUAINTANCE = "acquaintance"
    SHEET_CHOICES = [
        (SHEET_APPROVAL, "Лист утверждения"),
        (SHEET_ACQUAINTANCE, "Лист ознакомления"),
    ]

    process = models.ForeignKey(
        ApprovalProcess,
        on_delete=models.CASCADE,
        related_name="sheet_records",
        verbose_name="Согласование",
    )
    task = models.OneToOneField(
        ApprovalTask,
        on_delete=models.CASCADE,
        related_name="sheet_record",
        verbose_name="Задача",
    )
    sheet_type = models.CharField(
        "Тип листа", max_length=16, choices=SHEET_CHOICES,
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, verbose_name="Тип документа",
    )
    object_id = models.PositiveIntegerField("ID документа")
    document = GenericForeignKey("content_type", "object_id")
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Роль",
    )
    position = models.CharField("Отдел", max_length=150, blank=True)
    role_label = models.CharField("Роль", max_length=150, blank=True)
    signed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approval_sheet_records", verbose_name="Подписант",
    )
    signed_at = models.DateField("Дата", null=True, blank=True)
    cert_cn = models.CharField("ФИО из сертификата ЭЦП", max_length=500, blank=True)
    cert_issuer = models.CharField("Удостоверяющий центр (УЦ)", max_length=500, blank=True)
    step_order = models.PositiveSmallIntegerField("Порядок в маршруте", default=0)

    class Meta:
        verbose_name = "Запись листа согласования"
        verbose_name_plural = "Записи листов согласования"
        ordering = ("step_order", "pk")

    def __str__(self):
        return f"{self.get_sheet_type_display()} — {self.signed_by or '—'}"
