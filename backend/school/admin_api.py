from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q

from rest_framework import serializers
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_views import pick_term, weighted_average
from .models import Attendance, Class, GradeLevel, Guardian, School, Score, Student
from .phone import normalise_kenyan_phone

User = get_user_model()

class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "admin")


def current_school():
    # One school for now. When several schools are supported, this comes from the admin's account.
    return School.objects.first()


def photo_url(request, user):
    if user and user.profile_image:
        return request.build_absolute_uri(user.profile_image.url)
    return ""


def attendance_summary(records):
    counts = {"present": 0, "late": 0, "absent": 0}
    for record in records:
        counts[record.status] += 1
    total = sum(counts.values())
    return {
        "present_percent": round(100 * counts["present"] / total) if total else 0,
        "data": [
            {"name": "Present", "value": counts["present"]},
            {"name": "Late", "value": counts["late"]},
            {"name": "Absent", "value": counts["absent"]},
        ],
    }


def performance_for_student(student, term):
    if term is None:
        return {"term": None, "exams": [], "subjects": []}
    exams = list(term.exams.all())
    rows = {}
    scores = Score.objects.filter(student=student, exam__term=term).select_related("subject", "exam")
    for score in scores:
        row = rows.setdefault(score.subject_id, {"subject": score.subject.name, "scores": {}})
        row["scores"][score.exam.order] = float(score.marks)
    subjects = []
    for row in rows.values():
        row["weighted"] = weighted_average(row["scores"], exams)
        subjects.append(row)
    subjects.sort(key=lambda s: s["subject"])
    return {
        "term": str(term),
        "exams": [{"order": e.order, "label": e.name} for e in exams],
        "subjects": subjects,
    }


class GradeLevelOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = ["id", "name", "order"]


class TeacherOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "full_name"]


class StudentAdminSerializer(serializers.ModelSerializer):
    class_name = serializers.SerializerMethodField()
    activated = serializers.SerializerMethodField()
    email = serializers.EmailField(required=False, allow_blank=True)
    
    class Meta:
        model = Student
        fields = [
            "id", "reg_no", "full_name", "date_of_birth", "current_class",
            "class_name", "address", "nationality", "email", "activated",
        ]
        extra_kwargs = {"current_class": {"required": False, "allow_null": True}}

    def get_class_name(self, obj):
        return obj.current_class.name if obj.current_class else ""

    def get_activated(self, obj):
        return obj.user_id is not None

    def validate_reg_no(self, value):
        value = value.strip().upper()
        others = Student.objects.filter(reg_no=value)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError("A student with this registration number already exists.")
        return value

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if not email:
            return ""
        taken = User.objects.filter(Q(username=email) | Q(email__iexact=email))
        if self.instance is not None and self.instance.user_id:
            taken = taken.exclude(pk=self.instance.user_id)
        if taken.exists():
            raise serializers.ValidationError("This email is already used by another account.")
        return email

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        # Keep the login account in step with the student record, so password reset works.
        if instance.user_id:
            instance.user.email = instance.email
            instance.user.save(update_fields=["email"])
        return instance

    def create(self, validated_data):
        validated_data["school"] = current_school()
        return super().create(validated_data)


class ClassAdminSerializer(serializers.ModelSerializer):
    grade_level_name = serializers.CharField(source="grade_level.name", read_only=True)
    class_teacher = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role="teacher", approval_status="approved"),
        allow_null=True,
        required=False,
    )
    class_teacher_name = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Class
        fields = [
            "id", "name", "grade_level", "grade_level_name", "academic_year",
            "class_teacher", "class_teacher_name", "student_count",
        ]

    def get_class_teacher_name(self, obj):
        return obj.class_teacher.full_name if obj.class_teacher else ""

    def get_student_count(self, obj):
        return obj.student_set.count()

    def create(self, validated_data):
        validated_data["school"] = current_school()
        return super().create(validated_data)


class GuardianAdminSerializer(serializers.ModelSerializer):
    students = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Student.objects.all(), required=False
    )
    student_names = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = ["id", "full_name", "phone", "students", "student_names"]

    def get_student_names(self, obj):
        return [f"{s.full_name} ({s.reg_no})" for s in obj.students.all()]

    def validate_phone(self, value):
        phone = normalise_kenyan_phone(value)
        if phone is None:
            raise serializers.ValidationError("Enter a valid Kenyan phone number, such as 0712345678.")
        return phone

    def create(self, validated_data):
        students = validated_data.pop("students", [])
        validated_data["school"] = current_school()
        guardian = super().create(validated_data)
        guardian.students.set(students)
        return guardian

    def update(self, instance, validated_data):
        students = validated_data.pop("students", None)
        instance = super().update(instance, validated_data)
        if students is not None:
            instance.students.set(students)
        return instance


class AdminGradeLevelListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = GradeLevelOptionSerializer
    queryset = GradeLevel.objects.order_by("order")


class AdminTeacherListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = TeacherOptionSerializer
    queryset = User.objects.filter(role="teacher", approval_status="approved").order_by("full_name")


class AdminClassListView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ClassAdminSerializer
    queryset = Class.objects.select_related("grade_level", "class_teacher").order_by("name")


class AdminClassDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ClassAdminSerializer
    queryset = Class.objects.select_related("grade_level", "class_teacher")


class AdminClassOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        klass = Class.objects.select_related("school", "grade_level", "class_teacher").filter(pk=pk).first()
        if klass is None:
            return Response({"detail": "Class not found."}, status=404)

        term = pick_term(klass.school, request.query_params.get("term"))
        students = list(Student.objects.filter(current_class=klass).order_by("full_name"))
        ids = [s.pk for s in students]
        exams = list(term.exams.all()) if term else []
        exam_count = len(exams) or 1

        scores = []
        records = []
        if term:
            scores = list(
                Score.objects.filter(student_id__in=ids, exam__term=term).select_related("subject", "exam")
            )
            records = list(
                Attendance.objects.filter(
                    student_id__in=ids, date__range=(term.start_date, term.end_date)
                )
            )

        # Class averages per subject, for each exam.
        by_subject = {}
        student_sums = {}
        for sc in scores:
            subj = by_subject.setdefault(sc.subject_id, {"name": sc.subject.name, "by_exam": {}})
            subj["by_exam"].setdefault(sc.exam.order, []).append(sc.marks)
            per_student = student_sums.setdefault(sc.student_id, {})
            per_student[sc.subject_id] = per_student.get(sc.subject_id, Decimal("0")) + sc.marks

        subjects = []
        for subj in by_subject.values():
            averages = {
                order: sum(vals, Decimal("0")) / len(vals)
                for order, vals in subj["by_exam"].items()
            }
            subjects.append({
                "subject": subj["name"],
                "scores": {str(order): round(float(avg), 2) for order, avg in averages.items()},
                "weighted": weighted_average(averages, exams),
            })
        subjects.sort(key=lambda s: s["subject"])

        # One row per student: attendance and average mark.
        rows = []
        for s in students:
            own = [r for r in records if r.student_id == s.pk]
            present = sum(1 for r in own if r.status == "present")
            attendance_percent = round(100 * present / len(own)) if own else None

            sums = student_sums.get(s.pk, {})
            average = None
            if sums:
                per_subject = [total / exam_count for total in sums.values()]
                average = round(float(sum(per_subject, Decimal("0")) / len(per_subject)), 2)

            rows.append({
                "id": s.pk,
                "reg_no": s.reg_no,
                "full_name": s.full_name,
                "activated": s.user_id is not None,
                "attendance_percent": attendance_percent,
                "average": average,
            })

        averages_known = [r["average"] for r in rows if r["average"] is not None]
        average_mark = round(sum(averages_known) / len(averages_known), 2) if averages_known else None

        return Response({
            "class": ClassAdminSerializer(klass).data,
            "term": str(term) if term else None,
            "average_mark": average_mark,
            "performance": {
                "term": str(term) if term else None,
                "exams": [{"order": e.order, "label": e.name} for e in exams],
                "subjects": subjects,
            },
            "attendance": {
                **attendance_summary(records),
                "term": str(term) if term else None,
            },
            "students": rows,
        })


class AdminStudentListView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = StudentAdminSerializer
    queryset = Student.objects.select_related("current_class").order_by("full_name")


class AdminStudentDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = StudentAdminSerializer
    queryset = Student.objects.select_related("current_class")

    def perform_destroy(self, instance):
        # Remove the student's login as well, so the account can't be used after deletion.
        linked_user = instance.user
        instance.delete()
        if linked_user is not None:
            linked_user.delete()


class AdminStudentOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        student = Student.objects.select_related("school", "current_class", "user").filter(pk=pk).first()
        if student is None:
            return Response({"detail": "Student not found."}, status=404)

        term = pick_term(student.school, request.query_params.get("term"))
        records = []
        if term:
            records = list(
                Attendance.objects.filter(
                    student=student, date__range=(term.start_date, term.end_date)
                ).order_by("-date")
            )

        return Response({
            "student": StudentAdminSerializer(student).data,
            "photo": photo_url(request, student.user),
            "guardians": [
                {"id": g.pk, "full_name": g.full_name, "phone": g.phone}
                for g in student.guardians.all()
            ],
            "term": str(term) if term else None,
            "performance": performance_for_student(student, term),
            "attendance": {
                **attendance_summary(records),
                "term": str(term) if term else None,
                "records": [{"date": r.date.isoformat(), "status": r.status} for r in records],
            },
        })


class AdminGuardianListView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = GuardianAdminSerializer
    queryset = Guardian.objects.prefetch_related("students").order_by("full_name")


class AdminGuardianDetailView(RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = GuardianAdminSerializer
    queryset = Guardian.objects.prefetch_related("students")