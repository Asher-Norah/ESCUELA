from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()

VALID_ROLES = {"student", "parent", "teacher", "admin"}

# Always the same reply, so the form can't be used to find out which emails have accounts.
GENERIC_REPLY = "If an account with that email exists, a reset link has been sent."


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        role = str(request.data.get("role", "") or "").strip()

        user = None
        if email:
            user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            # The role is only a hint for where to send the user afterwards. It grants nothing.
            if role in VALID_ROLES:
                link += f"&role={role}"
            send_mail(
                "Reset your Escuela password",
                f"Use this link to choose a new password:\n\n{link}\n\n"
                "If you did not ask for this, you can ignore this email.",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )

        return Response({"detail": GENERIC_REPLY})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uid = str(request.data.get("uid", "")).strip()
        token = str(request.data.get("token", "")).strip()
        password = str(request.data.get("password", ""))

        if not uid or not token:
            return Response({"detail": "This link is incomplete. Request a new one."}, status=400)

        try:
            pk = force_str(urlsafe_base64_decode(uid))
            user = User.objects.filter(pk=pk).first()
        except (TypeError, ValueError, OverflowError):
            user = None

        if user is None:
            return Response({"detail": "This link does not match any account. Request a new one."}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "This link is no longer valid. It may have been used already, or the account "
                           "has changed since it was sent. Request a new one."},
                status=400,
            )

        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)

        user.set_password(password)
        user.save(update_fields=["password"])
        return Response({
            "detail": "Your password has been changed. You can now log in.",
            "role": user.role,
        })