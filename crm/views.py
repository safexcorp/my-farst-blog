from django.shortcuts import render

# Create your views here.
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import SupportTicket, TicketComment, KnowledgeBaseArticle
from .forms import SupportTicketForm, TicketCommentForm, KnowledgeBaseArticleForm


# ===== ЗАЯВКИ =====

@login_required
def tickets_list(request):
    qs = SupportTicket.objects.select_related(
        "customer", "product", "category", "created_by", "assigned_to"
    ).all()

    # Фильтры
    status = request.GET.get("status")
    category = request.GET.get("category")
    customer = request.GET.get("customer")
    product = request.GET.get("product")
    assigned = request.GET.get("assigned")
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")

    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category_id=category)
    if customer:
        qs = qs.filter(customer_id=customer)
    if product:
        qs = qs.filter(product_id=product)
    if assigned:
        qs = qs.filter(assigned_to_id=assigned)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Поиск
    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(id__iexact=q) |
            Q(problem__icontains=q) |
            Q(description__icontains=q) |
            Q(customer__full_name__icontains=q)
        )

    qs = qs.order_by("-created_at")

    return render(request, "crm/tickets_list.html", {
        "tickets": qs,
        "GET": request.GET,
    })


@login_required
def ticket_create(request):
    if request.method == "POST":
        form = SupportTicketForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket._created_by = request.user  # будет учтено в save()
            ticket.author = request.user
            ticket.save()
            messages.success(request, "Заявка создана.")
            return redirect("crm:tickets_list")
    else:
        form = SupportTicketForm()
    return render(request, "crm/ticket_form.html", {"form": form})


@login_required
def ticket_edit(request, pk: int):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    if request.method == "POST":
        form = SupportTicketForm(request.POST, request.FILES, instance=ticket)
        if form.is_valid():
            before = ticket.status
            ticket = form.save()
            if before != ticket.status:
                ticket.status_updated_at = timezone.now()
                ticket.save(update_fields=["status_updated_at"])
            messages.success(request, "Заявка обновлена.")
            return redirect("crm:tickets_list")
    else:
        form = SupportTicketForm(instance=ticket)

    # Комментарии + форма добавления комментария прямо на странице заявки
    comment_form = TicketCommentForm()
    comments = ticket.comments.select_related("author").all()
    return render(request, "crm/ticket_form.html", {
        "form": form,
        "ticket": ticket,
        "comment_form": comment_form,
        "comments": comments,
    })


@login_required
def ticket_add_comment(request, pk: int):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    if request.method == "POST":
        form = TicketCommentForm(request.POST, request.FILES)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.ticket = ticket
            comment.author = request.user
            comment.save()
            messages.success(request, "Комментарий добавлен.")
        else:
            messages.error(request, "Проверьте форму комментария.")
    return redirect("crm:ticket_edit", pk=ticket.pk)


# ===== БАЗА ЗНАНИЙ =====

@login_required
def kb_list(request):
    qs = KnowledgeBaseArticle.objects.select_related("category", "author").all()

    # Фильтры
    status = request.GET.get("status")
    category = request.GET.get("category")
    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category_id=category)

    # Поиск
    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(title__icontains=q) | Q(content__icontains=q)
        )

    qs = qs.order_by("-updated_at")
    return render(request, "crm/kb_list.html", {
        "articles": qs,
        "GET": request.GET,
    })


@login_required
def kb_create(request):
    if request.method == "POST":
        form = KnowledgeBaseArticleForm(request.POST, request.FILES)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            messages.success(request, "Статья создана.")
            return redirect("crm:kb_list")
    else:
        form = KnowledgeBaseArticleForm()
    return render(request, "crm/kb_form.html", {"form": form})


@login_required
def kb_edit(request, pk: int):
    article = get_object_or_404(KnowledgeBaseArticle, pk=pk)
    if request.method == "POST":
        form = KnowledgeBaseArticleForm(request.POST, request.FILES, instance=article)
        if form.is_valid():
            form.save()
            messages.success(request, "Статья обновлена.")
            return redirect("crm:kb_list")
    else:
        form = KnowledgeBaseArticleForm(instance=article)
    return render(request, "crm/kb_form.html", {"form": form, "article": article})
