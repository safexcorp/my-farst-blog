"""Массовое добавление изделий к отгрузке (страница «Добавить списком»).

Строка списка — «<номер> <SN>», ровно в том виде, в каком номера ведутся
в заметке на телефоне:

    910 00885509  ->  зав. № 2009102026, примечание «ПУ - SN:00885509»

Заводской номер собирается по маске «2» + номер (5 знаков с ведущими нулями)
+ год даты изготовления, поэтому длина всегда 10 символов. Из этой же маски
генератор ПСИ берёт номер протокола — sn[1:6] (blog/utils.py).

Модуль самодостаточный: моделей не меняет и миграций не требует. Чтобы убрать
функционал, достаточно удалить этот файл, шаблон admin/blog/shipment/bulk_add.html,
ShipmentAdmin.get_urls()/bulk_add_view() и ссылку в change_list.html — уже
созданные изделия при этом остаются обычными записями.
"""

import re
from dataclasses import dataclass

from django import forms
from django.contrib.admin.widgets import AdminDateWidget, AutocompleteSelect

from crm.models import Customer

from .models import Post, RKDDeveloper, Shipment

# Маска заводского номера: «2» + номер (5 знаков) + год.
SERIAL_PREFIX = "2"
SERIAL_DIGITS = 5
MAX_ITEM_NUMBER = 10 ** SERIAL_DIGITS - 1  # 99999
# Примечание собирается из второго столбца заметки.
SN_DIGITS = 8
NOTE_TEMPLATE = "ПУ - SN:{sn}"
# Мягкий предел, чтобы случайная вставка постороннего текста не ушла в базу.
MAX_LINES = 1000

# «910 00885509»: номер и SN, разделитель — пробелы, табы, «;», «,» или «:».
_LINE_RE = re.compile(r"^(\d{1,%d})[\s;,:]+(\d{%d})$" % (SERIAL_DIGITS, SN_DIGITS))

_FORMAT_HINT = "ожидается «номер SN», например «910 00885509»"


def build_serial_number(number, year):
    """910, 2026 -> «2009102026»."""
    return "{}{:0{}d}{}".format(SERIAL_PREFIX, number, SERIAL_DIGITS, year)


def build_note(sn):
    """«00885509» -> «ПУ - SN:00885509»."""
    return NOTE_TEMPLATE.format(sn=sn)


@dataclass
class BulkRow:
    """Одна строка списка вместе с результатом её разбора."""

    line_no: int
    raw: str
    number: int = None
    serial_number: str = ""
    note: str = ""
    error: str = ""
    # Такой зав. № уже есть в базе по этой разработке — строку пропустим.
    duplicate: bool = False

    @property
    def will_be_created(self):
        return not self.error and not self.duplicate


def parse_bulk_items(raw_text, year):
    """Разбирает текст списка в строки BulkRow. Пустые строки пропускаются."""
    rows = []
    for line_no, raw in enumerate(raw_text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        row = BulkRow(line_no=line_no, raw=line)
        match = _LINE_RE.match(line)
        if not match:
            row.error = _FORMAT_HINT
        else:
            number = int(match.group(1))
            if number == 0:
                row.error = "номер изделия не может быть нулевым"
            else:
                row.number = number
                row.serial_number = build_serial_number(number, year)
                row.note = build_note(match.group(2))
        rows.append(row)
    return rows


def mark_duplicates(rows, post):
    """Помечает повторы внутри списка (ошибка) и уже заведённые зав. № (пропуск)."""
    first_seen = {}
    for row in rows:
        if row.error:
            continue
        previous = first_seen.get(row.serial_number)
        if previous is not None:
            row.error = "тот же зав. № уже задан строкой {}".format(previous)
        else:
            first_seen[row.serial_number] = row.line_no

    if post is None or not first_seen:
        return
    existing = set(
        Shipment.objects.filter(
            post=post, serial_number__in=first_seen
        ).values_list("serial_number", flat=True)
    )
    for row in rows:
        if not row.error and row.serial_number in existing:
            row.duplicate = True


class ShipmentBulkAddForm(forms.Form):
    """Общие для всей пачки поля + сам список «номер SN»."""

    post = forms.ModelChoiceField(
        label="Разработка (модификация)",
        queryset=Post.objects.all(),
    )
    manufacture_date = forms.DateField(
        label="Дата изготовления",
        widget=AdminDateWidget,
        help_text="Год из этой даты подставляется в заводской номер.",
    )
    manufacturer_org = forms.ModelChoiceField(
        label="Изготовитель",
        queryset=RKDDeveloper.objects.all(),
        required=False,
    )
    supplier_org = forms.ModelChoiceField(
        label="Поставщик",
        queryset=RKDDeveloper.objects.all(),
        required=False,
    )
    buyer = forms.ModelChoiceField(
        label="Покупатель",
        queryset=Customer.objects.all(),
        required=False,
    )
    recipient = forms.ModelChoiceField(
        label="Грузополучатель",
        queryset=Customer.objects.all(),
        required=False,
    )
    completeness = forms.CharField(
        label="Комплектность",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Одна на всю пачку; при необходимости правится потом в карточке изделия.",
    )
    items = forms.CharField(
        label="Список «номер SN»",
        widget=forms.Textarea(attrs={"rows": 14, "spellcheck": "false"}),
        help_text=(
            "По одному изделию в строке, как в заметке: «910 00885509». "
            "Номер — до {} знаков, SN — ровно {}.".format(SERIAL_DIGITS, SN_DIGITS)
        ),
    )

    # Заполняется в clean(); нужен странице, чтобы показать предпросмотр
    # в том числе когда в списке есть ошибочные строки.
    rows = ()

    # Поля, которые переносятся в каждое создаваемое изделие как есть.
    COMMON_FIELDS = (
        "post",
        "manufacture_date",
        "manufacturer_org",
        "supplier_org",
        "buyer",
        "recipient",
        "completeness",
    )

    AUTOCOMPLETE_FIELDS = (
        "post",
        "manufacturer_org",
        "supplier_org",
        "buyer",
        "recipient",
    )

    def __init__(self, *args, **kwargs):
        admin_site = kwargs.pop("admin_site", None)
        super().__init__(*args, **kwargs)
        if admin_site is None:
            return
        # Те же поля-автодополнения, что и в обычной форме изделия
        # (ShipmentAdmin.autocomplete_fields).
        for name in self.AUTOCOMPLETE_FIELDS:
            form_field = self.fields[name]
            form_field.widget = AutocompleteSelect(
                Shipment._meta.get_field(name), admin_site
            )
            # Замена виджета обходит сеттер queryset, поэтому список значений
            # для него проставляем вручную.
            form_field.widget.choices = form_field.choices

    def clean(self):
        cleaned = super().clean()
        raw_text = cleaned.get("items") or ""
        manufacture_date = cleaned.get("manufacture_date")
        if not raw_text.strip() or manufacture_date is None:
            # Про незаполненные обязательные поля Django сообщил сам.
            return cleaned

        rows = parse_bulk_items(raw_text, manufacture_date.year)
        if not rows:
            self.add_error("items", "Список пуст.")
            return cleaned
        if len(rows) > MAX_LINES:
            self.add_error(
                "items",
                "В списке {} строк, за один раз можно не больше {}. "
                "Разбейте список на части.".format(len(rows), MAX_LINES),
            )
            return cleaned

        mark_duplicates(rows, cleaned.get("post"))
        self.rows = rows

        if any(row.error for row in rows):
            self.add_error(
                "items",
                "В списке есть строки с ошибками — они отмечены в таблице ниже.",
            )
        elif not any(row.will_be_created for row in rows):
            self.add_error(
                "items",
                "Все изделия из списка уже заведены по этой разработке.",
            )
        return cleaned

    def rows_to_create(self):
        return [row for row in self.rows if row.will_be_created]

    def build_shipments(self, user):
        """Собирает (но не сохраняет) изделия по строкам, готовым к созданию."""
        common = {name: self.cleaned_data[name] for name in self.COMMON_FIELDS}
        return [
            Shipment(
                serial_number=row.serial_number,
                note=row.note,
                author=user,
                last_editor=user,
                current_responsible=user,
                **common
            )
            for row in self.rows_to_create()
        ]
