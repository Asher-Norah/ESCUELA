from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Student
from .serializers import StudentActivateSerializer, StudentLookupSerializer

User = get_user_model()
NOT_FOUND = "We could not find a matching record."


def find_unclaimed_student(reg_no, date_of_birth):
    # Same message whether the reg no or the date of birth is wrong, so this
    # endpoint can't be used to check which reg numbers exist.
    return Student.objects.filter(
        reg_no=reg_no, date_of_birth=date_of_birth, user__isnull=True
    ).select_related("current_class").first()


class StudentLookupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = StudentLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = find_unclaimed_student(**serializer.validated_data)
        if not student:
            return Response({"detail": NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "reg_no": student.reg_no,
            "full_name": student.full_name,
            "class_name": student.current_class.name if student.current_class else "",
            "address": student.address,
            "nationality": student.nationality,
        })


class StudentActivateView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = StudentActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        student = find_unclaimed_student(data["reg_no"], data["date_of_birth"])
        if not student:
            return Response({"detail": NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        try:
            validate_password(data["password"])
        except DjangoValidationError as exc:
            return Response({"password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.create_user(
                username=student.reg_no,
                password=data["password"],
                role="student",
                approval_status="approved",
                full_name=student.full_name,
                profile_image=data["profile_image"],
            )
            # Only the student's own details change. The class is never touched here.
            student.address = data.get("address", student.address)
            student.nationality = data.get("nationality", student.nationality)
            student.user = user
            student.save()

        return Response({"detail": "Account activated. You can now log in."}, status=status.HTTP_201_CREATED)