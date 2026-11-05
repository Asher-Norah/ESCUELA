from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from accounts.password_reset import PasswordResetConfirmView, PasswordResetRequestView
from accounts.views import LoginView, MeView, health
from school.admin_api import (
    AdminClassDetailView,
    AdminClassListView,
    AdminClassOverviewView,
    AdminGradeLevelListView,
    AdminGuardianDetailView,
    AdminGuardianListView,
    AdminStudentDetailView,
    AdminStudentListView,
    AdminStudentOverviewView,
)
from school.admin_parent_api import (
    AdminParentChildDetailView,
    AdminParentChildrenView,
    AdminParentDetailView,
    AdminParentListView,
    AdminSetPasswordView,
)
from school.api_views import (
    ClassAttendanceView,
    ScoreEntryView,
    StudentAttendanceView,
    StudentPerformanceView,
    StudentReportCardsView,
)
from school.exam_api import (
    AdminExamDetailView,
    AdminExamListView,
    AdminTermDetailView,
    AdminTermListView,
)
from school.parent_api import ParentChildrenView
from school.parent_views import ParentSignUpView
from school.subject_api import (
    AdminAssignmentDetailView,
    AdminAssignmentListView,
    AdminSubjectDetailView,
    AdminSubjectListView,
)
from school.teacher_admin_api import TeacherAdminDetailView, TeacherAdminListView
from school.teacher_api import TeacherSignUpView
from school.teacher_dashboard_api import (
    TeacherClassDetailView,
    TeacherClassMarksView,
    TeacherOverviewView,
)
from school.views import StudentActivateView, StudentLookupView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/me/", MeView.as_view()),
    path("api/auth/password-reset/", PasswordResetRequestView.as_view()),
    path("api/auth/password-reset/confirm/", PasswordResetConfirmView.as_view()),
    path("api/auth/student/lookup/", StudentLookupView.as_view()),
    path("api/auth/student/activate/", StudentActivateView.as_view()),
    path("api/auth/parent/signup/", ParentSignUpView.as_view()),
    path("api/auth/teacher/signup/", TeacherSignUpView.as_view()),
    path("api/parent/children/", ParentChildrenView.as_view()),
    path("api/student/attendance/", StudentAttendanceView.as_view()),
    path("api/student/performance/", StudentPerformanceView.as_view()),
    path("api/student/report-cards/", StudentReportCardsView.as_view()),
    path("api/teacher/overview/", TeacherOverviewView.as_view()),
    path("api/teacher/class-detail/", TeacherClassDetailView.as_view()),
    path("api/teacher/class-marks/", TeacherClassMarksView.as_view()),
    path("api/teacher/scores/", ScoreEntryView.as_view()),
    path("api/teacher/attendance/", ClassAttendanceView.as_view()),
    path("api/admin/grade-levels/", AdminGradeLevelListView.as_view()),
    path("api/admin/teacher-accounts/", TeacherAdminListView.as_view()),
    path("api/admin/teacher-accounts/<int:pk>/", TeacherAdminDetailView.as_view()),
    path("api/admin/classes/", AdminClassListView.as_view()),
    path("api/admin/classes/<int:pk>/", AdminClassDetailView.as_view()),
    path("api/admin/classes/<int:pk>/overview/", AdminClassOverviewView.as_view()),
    path("api/admin/students/", AdminStudentListView.as_view()),
    path("api/admin/students/<int:pk>/", AdminStudentDetailView.as_view()),
    path("api/admin/students/<int:pk>/overview/", AdminStudentOverviewView.as_view()),
    path("api/admin/guardians/", AdminGuardianListView.as_view()),
    path("api/admin/guardians/<int:pk>/", AdminGuardianDetailView.as_view()),
    path("api/admin/subjects/", AdminSubjectListView.as_view()),
    path("api/admin/subjects/<int:pk>/", AdminSubjectDetailView.as_view()),
    path("api/admin/assignments/", AdminAssignmentListView.as_view()),
    path("api/admin/assignments/<int:pk>/", AdminAssignmentDetailView.as_view()),
    path("api/admin/terms/", AdminTermListView.as_view()),
    path("api/admin/terms/<int:pk>/", AdminTermDetailView.as_view()),
    path("api/admin/exams/", AdminExamListView.as_view()),
    path("api/admin/exams/<int:pk>/", AdminExamDetailView.as_view()),
    path("api/admin/parents/", AdminParentListView.as_view()),
    path("api/admin/parents/<int:pk>/", AdminParentDetailView.as_view()),
    path("api/admin/parents/<int:pk>/children/", AdminParentChildrenView.as_view()),
    path("api/admin/parents/<int:pk>/children/<int:sid>/", AdminParentChildDetailView.as_view()),
    path("api/admin/users/<int:pk>/set-password/", AdminSetPasswordView.as_view()),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)