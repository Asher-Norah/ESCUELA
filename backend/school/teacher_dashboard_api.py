from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_api import current_school
from .api_views import pick_term, to_int, weighted_average
from .models import Attendance, Class, Exam, Score, Student, TeachingAssignment
from .permissions import IsTeacher


class TeacherOverviewView(APIView):
    """The logged-in teacher's subjects, the current term's exams, and the classes they are class teacher of."""
    permission_classes = [IsTeacher]

    def get(self, request):
        term = pick_term(current_school())
        exams = list(term.exams.all()) if term else []
        assignments = (
            TeachingAssignment.objects.filter(teacher=request.user)
            .select_related("class_group", "subject")
            .order_by("class_group__name", "subject__name")
        )
        return Response({
            "term": str(term) if term else None,
            "exams": [
                {"id": e.pk, "name": e.name, "order": e.order, "max_marks": float(e.max_marks)}
                for e in exams
            ],
            "assignments": [
                {
                    "class_id": a.class_group_id,
                    "class_name": a.class_group.name,
                    "subject_id": a.subject_id,
                    "subject_name": a.subject.name,
                }
                for a in assignments
            ],
            "class_teacher_of": [
                {"id": c.pk, "name": c.name}
                for c in Class.objects.filter(class_teacher=request.user).order_by("name")
            ],
        })


class TeacherClassDetailView(APIView):
    """One class as seen by a teacher: their subjects, every student's marks by exam,
    and attendance, which is only included for the class teacher."""
    permission_classes = [IsTeacher]

    def get(self, request):
        klass = Class.objects.select_related("grade_level", "school").filter(
            pk=to_int(request.query_params.get("class_id"))
        ).first()
        if klass is None:
            return Response({"detail": "Class not found."}, status=404)

        is_class_teacher = klass.class_teacher_id == request.user.pk
        assignments = list(
            TeachingAssignment.objects.filter(teacher=request.user, class_group=klass)
            .select_related("subject")
            .order_by("subject__name")
        )
        if not assignments and not is_class_teacher:
            return Response({"detail": "You do not teach in this class."}, status=403)

        subjects = [{"id": a.subject_id, "name": a.subject.name} for a in assignments]
        subject_ids = [a.subject_id for a in assignments]

        term = pick_term(klass.school)
        exams = list(term.exams.all()) if term else []
        students = list(Student.objects.filter(current_class=klass).order_by("full_name"))
        ids = [s.pk for s in students]

        scores = Score.objects.none()
        if term and ids and subject_ids:
            scores = Score.objects.filter(
                student_id__in=ids, exam__term=term, subject_id__in=subject_ids
            ).select_related("exam")

        # student -> subject -> exam order -> marks
        marks = {}
        for sc in scores:
            marks.setdefault(sc.student_id, {}).setdefault(sc.subject_id, {})[sc.exam.order] = sc.marks

        records = []
        if is_class_teacher and term and ids:
            records = list(Attendance.objects.filter(
                student_id__in=ids, date__range=(term.start_date, term.end_date)
            ))

        rows = []
        for s in students:
            student_marks = marks.get(s.pk, {})
            averages = {
                str(sid): weighted_average(orders, exams)
                for sid, orders in student_marks.items()
            }
            term_average = round(sum(averages.values()) / len(averages), 2) if averages else None

            own = [r for r in records if r.student_id == s.pk]
            attendance_percent = None
            if own:
                present = sum(1 for r in own if r.status == "present")
                attendance_percent = round(100 * present / len(own))

            rows.append({
                "id": s.pk,
                "reg_no": s.reg_no,
                "full_name": s.full_name,
                "marks": {
                    str(sid): {str(order): float(mark) for order, mark in orders.items()}
                    for sid, orders in student_marks.items()
                },
                "averages": averages,
                "term_average": term_average,
                "attendance_percent": attendance_percent,
            })

        subject_averages = {}
        for sub in subjects:
            values = [r["averages"][str(sub["id"])] for r in rows if str(sub["id"]) in r["averages"]]
            subject_averages[str(sub["id"])] = round(sum(values) / len(values), 2) if values else None

        return Response({
            "class": {
                "id": klass.pk,
                "name": klass.name,
                "grade_level": klass.grade_level.name,
                "academic_year": klass.academic_year,
            },
            "term": str(term) if term else None,
            "is_class_teacher": is_class_teacher,
            "exams": [{"order": e.order, "label": e.name} for e in exams],
            "subjects": subjects,
            "subject_averages": subject_averages,
            "students": rows,
        })


class TeacherClassMarksView(APIView):
    """Students in a class with their current mark for one subject and exam.
    Only the teacher assigned to that subject in that class can see it."""
    permission_classes = [IsTeacher]

    def get(self, request):
        class_id = to_int(request.query_params.get("class_id"))
        subject_id = to_int(request.query_params.get("subject_id"))
        exam_id = to_int(request.query_params.get("exam_id"))

        allowed = TeachingAssignment.objects.filter(
            teacher=request.user, class_group_id=class_id, subject_id=subject_id
        ).exists()
        if not allowed:
            return Response(
                {"detail": "You are not assigned to this subject in this class."},
                status=403,
            )

        exam = Exam.objects.filter(pk=exam_id).first()
        if exam is None:
            return Response({"detail": "Choose a valid exam."}, status=400)

        students = list(Student.objects.filter(current_class_id=class_id).order_by("full_name"))
        marks = {
            s.student_id: float(s.marks)
            for s in Score.objects.filter(exam=exam, subject_id=subject_id, student__in=students)
        }
        return Response({
            "students": [
                {"id": s.pk, "full_name": s.full_name, "reg_no": s.reg_no, "marks": marks.get(s.pk)}
                for s in students
            ],
        })