from typing import Optional
from django import forms
from django.contrib.admin.widgets import AdminDateWidget
from django.utils import timezone
from .models import WorkAssignment, UniversalRKD, TechnicalProposalDocument
from .helpers import (
    RKD_CATEGORY_BY_SECTION,
    section_allows_position,
    section_has_category_choices,
)

_CATEGORY_PLACEHOLDER = [("", "---------")]


class WorkAssignmentForm(forms.ModelForm):
    class Meta:
        model = WorkAssignment
        fields = "__all__"
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}),
            'target_deadline': forms.DateInput(attrs={'type': 'date'}),
            'hard_deadline': forms.DateInput(attrs={'type': 'date'}),
            'time_window_start': forms.DateInput(attrs={'type': 'date'}),
            'time_window_end': forms.DateInput(attrs={'type': 'date'}),
            'control_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        today = timezone.localdate()
        instance = getattr(self, 'instance', None)

        if instance and instance.pk:
            if instance.deadline and today >= instance.deadline:
                self.fields['result'].required = True

            if instance.target_deadline and today >= instance.target_deadline:
                self.fields['control_date'].required = True

    def clean(self):
        cleaned = super().clean()
        today = timezone.localdate()

        deadline = cleaned.get('deadline')
        target_deadline = cleaned.get('target_deadline')
        result = cleaned.get('result')
        control_date = cleaned.get('control_date')
        tw_start = cleaned.get('time_window_start')
        tw_end = cleaned.get('time_window_end')

        # валидация окна
        if tw_start and tw_end and tw_end < tw_start:
            self.add_error('time_window_end', 'Дата «по» не может быть раньше даты «с».')

        if deadline and today >= deadline and not result:
            self.add_error('result', 'После наступления срока выполнения нужно выбрать результат.')

        if target_deadline and today >= target_deadline and not control_date:
            self.add_error('control_date', 'После наступления целевого срока необходимо указать дату контроля.')

        return cleaned


class UniversalRKDForm(forms.ModelForm):
    _cat = UniversalRKD._meta.get_field("category")
    category = forms.ChoiceField(
        label=_cat.verbose_name,
        required=False,
        choices=_CATEGORY_PLACEHOLDER,
    )

    class Meta:
        model = UniversalRKD
        fields = "__all__"
        exclude = ("order_in_section",)
        widgets = {
            "validity_date": AdminDateWidget(),
        }
        labels = {
            "document_uploaded_file": "Итоговый",
            "document_source": "Исходник",
            "approval_document": "Итоговый (PDF)",
            "approval_source": "Исходник (DOCX)",
            "attestation_document": "Итоговый (PDF)",
            "attestation_source": "Исходник (DOCX)",
        }
        help_texts = {
            "approval_document": "Допустимый формат: PDF.",
            "approval_source": "Допустимый формат: DOCX.",
            "attestation_document": "Допустимый формат: PDF.",
            "attestation_source": "Допустимый формат: DOCX.",
        }

    def _current_specification_section(self) -> Optional[str]:
        if self.is_bound:
            key = self.add_prefix("specification_section")
            raw = self.data.get(key)
            if raw is None:
                for k in self.data.keys():
                    if k == "specification_section" or k.endswith("-specification_section"):
                        raw = self.data.get(k)
                        break
            if raw is not None:
                s = (raw or "").strip()
                return s or None
        initial = getattr(self, "initial", None) or {}
        v = initial.get("specification_section")
        if v not in (None, ""):
            return str(v).strip()
        if getattr(self.instance, "pk", None):
            v = getattr(self.instance, "specification_section", None)
            if v not in (None, ""):
                return str(v).strip()
        return None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        section = self._current_specification_section()
        cats = RKD_CATEGORY_BY_SECTION.get(section or "", ()) or ()
        if cats:
            self.fields["category"].choices = _CATEGORY_PLACEHOLDER + [(c, c) for c in cats]
        else:
            self.fields["category"].choices = list(_CATEGORY_PLACEHOLDER)

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("specification_section") or ""
        if not section_has_category_choices(section):
            cleaned["category"] = ""
        if not section_allows_position(section):
            cleaned["position"] = "-"
        return cleaned


class TechnicalProposalForm(forms.ModelForm):
    class Meta:
        model = TechnicalProposalDocument
        fields = "__all__"
        labels = {
            "document_uploaded_file": "Итоговый",
            "document_source": "Исходник",
            "approval_document": "Итоговый (PDF)",
            "approval_source": "Исходник (DOCX)",
            "attestation_document": "Итоговый (PDF)",
            "attestation_source": "Исходник (DOCX)",
        }
        help_texts = {
            "approval_document": "Допустимый формат: PDF.",
            "approval_source": "Допустимый формат: DOCX.",
            "attestation_document": "Допустимый формат: PDF.",
            "attestation_source": "Допустимый формат: DOCX.",
        }
