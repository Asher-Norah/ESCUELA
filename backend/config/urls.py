from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from accounts.views import LoginView, MeView, health
from school.api_views import (
    ClassAttendanceView,
    ScoreEntryView,
    StudentAttendanceView,
    StudentPerformanceView,
    StudentReportCardsView,
)
from school.parent_views import ParentSignUpView
from school.views import StudentActivateView, StudentLookupView
from school.parent_api import ParentChildrenView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/me/", MeView.as_view()),
    path("api/auth/student/lookup/", StudentLookupView.as_view()),
    path("api/auth/student/activate/", StudentActivateView.as_view()),
    path("api/auth/parent/signup/", ParentSignUpView.as_view()),
    path("api/student/attendance/", StudentAttendanceView.as_view()),
    path("api/student/performance/", StudentPerformanceView.as_view()),
    path("api/student/report-cards/", StudentReportCardsView.as_view()),
    path("api/teacher/scores/", ScoreEntryView.as_view()),
    path("api/teacher/attendance/", ClassAttendanceView.as_view()),
    path("api/parent/children/", ParentChildrenView.as_view()),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)