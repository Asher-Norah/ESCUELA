from django.conf import settings
from django.db import models


class School(models.Model):
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to="school_logos/", blank=True)
    currency = models.CharField(max_length=3, default="KES")

    def __str__(self):
        return self.name


class GradeLevel(models.Model):
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField(unique=True)

    def __str__(self):
        return self.name


class Class(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT)
    name = models.CharField(max_length=50)
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.PROTECT)
    academic_year = models.CharField(max_length=9)
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="classes_taught", limit_choices_to={"role": "teacher"},
    )

    def __str__(self):
        return self.name


class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT)
    reg_no = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    current_class = models.ForeignKey(Class, null=True, blank=True, on_delete=models.SET_NULL)
    address = models.TextField(blank=True)
    nationality = models.CharField(max_length=60, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="student_profile",
    )

    def __str__(self):
        return f"{self.full_name} ({self.reg_no})"


class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10)

    class Meta:
        unique_together = ("school", "code")

    def __str__(self):
        return self.name


class Term(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT)
    academic_year = models.CharField(max_length=9)
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        unique_together = ("school", "academic_year", "name")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} {self.academic_year}"


class Exam(models.Model):
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="exams")
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField()
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Percentage of the term average, e.g. 30 for 30%",
    )

    class Meta:
        unique_together = ("term", "order")
        ordering = ["order"]

    def __str__(self):
        return f"{self.name} ({self.term})"


class TeachingAssignment(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="teaching_assignments", limit_choices_to={"role": "teacher"},
    )
    class_group = models.ForeignKey(Class, on_delete=models.CASCADE, related_name="assignments")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("teacher", "class_group", "subject")


class Score(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="scores")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="scores")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    marks = models.DecimalField(max_digits=5, decimal_places=2)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="entered_scores",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "exam", "subject")


class Attendance(models.Model):
    STATUS_CHOICES = [
        ("present", "Present"),
        ("late", "Late"),
        ("absent", "Absent"),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="marked_attendance",
    )

    class Meta:
        unique_together = ("student", "date")


class GradingBand(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    min_mark = models.DecimalField(max_digits=5, decimal_places=2)
    max_mark = models.DecimalField(max_digits=5, decimal_places=2)
    level_code = models.CharField(max_length=5)
    descriptor = models.CharField(max_length=60)
    remark = models.CharField(max_length=100)
    points = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-min_mark"]

    def __str__(self):
        return f"{self.level_code} ({self.min_mark}-{self.max_mark})"


class ReportComment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="report_comments")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="report_comments")
    class_teacher_comment = models.TextField(blank=True)
    head_teacher_comment = models.TextField(blank=True)

    class Meta:
        unique_together = ("student", "term")

class Guardian(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    students = models.ManyToManyField(Student, related_name="guardians", blank=True)

    def __str__(self):
        return self.full_name


class ParentLink(models.Model):
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="child_links",
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="parent_links")
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("parent", "student")