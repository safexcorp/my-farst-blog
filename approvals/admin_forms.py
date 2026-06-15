from django import forms

from .models import ApprovalRoute


class StartApprovalForm(forms.Form):
    route = forms.ModelChoiceField(
        queryset=ApprovalRoute.objects.filter(is_active=True),
        label="Маршрут согласования",
        empty_label="— выберите маршрут —",
    )


class RejectTaskForm(forms.Form):
    comment = forms.CharField(
        label="Замечание для автора",
        widget=forms.Textarea(attrs={"rows": 5, "cols": 80}),
    )
