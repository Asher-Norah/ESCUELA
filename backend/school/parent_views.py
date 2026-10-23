from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ParentLink, Student
from .phone import normalise_kenyan_phone

User = get_user_model()

MAX_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png"}
DENIED = (
    "Your details do not match the school's records. "
    "Check your name, phone number and the student's registration number."
)


def clean_name(value):
    # Ignore extra spaces and capital letters when comparing names.
    return " ".join(value.split()).lower()


class ParentSignUpSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    student_reg_no = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)
    profile_image = serializers.ImageField()

    def validate_profile_image(self, image):
        if image.size > MAX_PHOTO_BYTES:
            raise serializers.ValidationError("Photo must be under 2 MB.")
        if image.content_type not in ALLOWED_PHOTO_TYPES:
            raise serializers.ValidationError("Photo must be a JPEG or PNG.")
        return image


class ParentSignUpView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ParentSignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Every mismatch returns the same message, so the form can't be used
        # to discover which reg numbers or phone numbers exist.
        phone = normalise_kenyan_phone(data["phone"])
        if phone is None:
            return Response({"detail": DENIED}, status=status.HTTP_400_BAD_REQUEST)

        student = Student.objects.filter(reg_no=data["student_reg_no"].strip()).first()
        if student is None:
            return Response({"detail": DENIED}, status=status.HTTP_400_BAD_REQUEST)

        guardian = next(
            (g for g in student.guardians.all()
             if g.phone == phone and clean_name(g.full_name) == clean_name(data["full_name"])),
            None,
        )
        if guardian is None:
            return Response({"detail": DENIED}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=phone).exists():
            return Response(
                {"detail": "An account already exists for this phone number. Please log in."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(data["password"])
        except DjangoValidationError as exc:
            return Response({"password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.create_user(
                username=phone,
                password=data["password"],
                role="parent",
                approval_status="approved",
                full_name=guardian.full_name,
                phone=phone,
                profile_image=data["profile_image"],
            )
            ParentLink.objects.get_or_create(parent=user, student=student)

        return Response(
            {"detail": f"Account created. You can now log in as {student.full_name}'s parent."},
            status=status.HTTP_201_CREATED,
        )