from django import forms
from django.contrib.admin.widgets import AdminDateWidget

from .models import ApprovalRoute


class MyProfileForm(forms.Form):
    """Самостоятельное редактирование сотрудником своих личных данных.

    Только личные поля (ФИО, дата рождения, телефон, фото) — организационные
    (отдел, должность, руководитель) заполняет только сисадмин через «Пользователи»,
    т.к. отдел влияет на маршрутизацию согласований.
    """
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    patronymic = forms.CharField(label="Отчество", max_length=100, required=False)
    birth_date = forms.DateField(label="Дата рождения", required=False, widget=AdminDateWidget)
    phone = forms.CharField(
        label="Телефон", max_length=20, required=False,
        widget=forms.TextInput(attrs={"form": "my-profile-form"}),
    )
    email = forms.EmailField(
        label="Email", required=False,
        widget=forms.EmailInput(attrs={"form": "my-profile-form"}),
    )
    avatar = forms.ImageField(label="Фото", required=False)

    new_phone_value = forms.CharField(
        label="Ещё телефон", max_length=254, required=False,
        widget=forms.TextInput(attrs={
            "form": "my-profile-form", "placeholder": "Телефон",
            "style": "flex:1; min-width:120px;",
        }),
    )
    new_phone_note = forms.CharField(
        label="Примечание", max_length=100, required=False,
        widget=forms.TextInput(attrs={
            "form": "my-profile-form", "placeholder": "Примечание",
            "style": "flex:1; min-width:120px;",
        }),
    )
    new_email_value = forms.CharField(
        label="Ещё email", max_length=254, required=False,
        widget=forms.TextInput(attrs={
            "form": "my-profile-form", "placeholder": "Email",
            "style": "flex:1; min-width:120px;",
        }),
    )
    new_email_note = forms.CharField(
        label="Примечание", max_length=100, required=False,
        widget=forms.TextInput(attrs={
            "form": "my-profile-form", "placeholder": "Примечание",
            "style": "flex:1; min-width:120px;",
        }),
    )


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
