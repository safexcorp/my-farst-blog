import json
from typing import Optional
from django.contrib.auth import get_user_model

User = get_user_model()

# сопоставляем коду процесса (Process.code) поля в CheckDocumentWorkflow:
#  - кто отвечает за шаг (FK на User)
#  - булевый флаг "шаг подписан/подтверждён"
#  - поле для комментария/причины возврата
PROCESS_FIELD_MAP = {
    "it_requirements": {
        "responsible": "check_it_requirements_responsible",         # FK User
        "signature": "check_it_requirements_signature",             # Bool
        "comment": "check_it_requirements_comment",                 # Text
    },
    "tech_requirements": {
        "responsible": "check_technical_requirements_responsible",
        "signature": "check_technical_requirements_signature",
        "comment": "check_technical_requirements_comment",
    },
    "norm_control": {
        "responsible": "norm_control_responsible",
        "signature": "norm_control_signature",
        "comment": "norm_control_comment",
    },
    "3D_model": {
        "responsible": "3D_model_responsible",
        "signature": "3D_model_signature",
        "comment": "3D_model_comment",
    },
}


def wf_step_is_signed(wf, process_code: str) -> bool:
    """возвращает True, если текущий шаг (по коду процесса) уже подписан (…_signature=True)"""
    cfg = PROCESS_FIELD_MAP.get(process_code)
    if not cfg:
        return False
    return bool(getattr(wf, cfg["signature"], False))


def wf_step_responsible(wf, process_code: str) -> Optional[User]:
    """даёт ответственного (User) для шага (по коду процесса)"""
    cfg = PROCESS_FIELD_MAP.get(process_code)
    if not cfg:
        return None
    return getattr(wf, cfg["responsible"], None)


def wf_step_set_comment(wf, process_code: str, text: str) -> None:
    """записывает причину возврата в поле комментария соответствующего шага"""
    cfg = PROCESS_FIELD_MAP.get(process_code)
    if not cfg:
        return
    setattr(wf, cfg["comment"], text or "")


def first_incomplete_step_code(route, wf) -> Optional[str]:
    """
    берём шаги маршрута по порядку (RouteProcess.order) и ищем первый НЕподтверждённый.
    если всё подтверждено — возвращаем None.
    """
    if not wf or not route:
        return None
    for rp in route.routeprocess_set.select_related("process").order_by("order"):
        code = rp.process.code
        if not wf_step_is_signed(wf, code):
            return code
    return None


def next_step_code_after(route, current_code: str) -> Optional[str]:
    """даёт код следующего шага после current_code в рамках данного маршрута"""
    if not route or not current_code:
        return None
    ordered_codes = [
        rp.process.code
        for rp in route.routeprocess_set.select_related("process").order_by("order")
    ]
    try:
        i = ordered_codes.index(current_code)
    except ValueError:
        return None
    return ordered_codes[i + 1] if i + 1 < len(ordered_codes) else None


# РКД: разделы спецификации, коды вида документа; словарь для JS (категория от раздела).

SPECIFICATION_SECTION_ORDER: tuple[str, ...] = (
    "documentation",
    "complexes",
    "assembly_units",
    "parts",
    "standard_products",
    "other_products",
    "materials",
    "kits",
    "other_kits",
)

SPECIFICATION_SECTION_CHOICES: tuple[tuple[str, str], ...] = (
    ("documentation", "Документация"),
    ("complexes", "Комплексы"),
    ("assembly_units", "Сборочные единицы"),
    ("parts", "Детали"),
    ("standard_products", "Стандартные изделия"),
    ("other_products", "Прочие изделия"),
    ("materials", "Материалы"),
    ("kits", "Комплекты"),
    ("other_kits", "Прочие комплекты"),
)

_CATEGORY_DOCUMENTATION: tuple[str, ...] = (
    "СП",
    "СБ",
    "ЭМИ",
    "ГЧ",
    "Э3",
    "ПЭ3",
    "ТУ",
    "РЭ",
    "ПС",
    "ПМ",
    "УЧ",
    "ПК",
    "ВМ",
    "ВП",
    "ИС",
    "РР",
    "РК",
)

RKD_CATEGORY_BY_SECTION: dict[str, tuple[str, ...]] = {
    "documentation": _CATEGORY_DOCUMENTATION,
}

POSITION_EDITABLE_SECTIONS: frozenset[str] = frozenset(
    {
        "assembly_units",
        "parts",
        "standard_products",
        "other_products",
        "materials",
    }
)


def rkd_category_by_section_json() -> str:
    """JSON для JS в админке (зависимый select «Категория»)."""
    return json.dumps({k: list(v) for k, v in RKD_CATEGORY_BY_SECTION.items()}, ensure_ascii=False)


def specification_section_sort_index(code: str) -> int:
    try:
        return SPECIFICATION_SECTION_ORDER.index(code)
    except ValueError:
        return len(SPECIFICATION_SECTION_ORDER)


def allowed_categories_for_section(section: str) -> frozenset[str]:
    return frozenset(RKD_CATEGORY_BY_SECTION.get(section, ()))


def section_has_category_choices(section: str) -> bool:
    return bool(RKD_CATEGORY_BY_SECTION.get(section, ()))


def section_allows_position(section: str) -> bool:
    return section in POSITION_EDITABLE_SECTIONS


WA_CODE_LENGTH = 3
_WA_CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _wa_index_to_code(index: int) -> str:
    """0 → 'AAA', 1 → 'AAB', 26 → 'ABA', и т.д."""
    n = len(_WA_CODE_ALPHABET)
    chars = []
    for _ in range(WA_CODE_LENGTH):
        index, r = divmod(index, n)
        chars.append(_WA_CODE_ALPHABET[r])
    return "".join(reversed(chars))


def _wa_code_to_index(code: str) -> int:
    n = len(_WA_CODE_ALPHABET)
    idx = 0
    for ch in code:
        idx = idx * n + _WA_CODE_ALPHABET.index(ch)
    return idx


def next_free_wa_code(taken_codes) -> str:
    taken = set(taken_codes or ())
    max_idx = len(_WA_CODE_ALPHABET) ** WA_CODE_LENGTH
    for i in range(max_idx):
        code = _wa_index_to_code(i)
        if code not in taken:
            return code
    raise RuntimeError("Свободные буквенные коды для рабочих заданий закончились.")


def assign_wa_code_to_post(post) -> str:
    if getattr(post, "wa_code", None):
        return post.wa_code
    Post = post.__class__
    taken = Post.objects.exclude(pk=post.pk).exclude(wa_code__isnull=True).values_list("wa_code", flat=True)
    code = next_free_wa_code(taken)
    post.wa_code = code
    Post.objects.filter(pk=post.pk).update(wa_code=code)
    return code


def next_wa_number_for_post(post, exclude_pk=None) -> int:
    from django.db.models import Max
    from .models import WorkAssignment
    qs = WorkAssignment.objects.filter(post=post)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    last = qs.aggregate(m=Max("wa_number"))["m"] or 0
    return last + 1


def next_subtask_number_for_wa(work_assignment, exclude_pk=None) -> int:
    from django.db.models import Max
    from .models import WorkAssignmentSubtask
    qs = WorkAssignmentSubtask.objects.filter(work_assignment=work_assignment)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    last = qs.aggregate(m=Max("subtask_number"))["m"] or 0
    return last + 1

