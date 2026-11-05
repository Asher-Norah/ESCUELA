import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_api import IsAdminUser
from .models import Class, TeacherProfile, TeachingAssignment
from .phone import normalise_kenyan_phone

User = get_user_model()

MAX_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png"}
APPROVAL_STATUSES = {"pending", "approved", "rejected"}
TRUTHY = {"true", "on", "1", "yes"}

REQUIRED_FIELDS = [
    ("full_name", "full name"),
    ("email", "email"),
    ("phone", "phone number"),
    ("password", "password"),
    ("date_of_birth", "date of birth"),
    ("employee_number", "employee number"),
    ("tsc_number", "TSC number"),
    ("national_id", "ID number"),
]


def text(data, key):
    return str(data.get(key, "") or "").strip()


def teacher_row(request, user):
    profile = getattr(user, "teacher_profile", None)
    return {
        "id": user.pk,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "approval_status": user.approval_status,
        "date_joined": user.date_joined.date().isoformat(),
        "employee_number": profile.employee_number if profile else "",
        "tsc_number": profile.tsc_number if profile else "",
        "photo": request.build_absolute_uri(user.profile_image.url) if user.profile_image else "",
    }


class TeacherSignUpView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        data = request.data

        missing = [label for key, label in REQUIRED_FIELDS if not text(data, key)]
        if missing:
            return Response({"detail": "Please fill in: " + ", ".join(missing) + "."}, status=400)

        if text(data, "consent").lower() not in TRUTHY:
            return Response(
                {"detail": "You must accept the terms and consent to the school storing your details."},
                status=400,
            )

        photo = data.get("profile_image")
        if photo is None:
            return Response({"detail": "Please upload a photo."}, status=400)
        if photo.size > MAX_PHOTO_BYTES:
            return Response({"detail": "Photo must be under 2 MB."}, status=400)
        if photo.content_type not in ALLOWED_PHOTO_TYPES:
            return Response({"detail": "Photo must be a JPEG or PNG."}, status=400)

        phone = normalise_kenyan_phone(text(data, "phone"))
        if phone is None:
            return Response({"detail": "Enter a valid Kenyan phone number, such as 0712345678."}, status=400)

        try:
            date_of_birth = datetime.date.fromisoformat(text(data, "date_of_birth"))
        except ValueError:
            return Response({"detail": "Enter a valid date of birth."}, status=400)

        email = text(data, "email").lower()
        if User.objects.filter(Q(username=email) | Q(email__iexact=email)).exists():
            return Response({"detail": "An account with this email already exists."}, status=400)

        for field, label in [
            ("employee_number", "employee number"),
            ("tsc_number", "TSC number"),
            ("national_id", "ID number"),
        ]:
            if TeacherProfile.objects.filter(**{field: text(data, field)}).exists():
                return Response({"detail": f"A teacher with this {label} already exists."}, status=400)

        password = str(data.get("password", ""))
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)

        with transaction.atomic():
            user = User.objects.create_user(
                username=email, email=email, password=password,
                role="teacher", approval_status="pending",
                full_name=text(data, "full_name"), phone=phone, profile_image=photo,
            )
            TeacherProfile.objects.create(
                user=user,
                date_of_birth=date_of_birth,
                employee_number=text(data, "employee_number"),
                tsc_number=text(data, "tsc_number"),
                national_id=text(data, "national_id"),
                address=text(data, "address"),
                bank_name=text(data, "bank_name"),
                bank_account=text(data, "bank_account"),
                consent_given=True,
                consent_at=timezone.now(),
            )

        return Response(
            {"detail": "Thank you. Your account is waiting for admin approval. You can log in once it is approved."},
            status=201,
        )


class AdminTeacherAccountListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_filter = request.query_params.get("status", "all")
        qs = User.objects.filter(role="teacher").select_related("teacher_profile").order_by("full_name")
        if status_filter in APPROVAL_STATUSES:
            qs = qs.filter(approval_status=status_filter)
        return Response([teacher_row(request, u) for u in qs])


class AdminTeacherAccountDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get_teacher(self, pk):
        return User.objects.select_related("teacher_profile").filter(pk=pk, role="teacher").first()

    def get(self, request, pk):
        user = self.get_teacher(pk)
        if user is None:
            return Response({"detail": "Teacher not found."}, status=404)

        profile = getattr(user, "teacher_profile", None)
        row = teacher_row(request, user)
        row.update({
            "date_of_birth": profile.date_of_birth.isoformat() if profile else "",
            "national_id": profile.national_id if profile else "",
            "address": profile.address if profile else "",
            "bank_name": profile.bank_name if profile else "",
            "bank_account": profile.bank_account if profile else "",
            "consent_given": profile.consent_given if profile else False,
            "consent_at": profile.consent_at.date().isoformat() if profile and profile.consent_at else "",
        })
        row["assignments"] = [
            {"id": a.pk, "class_name": a.class_group.name, "subject_name": a.subject.name}
            for a in TeachingAssignment.objects.filter(teacher=user)
            .select_related("class_group", "subject")
            .order_by("class_group__name", "subject__name")
        ]
        row["class_teacher_of"] = [c.name for c in Class.objects.filter(class_teacher=user)]
        return Response(row)

    def patch(self, request, pk):
        user = self.get_teacher(pk)
        if user is None:
            return Response({"detail": "Teacher not found."}, status=404)

        new_status = text(request.data, "approval_status")
        if new_status not in APPROVAL_STATUSES:
            return Response({"detail": "Choose pending, approved or rejected."}, status=400)

        user.approval_status = new_status
        user.save(update_fields=["approval_status"])
        return Response(teacher_row(request, user))