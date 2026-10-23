import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Attendance, Class, Exam, Score, Student, Subject, Term, TeachingAssignment
from .parent_api import IsParent, student_for_request
from .permissions import IsStudent, IsTeacher
from .report import exam_report, render_pdf, term_report

ATTENDANCE_VALUES = {"present", "late", "absent"}


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_date(value):
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


def pick_term(school, term_id=None):
    terms = Term.objects.filter(school=school)
    if term_id:
        return terms.filter(pk=to_int(term_id)).first()
    return terms.first()  # newest term, since Term is ordered by start_date


def current_student(request):
    """A student sees their own record. A parent sees the child they choose."""
    if request.user.role == "parent":
        return student_for_request(request)
    return getattr(request.user, "student_profile", None)


def weighted_average(marks_by_order, exams):
    """Plain mean of the term's exam marks. The name is kept so the API stays the same."""
    if not exams:
        return 0.0
    total = sum(Decimal(str(marks_by_order.get(e.order, 0))) for e in exams)
    return round(float(total / len(exams)), 2)


class StudentAttendanceView(APIView):
    permission_classes = [IsStudent | IsParent]

    def get(self, request):
        student = current_student(request)
        if student is None:
            return Response({"detail": "No student record found."}, status=404)

        term = pick_term(student.school, request.query_params.get("term"))
        if term is None:
            return Response({"term": None, "present_percent": 0, "data": [], "records": []})

        records = list(
            Attendance.objects.filter(student=student, date__range=(term.start_date, term.end_date))
            .order_by("-date")
        )
        counts = {"present": 0, "late": 0, "absent": 0}
        for record in records:
            counts[record.status] += 1

        total = sum(counts.values())
        percent = round(100 * counts["present"] / total) if total else 0
        return Response({
            "term": str(term),
            "present_percent": percent,
            "data": [
                {"name": "Present", "value": counts["present"]},
                {"name": "Late", "value": counts["late"]},
                {"name": "Absent", "value": counts["absent"]},
            ],
            "records": [{"date": r.date.isoformat(), "status": r.status} for r in records],
        })


class StudentPerformanceView(APIView):
    permission_classes = [IsStudent | IsParent]

    def get(self, request):
        student = current_student(request)
        if student is None:
            return Response({"detail": "No student record found."}, status=404)

        term = pick_term(student.school, request.query_params.get("term"))
        if term is None:
            return Response({"term": None, "exams": [], "subjects": []})

        exams = list(term.exams.all())
        scores = Score.objects.filter(student=student, exam__term=term).select_related("subject", "exam")

        rows = {}
        for score in scores:
            row = rows.setdefault(score.subject_id, {"subject": score.subject.name, "scores": {}})
            row["scores"][score.exam.order] = float(score.marks)

        subjects = []
        for row in rows.values():
            row["weighted"] = weighted_average(row["scores"], exams)
            subjects.append(row)

        return Response({
            "term": str(term),
            "exams": [{"order": e.order, "label": e.name} for e in exams],
            "subjects": subjects,
        })


class ScoreEntryView(APIView):
    """Subject teacher enters marks for one subject and exam for their class."""
    permission_classes = [IsTeacher]

    def post(self, request):
        exam = Exam.objects.filter(pk=to_int(request.data.get("exam_id"))).first()
        subject = Subject.objects.filter(pk=to_int(request.data.get("subject_id"))).first()
        klass = Class.objects.filter(pk=to_int(request.data.get("class_id"))).first()
        if not (exam and subject and klass):
            return Response({"detail": "Choose a valid exam, subject and class."}, status=400)

        allowed = TeachingAssignment.objects.filter(
            teacher=request.user, class_group=klass, subject=subject
        ).exists()
        if not allowed:
            return Response(
                {"detail": "You are not assigned to teach this subject in this class."},
                status=403,
            )

        rows = request.data.get("scores", [])
        if not isinstance(rows, list) or not rows:
            return Response({"detail": "Send a list of scores."}, status=400)

        class_students = {s.pk: s for s in Student.objects.filter(current_class=klass)}
        saved, errors = 0, []

        with transaction.atomic():
            for row in rows:
                student_id = to_int(row.get("student_id"))
                student = class_students.get(student_id)
                if student is None:
                    errors.append(f"Student {row.get('student_id')} is not in this class.")
                    continue
                try:
                    marks = Decimal(str(row.get("marks")))
                except (InvalidOperation, TypeError):
                    errors.append(f"{student.full_name}: marks must be a number.")
                    continue
                if marks < 0 or marks > exam.max_marks:
                    errors.append(f"{student.full_name}: marks must be between 0 and {exam.max_marks}.")
                    continue
                Score.objects.update_or_create(
                    student=student, exam=exam, subject=subject,
                    defaults={"marks": marks, "entered_by": request.user},
                )
                saved += 1

        return Response({"saved": saved, "errors": errors})


class ClassAttendanceView(APIView):
    """Class teacher views and records the day's attendance for their class."""
    permission_classes = [IsTeacher]

    def get(self, request):
        klass = Class.objects.filter(
            pk=to_int(request.query_params.get("class_id")), class_teacher=request.user
        ).first()
        day = parse_date(request.query_params.get("date"))
        if klass is None or day is None:
            return Response({"detail": "Choose one of your classes and a valid date."}, status=400)

        students = list(Student.objects.filter(current_class=klass).order_by("full_name"))
        marked = {a.student_id: a.status for a in Attendance.objects.filter(
            date=day, student__in=students)}

        return Response({
            "date": day.isoformat(),
            "students": [
                {"id": s.pk, "full_name": s.full_name, "reg_no": s.reg_no,
                 "status": marked.get(s.pk, "present")}
                for s in students
            ],
        })

    def post(self, request):
        klass = Class.objects.filter(
            pk=to_int(request.data.get("class_id")), class_teacher=request.user
        ).first()
        day = parse_date(request.data.get("date"))
        if klass is None or day is None:
            return Response({"detail": "Choose one of your classes and a valid date."}, status=400)

        valid_ids = set(Student.objects.filter(current_class=klass).values_list("id", flat=True))
        saved = 0
        with transaction.atomic():
            for row in request.data.get("records", []):
                student_id = to_int(row.get("student_id"))
                status_value = row.get("status")
                if student_id not in valid_ids or status_value not in ATTENDANCE_VALUES:
                    continue
                Attendance.objects.update_or_create(
                    student_id=student_id, date=day,
                    defaults={"status": status_value, "marked_by": request.user},
                )
                saved += 1

        return Response({"saved": saved})


class StudentReportCardsView(APIView):
    permission_classes = [IsStudent | IsParent]

    def get(self, request):
        student = current_student(request)
        if student is None:
            return Response({"detail": "No student record found."}, status=404)

        report_type = request.query_params.get("type")

        if report_type is None:
            return self.list_available(student)

        if report_type == "exam":
            exam = Exam.objects.filter(
                pk=to_int(request.query_params.get("id")), term__school=student.school
            ).first()
            if exam is None:
                return Response({"detail": "Report not found."}, status=404)
            report = exam_report(student, exam)

        elif report_type == "term":
            term = Term.objects.filter(
                pk=to_int(request.query_params.get("id")), school=student.school
            ).first()
            if term is None:
                return Response({"detail": "Report not found."}, status=404)
            report = term_report(student, term)

        else:
            return Response({"detail": "Unknown report type."}, status=400)

        pdf = render_pdf(report, student)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{report["filename"]}"'
        return response

    def list_available(self, student):
        term = pick_term(student.school)
        if term is None:
            return Response({"term": None, "reports": []})

        exams = list(term.exams.all())
        marked = set(
            Score.objects.filter(student=student, exam__term=term).values_list("exam_id", flat=True)
        )
        reports = [
            {"type": "exam", "id": e.pk, "label": f"{e.name} report"}
            for e in exams if e.pk in marked
        ]
        # The term report is available once every exam in the term has marks.
        if exams and all(e.pk in marked for e in exams):
            reports.append({"type": "term", "id": term.pk, "label": f"Term report, {term}"})

        return Response({"term": str(term), "reports": reports})