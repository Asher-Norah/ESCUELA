from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_api import IsAdminUser
from .models import Class, TeacherProfile, TeachingAssignment
from .phone import normalise_kenyan_phone

User = get_user_model()

STATUSES = {"pending", "approved", "rejected"}
UNIQUE_FIELDS = {
    "employee_number": "employee number",
    "tsc_number": "TSC number",
    "national_id": "ID number",
}
TEXT_FIELDS = ["address", "bank_name", "bank_account"]


def photo_url(request, user):
    return request.build_absolute_uri(user.profile_image.url) if user.profile_image else ""


def assignments_of(user):
    return (
        TeachingAssignment.objects.filter(teacher=user)
        .select_related("class_group", "subject")
        .order_by("class_group__name", "subject__name")
    )


def classes_taught(user):
    grouped = {}
    for a in assignments_of(user):
        grouped.setdefault(a.class_group.name, []).append(a.subject.name)
    return [{"name": name, "subjects": subjects} for name, subjects in grouped.items()]


def summary(request, user):
    profile = getattr(user, "teacher_profile", None)
    return {
        "id": user.pk,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "approval_status": user.approval_status,
        "employee_number": profile.employee_number if profile else "",
        "tsc_number": profile.tsc_number if profile else "",
        "photo": photo_url(request, user),
        "classes": classes_taught(user),
        "class_teacher_of": [c.name for c in Class.objects.filter(class_teacher=user).order_by("name")],
    }


def detail(request, user):
    profile = getattr(user, "teacher_profile", None)
    data = summary(request, user)
    data.update({
        "date_joined": user.date_joined.date().isoformat(),
        "date_of_birth": profile.date_of_birth.isoformat() if profile else "",
        "national_id": profile.national_id if profile else "",
        "address": profile.address if profile else "",
        "bank_name": profile.bank_name if profile else "",
        "bank_account": profile.bank_account if profile else "",
        "consent_given": profile.consent_given if profile else False,
        "consent_at": profile.consent_at.date().isoformat() if profile and profile.consent_at else "",
        "assignments": [
            {"id": a.pk, "class_name": a.class_group.name, "subject_name": a.subject.name}
            for a in assignments_of(user)
        ],
    })
    return data


class TeacherAdminListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        teachers = User.objects.filter(role="teacher").select_related("teacher_profile").order_by("full_name")
        return Response([summary(request, u) for u in teachers])


class TeacherAdminDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get_teacher(self, pk):
        return User.objects.select_related("teacher_profile").filter(pk=pk, role="teacher").first()

    def get(self, request, pk):
        user = self.get_teacher(pk)
        if user is None:
            return Response({"detail": "Teacher not found."}, status=404)
        return Response(detail(request, user))

    def patch(self, request, pk):
        user = self.get_teacher(pk)
        if user is None:
            return Response({"detail": "Teacher not found."}, status=404)
        data = request.data

        # Check everything first, so a bad field doesn't leave the account half-updated.
        if "approval_status" in data and str(data["approval_status"]).strip() not in STATUSES:
            return Response({"detail": "Choose pending, approved or rejected."}, status=400)

        if "full_name" in data and not str(data["full_name"]).strip():
            return Response({"detail": "Enter the teacher's full name."}, status=400)

        phone = None
        if "phone" in data:
            phone = normalise_kenyan_phone(str(data["phone"]))
            if phone is None:
                return Response(
                    {"detail": "Enter a valid Kenyan phone number, such as 0712345678."}, status=400
                )

        email = None
        if "email" in data:
            email = str(data["email"]).strip().lower()
            if not email:
                return Response({"detail": "Enter an email address."}, status=400)
            taken = User.objects.filter(Q(username=email) | Q(email__iexact=email)).exclude(pk=user.pk)
            if taken.exists():
                return Response({"detail": "This email is already used by another account."}, status=400)

        profile = getattr(user, "teacher_profile", None)
        if profile is not None:
            for field, label in UNIQUE_FIELDS.items():
                if field in data:
                    value = str(data[field]).strip()
                    if not value:
                        return Response({"detail": f"Enter the {label}."}, status=400)
                    if TeacherProfile.objects.filter(**{field: value}).exclude(pk=profile.pk).exists():
                        return Response(
                            {"detail": f"Another teacher already has this {label}."}, status=400
                        )

        # All checks passed. Now save.
        if "approval_status" in data:
            user.approval_status = str(data["approval_status"]).strip()
        if "full_name" in data:
            user.full_name = str(data["full_name"]).strip()
        if phone is not None:
            user.phone = phone
        if email is not None:
            user.email = email
            user.username = email  # teachers log in with their email, so keep the two in step
        user.save()

        if profile is not None:
            for field in UNIQUE_FIELDS:
                if field in data:
                    setattr(profile, field, str(data[field]).strip())
            for field in TEXT_FIELDS:
                if field in data:
                    setattr(profile, field, str(data[field]).strip())
            profile.save()

        return Response(detail(request, user))