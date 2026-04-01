import types

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blog"
    verbose_name = _("PLC (Управление жизненным циклом продуктов)")

    def ready(self):
        from django.contrib import admin

        site = admin.site
        _orig_get_app_list = site.get_app_list

        def get_app_list(self, request, app_label=None):
            app_list = _orig_get_app_list(request, app_label)
            first = [a for a in app_list if a.get("app_label") == "blog"]
            rest = [a for a in app_list if a.get("app_label") != "blog"]
            return first + rest

        site.get_app_list = types.MethodType(get_app_list, site)
