from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveDestroyAPIView,
    RetrieveUpdateDestroyAPIView,
)

from .admin_api import IsAdminUser, current_school
from .models import Class, Subject, TeachingAssignment

User = get_user_model()


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "code"]

    def validate_code(self, value):
        code = value.strip().upper()
        others = Subject.objects.filter(school=current_school(), code=code)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError("A subject with this code already exists.")
        return code

    def create(self, validated_data):
        validated_data["school"] = current_school()
        return super().create(validated_data)


class AssignmentSerializer(serializers.ModelSerializer):
    teacher = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role="teacher", approval_status="approved")
    )
    class_group = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    class_name = serializers.CharField(source="class_group.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = TeachingAssignment
        fields = [
            "id", "teacher", "teacher_name",
            "class_group", "class_name",
            "subject", "subject_name",
        ]

    def validate(self, attrs):
        existing = TeachingAssignment.objects.filter(
            teacher=attrs["teacher"],
            class_group=attrs["class_group"],
            subject=attrs["subject"],
        )
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                "This teacher is already assigned to that subject in that class."
            )
        return attrs


class AdminSubjectListView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.order_by("name")


class AdminSubjectDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.all()


class AdminAssignmentListView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        qs = TeachingAssignment.objects.select_related(
            "teacher", "class_group", "subject"
        ).order_by("class_group__name", "subject__name")
        class_id = self.request.query_params.get("class_id", "")
        if class_id.isdigit():
            qs = qs.filter(class_group_id=int(class_id))
        return qs


class AdminAssignmentDetailView(RetrieveDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AssignmentSerializer
    queryset = TeachingAssignment.objects.select_related("teacher", "class_group", "subject")