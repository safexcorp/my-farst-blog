from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


GROUP_ADMIN = "Согласование: Администратор"
GROUP_EMPLOYEE = "Согласование: Сотрудник"


def _ensure_departments(sender, **kwargs):
    from .models import Department, SIGNATURE_ROLE_CHOICES

    for role_key, role_label in SIGNATURE_ROLE_CHOICES:
        Department.objects.get_or_create(
            name=role_label,
            defaults={"signature_role": role_key},
        )


def _ensure_groups(sender, **kwargs):
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType
    from . import models as m

    admin_group, _ = Group.objects.get_or_create(name=GROUP_ADMIN)
    employee_group, _ = Group.objects.get_or_create(name=GROUP_EMPLOYEE)

    admin_only_models = [
        m.Department,
        m.DepartmentMember,
        m.Vacation,
        m.ApprovalRoute,
        m.ApprovalRouteStep,
    ]
    employee_extra_models = [
        m.ApprovalProcess,
        m.ApprovalTask,
        m.Notification,
    ]

    admin_perms = []
    for model_cls in admin_only_models + employee_extra_models:
        ct = ContentType.objects.get_for_model(model_cls)
        admin_perms.extend(Permission.objects.filter(content_type=ct))
    admin_group.permissions.set(admin_perms)

    employee_apps = {"blog", "crm", "shared_repository", "enterprise_asset_management"}
    all_app_perms = list(
        Permission.objects.filter(content_type__app_label__in=employee_apps)
    )
    for model_cls in employee_extra_models:
        ct = ContentType.objects.get_for_model(model_cls)
        all_app_perms.extend(Permission.objects.filter(content_type=ct))
    employee_group.permissions.set(all_app_perms)


class ApprovalsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "approvals"
    verbose_name = _("Согласование документов")

    def ready(self):
        post_migrate.connect(_ensure_groups, sender=self)
        post_migrate.connect(_ensure_departments, sender=self)
