from django import forms
from django.contrib.admin.widgets import AdminDateWidget
from django.utils import timezone

from .models import TicketComment, SupportTicket


class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ['text', 'file']
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Опишите взаимодействие с заказчиком…',
                'class': 'vLargeTextField',
            }),
        }


class SupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = [
            'customer',
            'product',
            'category',
            'problem',
            'description',
            'created_date',
            'intake_channel',
            'status',
            'resolution',
            'claim_type',
            'claim_attachment',
            'assigned_to',
        ]
        widgets = {
            'problem': forms.Textarea(attrs={'rows': 3, 'class': 'vLargeTextField'}),
            'description': forms.Textarea(attrs={'rows': 8, 'class': 'vLargeTextField'}),
            'resolution': forms.Textarea(attrs={'rows': 6, 'class': 'vLargeTextField'}),
            'created_date': AdminDateWidget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['claim_type'].required = False
        self.fields['created_date'].widget = AdminDateWidget()
        if self.instance.pk and self.instance.created_date:
            self.fields['created_date'].initial = self.instance.created_date
        else:
            self.fields['created_date'].initial = timezone.localdate()

    def clean_created_date(self):
        value = self.cleaned_data.get('created_date')
        if value:
            return value
        if not self.instance.pk:
            return timezone.localdate()
        return value

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        resolution = (cleaned.get('resolution') or '').strip()
        claim_type = cleaned.get('claim_type') or ''
        claim_attachment = cleaned.get('claim_attachment')

        if status == SupportTicket.STATUS_RESOLVED and not resolution:
            self.add_error(
                'resolution',
                'Обязательно при статусе «Решена/Закрыта».',
            )

        if claim_type == SupportTicket.CLAIM_OFFICIAL:
            has_attachment = bool(claim_attachment) or (
                self.instance.pk and self.instance.claim_attachment
            )
            if not has_attachment:
                self.add_error(
                    'claim_attachment',
                    'Для официальной претензии приложите письмо или декларацию.',
                )

        return cleaned
