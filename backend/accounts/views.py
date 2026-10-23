from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from school.phone import normalise_kenyan_phone

User = get_user_model()

DASHBOARDS = {
    "admin": "/dashboard/admin",
    "teacher": "/dashboard/teacher",
    "student": "/dashboard/student",
    "parent": "/dashboard/parent",
}


def health(request):
    return JsonResponse({"status": "ok", "service": "school-backend"})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = str(request.data.get("identifier", "")).strip()
        password = str(request.data.get("password", ""))

        if not identifier or not password:
            return Response(
                {"detail": "Enter your email or registration number and password."},
                status=400,
            )

        # Parents log in with their phone number in any Kenyan format.
        phone = normalise_kenyan_phone(identifier)
        user = User.objects.filter(
            Q(username=identifier) | Q(username=phone or identifier) | Q(email__iexact=identifier)
        ).first()

        if user is None or not user.check_password(password):
            return Response(
                {"detail": "Incorrect email, registration number, or password."},
                status=401,
            )

        if not user.is_active:
            return Response({"detail": "This account is disabled."}, status=403)

        if user.approval_status == "pending":
            return Response(
                {"detail": "Your account is waiting for admin approval."},
                status=403,
            )

        if user.approval_status == "rejected":
            return Response(
                {"detail": "Your account request was not approved. Contact the school office."},
                status=403,
            )

        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": user.role,
            "full_name": user.full_name,
            "redirect": DASHBOARDS.get(user.role, "/"),
        })


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        data = {
            "full_name": user.full_name,
            "role": user.role,
            "profile_image": (
                request.build_absolute_uri(user.profile_image.url)
                if user.profile_image else ""
            ),
        }
        # Students also get their school details. getattr returns None
        # if this user has no student record.
        student = getattr(user, "student_profile", None)
        if student is not None:
            data["reg_no"] = student.reg_no
            data["class_name"] = student.current_class.name if student.current_class else ""
        return Response(data)