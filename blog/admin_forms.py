from django import forms
from django.contrib.admin.widgets import AdminDateWidget

from .models import WorkAssignment, _as_date, _INVALID_DATE_MSG


class WorkAssignmentAdminForm(forms.ModelForm):
    requires_hard_deadline = forms.BooleanField(
        required=False,
        initial=False,
        label="Требуется установить абсолютный дедлайн?",
    )

    class Meta:
        model = WorkAssignment
        fields = "__all__"
        widgets = {
            "conditional_deadline": forms.Textarea(attrs={"rows": 4, "cols": 80}),
        }
        labels = {
            "hard_deadline": "Установить дедлайн",
            "conditional_deadline": "Условия/ограничения",
        }
        help_texts = {
            "hard_deadline": (
                "Дата абсолютного дедлайна должна быть не раньше целевого срока выполнения."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            self.fields["requires_hard_deadline"].initial = bool(instance.hard_deadline)
        if "executor" in self.fields:
            self.fields["executor"].required = False

    def clean(self):
        cleaned = super().clean()
        requires = cleaned.get("requires_hard_deadline")
        hard_raw = cleaned.get("hard_deadline")
        target_raw = cleaned.get("target_deadline")

        for field_name, raw in (
            ("target_deadline", target_raw),
            ("hard_deadline", hard_raw),
            ("time_window_start", cleaned.get("time_window_start")),
            ("time_window_end", cleaned.get("time_window_end")),
        ):
            if raw in (None, ""):
                continue
            if _as_date(raw) is None:
                self.add_error(
                    field_name,
                    _INVALID_DATE_MSG,
                )

        hard = _as_date(hard_raw)
        target = _as_date(target_raw)
        for field_name in ("time_window_start", "time_window_end"):
            coerced = _as_date(cleaned.get(field_name))
            if coerced is not None:
                cleaned[field_name] = coerced
        if hard is not None:
            cleaned["hard_deadline"] = hard
        if target is not None:
            cleaned["target_deadline"] = target

        if not requires:
            cleaned["hard_deadline"] = None
        elif not hard:
            self.add_error(
                "hard_deadline",
                "Укажите дату абсолютного дедлайна или снимите галочку.",
            )
        elif target and hard < target:
            self.add_error(
                "hard_deadline",
                "Абсолютный дедлайн не может быть раньше целевого срока выполнения.",
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
    reason = forms.CharField(label="Причина", widget=forms.TextInput(attrs={"size": 80}))
    expected_deadline_version = forms.IntegerField(widget=forms.HiddenInput)


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
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60}),
    )


class WorkAssignmentReturnForm(forms.Form):
    comment = forms.CharField(
        required=False,
        label="Что нужно доработать",
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60}),
    )
