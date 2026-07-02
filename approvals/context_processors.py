from django.db.models import Q
from django.urls import reverse

from .models import ApprovalTask, Notification


def cabinet_badge(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    tasks_count = ApprovalTask.objects.filter(
        assigned_to=user, status=ApprovalTask.STATUS_PENDING
    ).count()
    unread_count = Notification.objects.filter(
        recipient=user, is_read=False
    ).count()

    try:
        cabinet_url = reverse("admin:approvals_cabinet")
    except Exception:
        cabinet_url = ""

    return {
        "cabinet_url": cabinet_url,
        "cabinet_tasks_count": tasks_count,
        "cabinet_unread_count": unread_count,
        "cabinet_total_count": tasks_count + unread_count,
    }
