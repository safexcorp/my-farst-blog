from django.contrib.auth import get_user_model

from django.contrib.contenttypes.models import ContentType

from django.db import transaction

from django.urls import reverse

from django.utils import timezone



from .document_types import (

    get_config_for_document,

    get_document_from_process,

    signer_department_label,

)

from .models import (

    ApprovalProcess,

    ApprovalSheetRecord,

    ApprovalTask,

    DepartmentMember,

    Notification,

    Vacation,

)





def notify(recipient, title, *, text="", url="", kind=Notification.KIND_INFO):

    if recipient is None:

        return None

    return Notification.objects.create(

        recipient=recipient, title=title, text=text, url=url, kind=kind,

    )





def _cabinet_url():

    return reverse("admin:approvals_cabinet")




def _rkd_role_for_department(department):
    """Подбираем код роли для подписи РКД (UniversalRKDSignature.role).

    Роль РКД нужна только как ключ строки подписи в ГОСТ-листе РКД.
    Берём из совпадения названия роли (Department.name) со справочником ролей;
    если совпадения нет — используем код/усечённое имя роли, чтобы строки
    разных ролей не перезаписывали друг друга.
    """
    from .models import SIGNATURE_ROLE_CHOICES

    if not department:
        return "agreed"
    key_by_label = {label: key for key, label in SIGNATURE_ROLE_CHOICES}
    name = (department.name or "").strip()
    if name in key_by_label:
        return key_by_label[name]
    return (department.code or name or "agreed")[:20]





def is_on_vacation(user, on_date=None):

    if user is None:

        return False

    on_date = on_date or timezone.localdate()

    return Vacation.objects.filter(

        user=user, start_date__lte=on_date, end_date__gte=on_date

    ).exists()





def resolve_assignee(department, on_date=None):

    on_date = on_date or timezone.localdate()

    members = list(

        DepartmentMember.objects.filter(department=department)

        .select_related("user")

        .order_by("-is_main", "order")

    )

    if not members:

        return None

    for member in members:

        if not is_on_vacation(member.user, on_date):

            return member.user

    return members[0].user




def _step_target_label(step):
    """Текстовое описание адресата шага для уведомлений/журнала."""
    from .models import ApprovalRouteStep

    if step.target_type == ApprovalRouteStep.TARGET_ALL:
        return "все сотрудники"
    if step.target_type == ApprovalRouteStep.TARGET_HEADS:
        return "руководители отделов"
    if step.target_type == ApprovalRouteStep.TARGET_DEPARTMENT:
        return f"отдел «{step.org_department}»" if step.org_department_id else "отдел (не указан)"
    return f"роль «{step.department}»" if step.department_id else "роль (не указана)"


def _resolve_step_users(step, on_date=None):
    """Список пользователей-адресатов шага.

    - По роли: один ответственный с учётом отпусков (как раньше).
    - Весь отдел / Все / Руководители: рассылка всем сразу (для ознакомления).
    """
    from .models import ApprovalRouteStep
    from shared_repository.models import EmployeeProfile

    on_date = on_date or timezone.localdate()
    User = get_user_model()

    if step.target_type == ApprovalRouteStep.TARGET_ALL:
        return list(User.objects.filter(is_active=True).order_by("last_name", "username"))

    if step.target_type == ApprovalRouteStep.TARGET_HEADS:
        return list(
            User.objects.filter(is_active=True, profile__org_level=EmployeeProfile.ORG_LEVEL_LINE_MANAGER)
            .order_by("last_name", "username")
        )

    if step.target_type == ApprovalRouteStep.TARGET_DEPARTMENT:
        if not step.org_department_id:
            return []
        return list(
            User.objects.filter(is_active=True, profile__org_department_id=step.org_department_id)
            .order_by("last_name", "username")
        )

    # TARGET_ROLE
    if not step.department_id:
        return []
    assignee = resolve_assignee(step.department, on_date)
    return [assignee] if assignee else []





def _document_label(document) -> str:

    cfg = get_config_for_document(document)

    title = cfg.get_title(document)

    return f"{cfg.label}: {title}"





class ApprovalEngine:

    @staticmethod

    @transaction.atomic

    def start(document, route, user, comment=""):

        cfg = get_config_for_document(document)

        ct = ContentType.objects.get_for_model(document)



        if not route.steps.exists():

            raise ValueError("В выбранном маршруте нет шагов.")

        if ApprovalProcess.objects.filter(

            content_type=ct,

            object_id=document.pk,

            status=ApprovalProcess.STATUS_IN_PROGRESS,

        ).exists():

            raise ValueError("По этому документу уже идёт согласование.")

        if not cfg.has_main_file(document):

            raise ValueError(cfg.no_file_message)



        empty_targets = []

        for step in route.steps.order_by("order"):

            if not _resolve_step_users(step):

                empty_targets.append(step.target_label)

        if empty_targets:

            raise ValueError(

                f"Для шагов маршрута не найдено адресатов: {', '.join(empty_targets)}."

            )



        first_step = route.steps.order_by("order").first()

        process_kwargs = {

            "content_type": ct,

            "object_id": document.pk,

            "route": route,

            "started_by": user,

            "current_order": first_step.order,

            "status": ApprovalProcess.STATUS_IN_PROGRESS,

        }

        if cfg.key == "rkd":

            process_kwargs["rkd"] = document



        process = ApprovalProcess.objects.create(**process_kwargs)

        ApprovalEngine._create_step_tasks(process, first_step, launch_comment=comment)



        author = cfg.get_author(document)

        doc_label = _document_label(document)

        if author and author != user:

            notify(

                author,

                f"По вашему документу запущено согласование ({cfg.label})",

                text=f"«{doc_label}» — маршрут «{route}».",

                url=_cabinet_url(),

                kind=Notification.KIND_INFO,

            )

        return process



    @staticmethod

    def _create_step_tasks(process, step, *, is_recheck=False, parent=None, launch_comment=""):
        """Создаёт задачи для шага маршрута.

        Для адресата «по роли» — одна задача (с учётом отпусков).
        Для «весь отдел / все / руководители» — задачи всем сразу (параллельно).
        """
        process.current_order = step.order
        process.save(update_fields=["current_order"])

        document = get_document_from_process(process)
        cfg = get_config_for_document(document)
        doc_label = _document_label(document)

        is_sign = step.action_type == step.ACTION_SIGN
        prefix = "Повторно: " if is_recheck else ""
        action = "на согласование / подпись" if is_sign else "на ознакомление"
        target_label = _step_target_label(step)
        note_text = f"«{doc_label}» — {target_label}."
        if launch_comment.strip():
            note_text += f" Комментарий: {launch_comment.strip()}"

        seen, first_task = set(), None
        for assignee in _resolve_step_users(step):
            if assignee is None or assignee.pk in seen:
                continue
            seen.add(assignee.pk)
            task = ApprovalTask.objects.create(
                process=process,
                step=step,
                department=step.department,
                kind=ApprovalTask.KIND_REVIEW,
                assigned_to=assignee,
                is_recheck=is_recheck,
                parent=parent,
            )
            first_task = first_task or task
            notify(
                assignee,
                f"{prefix}{cfg.label} {action}",
                text=note_text,
                url=_cabinet_url(),
                kind=Notification.KIND_SIGN if is_sign else Notification.KIND_ACK,
            )

        if first_task is None:
            # Никого не удалось определить — создаём незанятую задачу,
            # чтобы шаг был виден администратору, а не «пропал» молча.
            first_task = ApprovalTask.objects.create(
                process=process,
                step=step,
                department=step.department,
                kind=ApprovalTask.KIND_REVIEW,
                assigned_to=None,
                is_recheck=is_recheck,
                parent=parent,
            )
        return first_task



    @staticmethod

    @transaction.atomic

    def approve(task, user, cert_info=None):

        ApprovalEngine._guard_pending_review(task)



        if task.step and task.step.action_type == task.step.ACTION_SIGN:

            ApprovalEngine._record_signature(task, user, cert_info=cert_info)

        elif task.step and task.step.action_type == task.step.ACTION_ACK:

            ApprovalEngine._record_acknowledgment(task, user, cert_info=cert_info)



        task.status = ApprovalTask.STATUS_APPROVED

        task.resolved_at = timezone.now()

        task.save(update_fields=["status", "resolved_at"])



        process = task.process

        document = get_document_from_process(process)

        cfg = get_config_for_document(document)

        doc_label = _document_label(document)



        siblings_pending = (

            ApprovalTask.objects

            .filter(

                process=process,

                step=task.step,

                kind=ApprovalTask.KIND_REVIEW,

                status=ApprovalTask.STATUS_PENDING,

            )

            .exclude(pk=task.pk)

            .exists()

        )

        if siblings_pending:

            return process



        next_step = (

            process.route.steps

            .filter(order__gt=task.step.order)

            .order_by("order")

            .first()

        )

        if next_step:

            ApprovalEngine._create_step_tasks(process, next_step)

        else:

            process.status = ApprovalProcess.STATUS_APPROVED

            process.finished_at = timezone.now()

            process.save(update_fields=["status", "finished_at"])

            recipient = cfg.get_author(document) or process.started_by

            notify(

                recipient,

                f"{cfg.label}: документ полностью согласован",

                text=f"«{doc_label}» прошёл все шаги маршрута.",

                url=_cabinet_url(),

                kind=Notification.KIND_INFO,

            )

        return process



    @staticmethod

    @transaction.atomic

    def reject(task, user, comment):

        ApprovalEngine._guard_pending_review(task)

        comment = (comment or "").strip()

        if not comment:

            raise ValueError("Укажите замечание для автора.")



        document = get_document_from_process(task.process)

        cfg = get_config_for_document(document)

        doc_label = _document_label(document)



        task.status = ApprovalTask.STATUS_REJECTED

        task.comment = comment

        task.resolved_at = timezone.now()

        task.save(update_fields=["status", "comment", "resolved_at"])



        author = cfg.get_author(document) or task.process.started_by

        if author is None:

            raise ValueError(

                "У документа не указан автор — некому отправить на доработку."

            )



        ApprovalTask.objects.create(

            process=task.process,

            step=task.step,

            department=task.department,

            kind=ApprovalTask.KIND_FIX,

            assigned_to=author,

            comment=comment,

            parent=task,

        )

        notify(

            author,

            f"{cfg.label}: документ вернули на доработку",

            text=f"«{doc_label}» — отдел «{task.department}». Замечание: {comment}",

            url=_cabinet_url(),

            kind=Notification.KIND_FIX,

        )

        return task



    @staticmethod

    @transaction.atomic

    def resubmit(fix_task, user):

        if fix_task.kind != ApprovalTask.KIND_FIX:

            raise ValueError("Это не задача на доработку.")

        if fix_task.status != ApprovalTask.STATUS_PENDING:

            raise ValueError("Эта задача на доработку уже закрыта.")



        fix_task.status = ApprovalTask.STATUS_DONE

        fix_task.resolved_at = timezone.now()

        fix_task.save(update_fields=["status", "resolved_at"])



        ApprovalEngine._create_step_tasks(

            fix_task.process, fix_task.step, is_recheck=True, parent=fix_task

        )

        return fix_task



    @staticmethod

    @transaction.atomic

    def cancel(process, user):

        if process.status != ApprovalProcess.STATUS_IN_PROGRESS:

            raise ValueError("Согласование уже завершено или отменено.")

        process.tasks.filter(status=ApprovalTask.STATUS_PENDING).update(

            status=ApprovalTask.STATUS_CANCELLED,

            resolved_at=timezone.now(),

        )

        process.status = ApprovalProcess.STATUS_CANCELLED

        process.finished_at = timezone.now()

        process.save(update_fields=["status", "finished_at"])



        document = get_document_from_process(process)

        cfg = get_config_for_document(document)

        doc_label = _document_label(document)

        recipient = cfg.get_author(document) or process.started_by

        if recipient:

            notify(

                recipient,

                f"{cfg.label}: согласование отменено",

                text=f"«{doc_label}» — маршрут «{process.route}».",

                url=_cabinet_url(),

                kind=Notification.KIND_INFO,

            )

        return process



    @staticmethod

    def _record_signature(task, user, cert_info=None):

        document = get_document_from_process(task.process)

        cfg = get_config_for_document(document)

        cert_cn = cert_info.get("cn", "") if cert_info else ""

        cert_issuer = cert_info.get("issuer_cn", "") if cert_info else ""

        position = signer_department_label(user)



        if cfg.key == "rkd":

            from blog.models import UniversalRKDSignature



            role = _rkd_role_for_department(task.department)

            UniversalRKDSignature.objects.update_or_create(

                rkd=document,

                role=role,

                defaults={

                    "signed_by": user,

                    "signed_at": timezone.localdate(),

                    "cert_cn": cert_cn,

                    "cert_issuer": cert_issuer,

                },

            )

        else:

            ct = ContentType.objects.get_for_model(document)

            ApprovalSheetRecord.objects.update_or_create(

                task=task,

                defaults={

                    "process": task.process,

                    "sheet_type": ApprovalSheetRecord.SHEET_APPROVAL,

                    "content_type": ct,

                    "object_id": document.pk,

                    "department": task.department,

                    "position": position,

                    "role_label": str(task.department) if task.department else "",

                    "signed_by": user,

                    "signed_at": timezone.localdate(),

                    "cert_cn": cert_cn,

                    "cert_issuer": cert_issuer,

                    "step_order": task.step.order if task.step else 0,

                },

            )



        try:

            from .sheet_service import generate_approval_sheet

            generate_approval_sheet(document, task.process)

        except Exception:

            pass



    @staticmethod

    def _record_acknowledgment(task, user, cert_info=None):

        document = get_document_from_process(task.process)

        cfg = get_config_for_document(document)

        process = task.process

        cert_cn = cert_info.get("cn", "") if cert_info else ""

        cert_issuer = cert_info.get("issuer_cn", "") if cert_info else ""

        position = signer_department_label(user)



        if cfg.key == "rkd":

            from blog.models import UniversalRKDAcknowledgment



            UniversalRKDAcknowledgment.objects.update_or_create(

                task=task,

                defaults={

                    "rkd": document,

                    "process": process,

                    "department": task.department,

                    "position": position,

                    "signed_by": user,

                    "signed_at": timezone.localdate(),

                    "cert_cn": cert_cn,

                    "cert_issuer": cert_issuer,

                    "step_order": task.step.order if task.step else 0,

                },

            )

        else:

            ct = ContentType.objects.get_for_model(document)

            ApprovalSheetRecord.objects.update_or_create(

                task=task,

                defaults={

                    "process": process,

                    "sheet_type": ApprovalSheetRecord.SHEET_ACQUAINTANCE,

                    "content_type": ct,

                    "object_id": document.pk,

                    "department": task.department,

                    "position": position,

                    "role_label": "",

                    "signed_by": user,

                    "signed_at": timezone.localdate(),

                    "cert_cn": cert_cn,

                    "cert_issuer": cert_issuer,

                    "step_order": task.step.order if task.step else 0,

                },

            )



        try:

            from .sheet_service import generate_acquaintance_sheet

            generate_acquaintance_sheet(document, process)

        except Exception:

            pass



    @staticmethod

    def _guard_pending_review(task):

        if task.kind != ApprovalTask.KIND_REVIEW:

            raise ValueError("Действие доступно только для задач проверки.")

        if task.status != ApprovalTask.STATUS_PENDING:

            raise ValueError("Эта задача уже обработана.")


