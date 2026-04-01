from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from crm.models import Decision_maker, IncomingLetter
from .models import Post, WorkAssignment, Attachment

def product_list(request):
    products = Post.objects.all().order_by("id")[:5]
    return render(request, "products/product_list.html", {"products": products})

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # авторизовать сразу после регистрации
            return redirect('home')  # путь куда перенаправить
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def create_work_assignment(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')

        work = WorkAssignment.objects.create(title=title, description=description)

        for f in request.FILES.getlist('files'):
            Attachment.objects.create(work=work, file=f)

        return redirect('work_detail', pk=work.pk)

    return render(request, 'work/create.html')


@require_GET
def decision_makers_by_customer_json(request):
    """ЛПР по выбранному контрагенту — для формы входящего письма в админке."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"results": []}, status=403)
    raw = request.GET.get("customer_id")
    if not raw:
        return JsonResponse({"results": []})
    try:
        customer_id = int(raw)
    except (TypeError, ValueError):
        return JsonResponse({"results": []})
    qs = Decision_maker.objects.filter(customer_id=customer_id).order_by("full_name", "id")
    results = [{"id": str(r.id), "text": str(r)} for r in qs]
    return JsonResponse({"results": results})


@require_GET
def incoming_letter_sender_for_reply_json(request):
    """Отправитель входящего письма — для автоподстановки получателя в исходящем (админка)."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"sender_id": None}, status=403)
    raw = request.GET.get("incoming_letter_id")
    if not raw:
        return JsonResponse({"sender_id": None})
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return JsonResponse({"sender_id": None})
    il = (
        IncomingLetter.objects.filter(pk=pk)
        .select_related("sender")
        .first()
    )
    if not il or not il.sender_id:
        return JsonResponse({"sender_id": None})
    return JsonResponse(
        {
            "sender_id": str(il.sender_id),
            "sender_label": str(il.sender),
        }
    )
