"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.shortcuts import redirect
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from registration.admin import wipe_exam_data_view

def home(request):
    return redirect('candidate/login/')

urlpatterns = [
    # Custom admin tools first (must come before the main admin route)
    path("admin/wipe-data/", admin.site.admin_view(wipe_exam_data_view), name="admin_wipe_data"),
    path("admin/", admin.site.urls),
    path("", home),
    path("candidate/", include("registration.urls")),
    path("results/", include("results.urls")),
    


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
