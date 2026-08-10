import re

import bleach
from django import forms
from django.contrib.admin.widgets import AdminDateWidget

from .models import WorkAssignment, _as_date, _INVALID_DATE_MSG
from .widgets import RichTextWidget

# Matches exactly what the "task" field's Quill toolbar can produce
# (assets/js/richtext_widget.js) - font, size, bold/italic/underline/strike, lists+indent, align.
# Quill 2.x renders both bullet and numbered lists as <ol>, distinguished by
# li[data-list] - see assets/vendor/quill/quill.snow.css.
TASK_ALLOWED_TAGS = ["p", "br", "strong", "em", "u", "s", "ol", "ul", "li", "span"]
_TASK_ALLOWED_CLASS_RE = re.compile(r"^ql-(font|size|indent|align|direction)-[a-z0-9-]+$")


def _task_attr_filter(tag, name, value):
    if name == "data-list":
        return tag == "li" and value in ("bullet", "ordered")
    if name != "class":
        return False
    return all(_TASK_ALLOWED_CLASS_RE.match(cls) for cls in value.split())


def sanitize_task_html(value):
    return bleach.clean(
        value or "",
        tags=TASK_ALLOWED_TAGS,
        attributes=_task_attr_filter,
        strip=True,
    )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data]
        return single_file_clean(data, initial)


class WorkAssignmentAdminForm(forms.ModelForm):
    requires_hard_deadline = forms.BooleanField(
        required=False,
        initial=False,
        label="Требуется установить дедлайн?",
    )
    attachments = MultipleFileField(
        required=False,
        label="Вложения (к заданию)",
        help_text="Можно выбрать сразу несколько файлов.",
    )

    class Meta:
        model = WorkAssignment
        fields = "__all__"
        widgets = {
            "conditional_deadline": forms.Textarea(attrs={"rows": 4, "cols": 80}),
            "task": RichTextWidget(),
        }
        labels = {
            "hard_deadline": "Установить дедлайн",
            "conditional_deadline": "Условия/ограничения",
        }
        help_texts = {
            "hard_deadline": (
                "Дата дедлайна должна быть не раньше целевого срока выполнения."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance and instance.pk and "requires_hard_deadline" in self.fields:
            self.fields["requires_hard_deadline"].initial = bool(instance.hard_deadline)
        if "executor" in self.fields:
            self.fields["executor"].required = False

    def clean_task(self):
        return sanitize_task_html(self.cleaned_data.get("task"))

    def clean(self):
        cleaned = super().clean()

        for field_name in ("target_deadline", "hard_deadline", "time_window_start", "time_window_end"):
            if field_name not in self.fields:
                continue
            raw = cleaned.get(field_name)
            if raw in (None, ""):
                continue
            coerced = _as_date(raw)
            if coerced is None:
                self.add_error(field_name, _INVALID_DATE_MSG)
            else:
                cleaned[field_name] = coerced

        if "hard_deadline" in self.fields:
            requires = cleaned.get("requires_hard_deadline")
            hard = cleaned.get("hard_deadline")
            target = cleaned.get("target_deadline")
            if not requires:
                cleaned["hard_deadline"] = None
            elif not hard:
                self.add_error(
                    "hard_deadline",
                    "Укажите дату дедлайна или снимите галочку.",
                )
            elif target and hard < target:
                self.add_error(
                    "hard_deadline",
                    "Дедлайн не может быть раньше целевого срока выполнения.",
                )

        action = self._save_action()
        executor = cleaned.get("executor")
        if action == "draft":
            if executor:
                self.add_error(
                    "executor",
                    "Черновик сохраняется без исполнителя. Очистите поле «Исполнитель».",
                )
            if self.instance.pk and self.instance.executor_id:
                self.add_error(
                    None,
                    "Отправленное рабочее задание нельзя сохранить как черновик.",
                )
        elif action == "publish" and not executor:
            self.add_error(
                "executor",
                "Укажите исполнителя для отправки рабочего задания.",
            )
        elif action == "continue":
            if not executor and self.instance.pk and self.instance.executor_id:
                self.add_error(
                    "executor",
                    "У отправленного рабочего задания нельзя убрать исполнителя.",
                )
        return cleaned

    def _save_action(self):
        if not self.data:
            return None
        if "_addanother" in self.data:
            return "draft"
        if "_save" in self.data:
            return "publish"
        if "_continue" in self.data:
            return "continue"
        return None


class RescheduleAdminForm(forms.Form):
    new_target_deadline = forms.DateField(
        required=False,
        label="Новый целевой срок",
        widget=AdminDateWidget,
    )
    requires_hard_deadline = forms.BooleanField(
        required=False,
        label="Требуется установить дедлайн?",
    )
    new_hard_deadline = forms.DateField(
        required=False,
        label="Дедлайн",
        widget=AdminDateWidget,
    )
    reason = forms.CharField(label="Причина", widget=forms.TextInput(attrs={"size": 80}))
    expected_deadline_version = forms.IntegerField(widget=forms.HiddenInput)

    def clean(self):
        cleaned = super().clean()
        requires = cleaned.get("requires_hard_deadline")
        hard = cleaned.get("new_hard_deadline")
        target = cleaned.get("new_target_deadline")

        if not requires:
            cleaned["new_hard_deadline"] = None
        elif not hard:
            self.add_error("new_hard_deadline", "Укажите дату дедлайна или снимите галочку.")
        elif target and hard < target:
            self.add_error("new_hard_deadline", "Дедлайн не может быть раньше целевого срока.")

        return cleaned


class WorkAssignmentCloseForm(forms.Form):
    RESULT_CHOICES = [
        ("done", "Выполнено"),
        ("partial", "Выполнено частично"),
        ("not_done", "Не выполнено"),
    ]
    result = forms.ChoiceField(
        choices=RESULT_CHOICES,
        widget=forms.RadioSelect,
        label="Результат проверки",
    )
    comment = forms.CharField(
        required=False,
        label="Комментарий (необязательно)",
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60, "class": "vLargeTextField"}),
    )


class WorkAssignmentReturnForm(forms.Form):
    comment = forms.CharField(
        required=False,
        label="Что нужно доработать",
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60, "class": "vLargeTextField"}),
    )


class WorkAssignmentRescheduleRequestForm(forms.Form):
    reason = forms.CharField(
        label="Причина переноса",
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60, "class": "vLargeTextField"}),
    )
    desired_date = forms.DateField(
        label="Желаемая дата выполнения",
        widget=AdminDateWidget,
    )


class WorkAssignmentSubmitReviewForm(forms.Form):
    result_description = forms.CharField(
        label="Описание результата",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60, "class": "vLargeTextField"}),
    )
    file = MultipleFileField(required=False, label="Вложения (приложенные к результату)")
