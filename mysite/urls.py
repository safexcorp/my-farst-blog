"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from blog.views import (
    decision_makers_by_customer_json,
    incoming_letter_sender_for_reply_json,
)
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.conf import settings
from django.conf.urls.static import static

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')  # или куда перенаправить
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

urlpatterns = [
    path(
        "crm/api/decision-makers-by-customer/",
        decision_makers_by_customer_json,
        name="crm_decision_makers_by_customer",
    ),
    path(
        "crm/api/incoming-letter-sender/",
        incoming_letter_sender_for_reply_json,
        name="crm_incoming_letter_sender_for_reply",
    ),
    path('admin/', admin.site.urls),
    path('register/', register, name='register'),  # маршрут регистрации
    path('login/', auth_views.LoginView.as_view(), name='login'),  # если нужно логин
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),  # и логаут
]

from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
