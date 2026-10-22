from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from accounts.views import LoginView, MeView, health
from school.views import StudentActivateView, StudentLookupView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/me/", MeView.as_view()),
    path("api/auth/student/lookup/", StudentLookupView.as_view()),
    path("api/auth/student/activate/", StudentActivateView.as_view()),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)