from django.contrib.contenttypes.models import ContentType

from django.db import transaction

from django.urls import reverse

from django.utils import timezone



from .document_types import (

    get_config_for_document,

    get_document_from_process,

    role_label_for_department,

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





def _document_label(document) -> str:

    cfg = get_config_for_document(document)

    title = cfg.get_title(document)

    return f"{cfg.label}: {title}"





class ApprovalEngine:

    @staticmethod

    @transaction.atomic

    def start(document, route, user):

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



        empty_depts = []

        for step in route.steps.select_related("department").order_by("order"):

            if not DepartmentMember.objects.filter(department=step.department).exists():

                empty_depts.append(str(step.department))

        if empty_depts:

            raise ValueError(

                f"В отделах нет сотрудников, задача некому назначить: {', '.join(empty_depts)}."

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

        ApprovalEngine._create_review_task(process, first_step)



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

    def _create_review_task(process, step, *, is_recheck=False, parent=None):

        assignee = resolve_assignee(step.department)

        process.current_order = step.order

        process.save(update_fields=["current_order"])



        document = get_document_from_process(process)

        cfg = get_config_for_document(document)

        doc_label = _document_label(document)



        task = ApprovalTask.objects.create(

            process=process,

            step=step,

            department=step.department,

            kind=ApprovalTask.KIND_REVIEW,

            assigned_to=assignee,

            is_recheck=is_recheck,

            parent=parent,

        )

        is_sign = step.action_type == step.ACTION_SIGN

        prefix = "Повторно: " if is_recheck else ""

        action = "на согласование / подпись" if is_sign else "на ознакомление"

        notify(

            assignee,

            f"{prefix}{cfg.label} {action}",

            text=f"«{doc_label}» — отдел «{step.department}».",

            url=_cabinet_url(),

            kind=Notification.KIND_SIGN if is_sign else Notification.KIND_ACK,

        )

        return task



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



        next_step = (

            process.route.steps

            .filter(order__gt=task.step.order)

            .order_by("order")

            .first()

        )

        if next_step:

            ApprovalEngine._create_review_task(process, next_step)

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



        ApprovalEngine._create_review_task(

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

        role_label = role_label_for_department(task.department)

        position = str(task.department) if task.department else role_label



        if cfg.key == "rkd":

            from blog.models import UniversalRKDSignature



            role = (task.department and task.department.signature_role) or "agreed"

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

                    "position": role_label,

                    "role_label": role_label,

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

        position = str(task.department) if task.department else ""



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


