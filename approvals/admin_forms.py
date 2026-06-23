from django import forms

from .models import ApprovalRoute


class StartApprovalForm(forms.Form):
    route = forms.ModelChoiceField(
        queryset=ApprovalRoute.objects.none(),
        label="Маршрут",
        empty_label="— выберите маршрут —",
    )
    comment = forms.CharField(
        label="Сопроводительный комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60}),
        help_text="Необязательно. Будет показан в уведомлении адресатам.",
    )

    def __init__(self, *args, kind=ApprovalRoute.KIND_APPROVAL, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        self.fields["route"].queryset = ApprovalRoute.objects.filter(
            is_active=True, kind=kind,
        )
        if kind == ApprovalRoute.KIND_ACK:
            self.fields["route"].label = "Маршрут ознакомления"
            self.fields["route"].empty_label = "— выберите маршрут ознакомления —"
        else:
            self.fields["route"].label = "Маршрут согласования"
            self.fields["route"].empty_label = "— выберите маршрут согласования —"


class RejectTaskForm(forms.Form):
    comment = forms.CharField(
        label="Замечание для автора",
        widget=forms.Textarea(attrs={"rows": 5, "cols": 80}),
    )
