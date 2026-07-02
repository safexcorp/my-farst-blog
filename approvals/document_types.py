from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse


@dataclass(frozen=True)
class DocumentTypeConfig:
    key: str
    label: str
    model_label: str
    file_field: str
    author_field: str
    approval_document_field: str
    acquaintance_document_field: str
    admin_url_name: str
    no_file_message: str
    approval_filename_prefix: str
    acquaintance_filename_prefix: str
    get_center_line: Callable[[Any], str]
    get_doc_info_lines: Callable[[Any], list[tuple[str, str]]]
    get_title: Callable[[Any], str]
    get_subtitle: Callable[[Any], str]

    @property
    def model(self):
        return apps.get_model(self.model_label)

    def get_content_type(self):
        return ContentType.objects.get_for_model(self.model)

    def get_main_file(self, document):
        return getattr(document, self.file_field, None)

    def has_main_file(self, document) -> bool:
        f = self.get_main_file(document)
        return bool(f and getattr(f, "name", None))

    def get_author(self, document):
        return getattr(document, self.author_field, None)

    def get_admin_url(self, document) -> str:
        return reverse(self.admin_url_name, args=[document.pk])

    def get_file_url(self, document) -> str:
        f = self.get_main_file(document)
        if f and getattr(f, "url", None):
            return f.url
        return ""


def _rkd_center(doc) -> str:
    return (doc.desig_document or "—").strip() or "—"


def _rkd_info(doc) -> list[tuple[str, str]]:
    lines = []
    if doc.post:
        lines.append(("Разработка (модификация)", str(doc.post)))
    lines.append(("Обозначение документа", doc.desig_document or "—"))
    lines.append(("Наименование", doc.name or "—"))
    return lines


def _qms_center(doc) -> str:
    return (doc.document_title or "—").strip() or "—"


def _qms_info(doc) -> list[tuple[str, str]]:
    category = doc.get_category_display() if doc.category else "—"
    return [
        ("Категория", category),
        ("Название", doc.document_title or "—"),
        ("Номер изменения", doc.change_number or "—"),
    ]


def _independent_center(doc) -> str:
    return (doc.document_title or "—").strip() or "—"


def _independent_info(doc) -> list[tuple[str, str]]:
    return [
        ("Название документа", doc.document_title or "—"),
        ("Версия", doc.version or "—"),
    ]


def _order_center(doc) -> str:
    return (doc.registration_number or doc.subject or "—").strip() or "—"


def _order_info(doc) -> list[tuple[str, str]]:
    date_str = doc.order_date.strftime("%d.%m.%Y") if doc.order_date else "—"
    return [
        ("Тема", doc.subject or "—"),
        ("Дата", date_str),
        ("Регистрационный номер", doc.registration_number or "—"),
    ]


DOCUMENT_TYPES: dict[str, DocumentTypeConfig] = {
    "rkd": DocumentTypeConfig(
        key="rkd",
        label="РКД",
        model_label="blog.UniversalRKD",
        file_field="document_uploaded_file",
        author_field="author",
        approval_document_field="approval_document",
        acquaintance_document_field="acquaintance_document",
        admin_url_name="admin:blog_universalrkd_change",
        no_file_message=(
            "Загрузите основной документ (итоговый) в карточке РКД "
            "перед отправкой на согласование."
        ),
        approval_filename_prefix="ЛУ",
        acquaintance_filename_prefix="ЛО",
        get_center_line=_rkd_center,
        get_doc_info_lines=_rkd_info,
        get_title=lambda d: (d.desig_document or str(d)).strip(),
        get_subtitle=lambda d: (d.name or "").strip(),
    ),
    "qms": DocumentTypeConfig(
        key="qms",
        label="Документ СМК",
        model_label="shared_repository.QMSDocument",
        file_field="uploaded_file",
        author_field="author",
        approval_document_field="approval_document",
        acquaintance_document_field="acquaintance_document",
        admin_url_name="admin:shared_repository_qmsdocument_change",
        no_file_message=(
            "Загрузите файл в поле «Загружаемый файл» перед отправкой на согласование."
        ),
        approval_filename_prefix="ЛУ",
        acquaintance_filename_prefix="ЛО",
        get_center_line=_qms_center,
        get_doc_info_lines=_qms_info,
        get_title=lambda d: (d.document_title or str(d)).strip(),
        get_subtitle=lambda d: f"{d.get_category_display()} · изм. {d.change_number or '—'}",
    ),
    "independent": DocumentTypeConfig(
        key="independent",
        label="Отдельный документ",
        model_label="shared_repository.SharedRepository",
        file_field="uploaded_file",
        author_field="author",
        approval_document_field="approval_document",
        acquaintance_document_field="acquaintance_document",
        admin_url_name="admin:shared_repository_sharedrepository_change",
        no_file_message=(
            "Загрузите файл в поле «Загружаемый файл» перед отправкой на согласование."
        ),
        approval_filename_prefix="ЛУ",
        acquaintance_filename_prefix="ЛО",
        get_center_line=_independent_center,
        get_doc_info_lines=_independent_info,
        get_title=lambda d: (d.document_title or str(d)).strip(),
        get_subtitle=lambda d: f"вер. {d.version or '—'}",
    ),
    "order": DocumentTypeConfig(
        key="order",
        label="Приказ",
        model_label="shared_repository.AdministrativeOrder",
        file_field="uploaded_file",
        author_field="author",
        approval_document_field="approval_document",
        acquaintance_document_field="acquaintance_document",
        admin_url_name="admin:shared_repository_administrativeorder_change",
        no_file_message=(
            "Загрузите файл в поле «Загружаемый файл» перед отправкой на согласование."
        ),
        approval_filename_prefix="ЛУ",
        acquaintance_filename_prefix="ЛО",
        get_center_line=_order_center,
        get_doc_info_lines=_order_info,
        get_title=lambda d: (d.registration_number or str(d)).strip(),
        get_subtitle=lambda d: (d.subject or "").strip(),
    ),
}

DOCUMENT_TYPE_FILTER_CHOICES = [(k, v.label) for k, v in DOCUMENT_TYPES.items()]


def get_config_by_key(key: str) -> DocumentTypeConfig:
    try:
        return DOCUMENT_TYPES[key]
    except KeyError as exc:
        raise ValueError(f"Неизвестный тип документа: {key}") from exc


def get_config_for_document(document) -> DocumentTypeConfig:
    for cfg in DOCUMENT_TYPES.values():
        if isinstance(document, cfg.model):
            return cfg
    raise ValueError(f"Тип документа не поддерживается: {document.__class__.__name__}")


def get_config_for_process(process) -> Optional[DocumentTypeConfig]:
    document = get_document_from_process(process)
    if document is None:
        return None
    return get_config_for_document(document)


def get_document_from_process(process):
    if process.content_type_id and process.object_id:
        return process.document
    if process.rkd_id:
        return process.rkd
    return None


def resolve_documents(doc_type: str, ids: list[int]):
    cfg = get_config_by_key(doc_type)
    return list(cfg.model.objects.filter(pk__in=ids))


def processes_for_user_q(user) -> Q:
    q = Q(started_by=user)
    for cfg in DOCUMENT_TYPES.values():
        ct = cfg.get_content_type()
        author_ids = cfg.model.objects.filter(
            **{cfg.author_field: user}
        ).values_list("pk", flat=True)
        q |= Q(content_type=ct, object_id__in=author_ids)
    q |= Q(rkd__author=user)
    return q


def user_can_view_process(user, process, *, is_admin: bool) -> bool:
    if is_admin:
        return True
    if process.started_by_id == user.id:
        return True
    document = get_document_from_process(process)
    if document is None:
        return False
    cfg = get_config_for_document(document)
    author = cfg.get_author(document)
    return author is not None and author.id == user.id


def task_doc_context(task) -> dict:
    document = get_document_from_process(task.process)
    if document is None:
        return {
            "type_label": "Документ",
            "type_key": "",
            "title": str(task.process),
            "subtitle": "",
            "file_url": "",
            "admin_url": "",
        }
    cfg = get_config_for_document(document)
    subtitle = cfg.get_subtitle(document)
    return {
        "type_label": cfg.label,
        "type_key": cfg.key,
        "title": cfg.get_title(document) or str(document),
        "subtitle": subtitle,
        "file_url": cfg.get_file_url(document),
        "admin_url": cfg.get_admin_url(document),
    }


def signer_department_label(user) -> str:
    """Отдел подписанта берём из его профиля (EmployeeProfile.org_department).

    В ЛУ/ЛО пишем именно отдел текущего пользователя, который подписывает,
    а не роль из маршрута.
    """
    if not user:
        return ""
    profile = getattr(user, "profile", None)
    department = getattr(profile, "org_department", None)
    return str(department) if department else ""
