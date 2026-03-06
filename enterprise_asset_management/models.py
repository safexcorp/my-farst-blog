from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


MAX_FILE_MB = 50


def validate_file_size(value):
    limit = MAX_FILE_MB * 1024 * 1024
    if value.size > limit:
        raise ValidationError(f"Размер одного файла не должен превышать {MAX_FILE_MB} МБ")


class WorkEquipment(models.Model):
    """
    Рабочее оборудование
    """

    name_type = models.CharField("Наименование, тип", max_length=100)
    serial_number = models.CharField("Заводской номер (s/n)", max_length=12, blank=True, null=True,unique=True)
    measuring_device = models.BooleanField("Средство измерений", default=False)
    next_calibration_date = models.DateField("Дата плановой поверки", blank=True, null=True)
    calibration_required = models.BooleanField("Требуется калибровка", default=False)
    planned_calibration_date = models.DateField("Дата плановой калибровки", blank=True, null=True)
    workstation = models.CharField("Рабочее место", max_length=100, blank=True, null=True)

    STATUS_CHOICES = [
        ("in_use", "В эксплуатации"),
        ("under_verification", "На поверке"),
        ("under_calibration", "На калибровке"),
        ("in_stock", "На складе"),
        ("under_repair", "В ремонте"),
        ("faulty", "Неисправен"),
    ]
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        blank=True,
        default="in_use",
    )

    replacement_allowed = models.CharField(
        "Допустимая замена",
        max_length=200,
        blank=True,
        null=True,
    )

    note = models.CharField(
        "Примечание",
        max_length=300,
        blank=True,
        null=True,
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="work_equipment_author",
        verbose_name="Создатель (автор)",
    )
    date_of_creation = models.DateTimeField("Дата и время создания", default=timezone.now)

    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="work_equipment_last_editor",
        verbose_name="Последний редактор",
    )
    date_of_change = models.DateTimeField("Дата и время последнего изменения", auto_now=True)

    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="work_equipment_current_responsible",
        verbose_name="Текущий ответственный",
    )

    version = models.CharField(
        "Версия",
        max_length=3,
        default="1",
    )
    version_diff = models.CharField("Сравнение версий", max_length=1000, blank=True, null=True)

    class Meta:
        verbose_name = "Рабочее оборудование"
        verbose_name_plural = "Рабочее оборудование"

    def clean(self):
        if self.measuring_device and not self.next_calibration_date:
            raise ValidationError({"next_calibration_date": "Обязательное поле для средства измерений."})
        if self.calibration_required and not self.planned_calibration_date:
            raise ValidationError({"planned_calibration_date": "Обязательное поле при включённой калибровке."})

    def __str__(self):
        return self.name_type


class WorkEquipmentFile(models.Model):
    """
    Сопроводительные документы к рабочему оборудованию
    """

    work_equipment = models.ForeignKey(
        WorkEquipment,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Рабочее оборудование",
    )
    file = models.FileField("Файл", upload_to="work_equipment_files/", validators=[validate_file_size])
    uploaded_at = models.DateTimeField("Дата загрузки", default=timezone.now)

    class Meta:
        verbose_name = "Сопроводительный документ"
        verbose_name_plural = "Сопроводительные документы"

    def __str__(self):
        return f"Файл для: {self.work_equipment}"


class TransportVehicle(models.Model):
    """
    Транспортные средства
    """

    make_model = models.CharField("Марка, модель", max_length=100, default="")

    registration_plate = models.CharField(
        "Регистрационный знак",
        max_length=20,
        unique=True,
        blank=True,
        null=True,
    )

    insurance = models.BooleanField(
        "Подлежит страхованию",
        default=False,
    )

    next_insurance_date = models.DateField(
        "Дата плановой страховки",
        blank=True,
        null=True,
    )

    inspection = models.BooleanField(
        "Подлежит техосмотру",
        default=False,
    )

    next_inspection_date = models.DateField(
        "Дата планового техосмотра",
        blank=True,
        null=True,
    )


    note = models.TextField(
        "Примечание",
        max_length=2000,
        blank=True,
        null=True,
    )

    # --- Системные поля ---

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transport_vehicle_author",
        verbose_name="Создатель (автор)",
        default=1,
    )

    date_of_creation = models.DateTimeField(
        "Дата и время создания",
        default=timezone.now,
    )

    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transport_vehicle_last_editor",
        verbose_name="Последний редактор",
        default=1,
    )

    date_of_change = models.DateTimeField(
        "Дата и время последнего изменения",
        auto_now=True,
    )

    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transport_vehicle_current_responsible",
        verbose_name="Текущий ответственный",
        default=1,
    )

    version = models.CharField(
        "Версия",
        max_length=3,
        default="1",
    )

    class Meta:
        verbose_name = "Транспортное средство"
        verbose_name_plural = "Транспортные средства"

    def clean(self):
        errors = {}

        if self.insurance and not self.next_insurance_date:
            errors["next_insurance_date"] = "Обязательное поле при включенном страховании."

        if self.inspection and not self.next_inspection_date:
            errors["next_inspection_date"] = "Обязательное поле при включенном техосмотре."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.make_model} ({self.registration_plate})"

class TransportVehicleFile(models.Model):
    """
    Сопроводительные документы к транспортному средству
    """

    transport_vehicle = models.ForeignKey(
        TransportVehicle,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Транспортное средство",
    )

    file = models.FileField(
        "Файл",
        upload_to="transport_vehicle_files/",
        validators=[validate_file_size],
    )

    uploaded_at = models.DateTimeField(
        "Дата загрузки",
        default=timezone.now,
    )

    class Meta:
        verbose_name = "Сопроводительный документ"
        verbose_name_plural = "Сопроводительные документы"

    def __str__(self):
        return f"Файл для: {self.transport_vehicle}"

class TransportRepair(models.Model):
    """
    Ремонт транспортного средства
    """

    transport_vehicle = models.ForeignKey(
        TransportVehicle,
        on_delete=models.CASCADE,
        related_name="repairs",
        verbose_name="Транспортное средство",
    )

    repair_date = models.DateField(
        "Дата ремонта",
    )

    description = models.TextField(
        "Описание выполненных работ",
        max_length=5000,
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transport_repair_author",
        verbose_name="Создатель (автор)",
    )

    date_of_creation = models.DateTimeField(
        "Дата и время создания",
        default=timezone.now,
    )

    class Meta:
        verbose_name = "Ремонт"
        verbose_name_plural = "Ремонты"
        ordering = ("-repair_date",)

    def __str__(self):
        return f"{self.transport_vehicle} — {self.repair_date}"


class TransportRepairFile(models.Model):
    transport_repair = models.ForeignKey(
        TransportRepair,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Ремонт",
    )
    file = models.FileField(
        "Файл",
        upload_to="transport_repair_files/",
        validators=[validate_file_size],
    )
    uploaded_at = models.DateTimeField("Дата загрузки", default=timezone.now)

    class Meta:
        verbose_name = "Документ, чек"
        verbose_name_plural = "Документы, чеки"

    def __str__(self):
        return f"Файл для: {self.transport_repair}"


from django.contrib.auth import get_user_model
User = get_user_model()

#ПроизводственныеПлощадки
class ProductionArea(models.Model):

    OBJECT_CHOICES = [
        ("office", "Офис / помещение"),
        ("building", "Здание"),
        ("land", "Участок"),
    ]

    LOCATION_CHOICES = [
        ("techno_park", "Технопарк Университетский"),
    ]

    WORKING_CONDITIONS_CHOICES = [
        ("optimal", "Оптимальные"),
        ("acceptable", "Допустимые"),
        ("harmful", "Вредные"),
        ("dangerous", "Опасные"),
    ]

    RESTRICTIONS_CHOICES = [
        ("none", "-"),
        ("servitude", "Сервитут"),
        ("mortgage", "Ипотека"),
        ("trust", "Доверительное управление"),
        ("rent", "Аренда, лизинг"),
    ]


    object = models.CharField(
        "Объект",
        max_length=20,
        choices=OBJECT_CHOICES,
        default="office",
    )

    location = models.CharField(
        "Место нахождения",
        max_length=100,
        choices=LOCATION_CHOICES,
        default="techno_park",
    )

    number_name = models.CharField(
        "Номер (наименование)",
        max_length=20,
    )

    area = models.DecimalField(
        "Площадь, м²",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )

    purpose = models.CharField(
        "Назначение",
        max_length=1000,
        blank=True,
    )

    workstations = models.CharField(
        "Рабочие места (зоны)",
        max_length=1000,
        blank=True,
    )

    working_conditions = models.CharField(
        "Условия труда",
        max_length=20,
        choices=WORKING_CONDITIONS_CHOICES,
        default="optimal",
        blank=True,
    )

    restrictions = models.CharField(
        "Ограничения",
        max_length=20,
        choices=RESTRICTIONS_CHOICES,
        default="none",
        blank=True,
    )

    contract_date = models.DateField(
        "Дата действия договора",
        null=True,
        blank=True,
    )

    note = models.TextField(
        "Примечание",
        max_length=2000,
        blank=True,
    )


    author = models.ForeignKey(
        User,
        verbose_name="Создатель",
        on_delete=models.PROTECT,
        related_name="production_area_created",
    )

    last_editor = models.ForeignKey(
        User,
        verbose_name="Последний редактор",
        on_delete=models.PROTECT,
        related_name="production_area_edited",
    )

    current_responsible = models.ForeignKey(
        User,
        verbose_name="Текущий ответственный",
        on_delete=models.PROTECT,
        related_name="production_area_responsible",
    )

    date_of_creation = models.DateTimeField(
        "Дата создания",
        auto_now_add=True
    )

    date_of_change = models.DateTimeField(
        "Дата изменения",
        auto_now=True
    )

    version = models.CharField(
        "Версия",
        max_length=3,
        default="1",
    )


    def clean(self):
        from django.core.exceptions import ValidationError

        if self.restrictions != "none" and not self.contract_date:
            raise ValidationError(
                {"contract_date": "Укажите дату действия договора при наличии ограничений."}
            )

    class Meta:
        verbose_name = "Производственная площадка"
        verbose_name_plural = "Производственные площадки"
        ordering = ["-date_of_creation"]

    def __str__(self):
        return f"{self.number_name}"

class ProductionAreaFile(models.Model):
    production_area = models.ForeignKey(
        ProductionArea,
        on_delete=models.CASCADE,
        related_name="files",
    )

    file = models.FileField("Файл", upload_to="production_area_files/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Файл площадки"
        verbose_name_plural = "Файлы площадки"

    def __str__(self):
        return self.file.name