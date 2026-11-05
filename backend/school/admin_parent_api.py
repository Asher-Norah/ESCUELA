# pyright: reportMissingModuleSource=false
# pyright: reportMissingImports=false
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.crypto import get_random_string
from rest_framework.response import Response  # pyright: ignore[reportMissingImports]
from rest_framework.views import APIView

from .admin_api import IsAdminUser
from .api_views import to_int
from .models import Guardian, ParentLink, Student
from .parent_api import linked_students

User = get_user_model()


def student_summary(student):
    return {
        "id": student.pk,
        "full_name": student.full_name,
        "reg_no": student.reg_no,
        "class_name": student.current_class.name if student.current_class else "",
    }


def children_of(user):
    return [student_summary(s) for s in linked_students(user)]


def parent_row(guardian, account, children):
    return {
        "key": f"g{guardian.pk}" if guardian else f"u{account.pk}",
        "guardian_id": guardian.pk if guardian else None,
        "user_id": account.pk if account else None,
        "full_name": account.full_name if account else guardian.full_name,
        "phone": guardian.phone if guardian else account.username,
        "email": account.email if account else "",
        "has_account": account is not None,
        "children": children,
    }


class AdminParentListView(APIView):
    """One row per phone number. Guardian records with the same phone are merged,
    and a parent account that has no guardian record still appears."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        accounts = {u.username: u for u in User.objects.filter(role="parent")}

        grouped = {}
        guardians = Guardian.objects.prefetch_related("students__current_class").order_by("full_name")
        for guardian in guardians:
            entry = grouped.setdefault(guardian.phone, {"guardian": guardian, "children": {}})
            for s in guardian.students.all():
                entry["children"][s.pk] = student_summary(s)

        rows = []
        for phone, entry in grouped.items():
            account = accounts.get(phone)
            children = dict(entry["children"])
            if account is not None:
                for c in children_of(account):
                    children[c["id"]] = c
            rows.append(parent_row(
                entry["guardian"], account,
                sorted(children.values(), key=lambda c: c["full_name"]),
            ))

        for username, account in accounts.items():
            if username not in grouped:
                rows.append(parent_row(None, account, children_of(account)))

        rows.sort(key=lambda r: r["full_name"].lower())
        return Response(rows)


class AdminParentDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        user = User.objects.filter(pk=pk, role="parent").first()
        if user is None:
            return Response({"detail": "Parent not found."}, status=404)

        children = children_of(user)
        linked_ids = [c["id"] for c in children]
        available = Student.objects.exclude(pk__in=linked_ids).order_by("full_name")

        return Response({
            "id": user.pk,
            "full_name": user.full_name,
            "phone": user.phone,
            "email": user.email,
            "date_joined": user.date_joined.date().isoformat(),
            "children": children,
            "available_students": [
                {"id": s.pk, "full_name": s.full_name, "reg_no": s.reg_no} for s in available
            ],
        })

    def patch(self, request, pk):
        user = User.objects.filter(pk=pk, role="parent").first()
        if user is None:
            return Response({"detail": "Parent not found."}, status=404)

        email = str(request.data.get("email", "")).strip().lower()
        if email:
            taken = User.objects.filter(Q(username=email) | Q(email__iexact=email)).exclude(pk=user.pk)
            if taken.exists():
                return Response(
                    {"detail": "This email is already used by another account."}, status=400
                )

        user.email = email
        user.save(update_fields=["email"])
        return Response({"email": user.email, "detail": "Email saved."})


class AdminParentChildrenView(APIView):
    """Link a child to a parent account directly."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk, role="parent").first()
        student = Student.objects.filter(pk=to_int(request.data.get("student_id"))).first()
        if user is None or student is None:
            return Response({"detail": "Choose a valid parent and student."}, status=400)

        ParentLink.objects.get_or_create(parent=user, student=student)
        return Response({"children": children_of(user)})


class AdminParentChildDetailView(APIView):
    """Unlink a child. This removes the direct link and the child from any guardian
    record with the parent's phone number. The student's records are kept."""
    permission_classes = [IsAdminUser]

    def delete(self, request, pk, sid):
        user = User.objects.filter(pk=pk, role="parent").first()
        if user is None:
            return Response({"detail": "Parent not found."}, status=404)

        ParentLink.objects.filter(parent=user, student_id=sid).delete()
        for guardian in Guardian.objects.filter(phone=user.username, students__pk=sid):
            guardian.students.remove(sid)
        return Response({"children": children_of(user)})


class AdminSetPasswordView(APIView):
    """The admin sets a temporary password for a student, parent or teacher.
    The password is shown once, so the admin can pass it on in person."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).exclude(role="admin").first()
        if user is None:
            return Response({"detail": "User not found."}, status=404)

        temporary = get_random_string(10, allowed_chars="abcdefghjkmnpqrstuvwxyz23456789")
        user.set_password(temporary)
        user.save(update_fields=["password"])
        return Response({
            "full_name": user.full_name,
            "password": temporary,
            "detail": "Give this password to the user. It is shown only once.",
        })