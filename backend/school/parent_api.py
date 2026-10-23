from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Student


class IsParent(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "parent"
                    and user.approval_status == "approved")


def linked_students(user):
    return Student.objects.filter(parent_links__parent=user).distinct().order_by("full_name")


def student_for_request(request):
    """Returns the child chosen in ?student_id=, if the parent is linked to them."""
    children = linked_students(request.user)
    chosen = request.query_params.get("student_id")
    if chosen:
        return children.filter(pk=chosen).first()
    return children.first()


class ParentChildrenView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        children = linked_students(request.user)
        return Response({
            "children": [
                {
                    "id": s.pk,
                    "full_name": s.full_name,
                    "reg_no": s.reg_no,
                    "class_name": s.current_class.name if s.current_class else "",
                }
                for s in children
            ]
        })