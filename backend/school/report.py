import os
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.db.models import Sum
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import GradingBand, ReportComment, Score, Student

BRAND = colors.HexColor("#8B0000")
DARK = colors.HexColor("#5B0A0A")
INK = colors.HexColor("#111111")
GREY = colors.HexColor("#666666")
LIGHT = colors.HexColor("#F7F2F2")
RULE = colors.HexColor("#DDDDDD")
GREEN = colors.HexColor("#1A7F37")
WHITE = colors.white

MOTTO = "IN PURSUIT OF EXCELLENCE"
PASS_PERCENT = Decimal("31")  # Placeholder: confirm the pass mark with the school.
FALLBACK_LOGO = os.path.join(os.path.dirname(__file__), "assets", "logo.png")


def ps(name, **kwargs):
    base = dict(fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=INK, alignment=TA_LEFT)
    base.update(kwargs)
    return ParagraphStyle(name, **base)


S = {
    "school": ps("school", fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=TA_CENTER, textColor=BRAND),
    "motto": ps("motto", fontName="Helvetica-Bold", fontSize=8.5, leading=12, alignment=TA_CENTER, textColor=GREY),
    "banner": ps("banner", fontName="Helvetica-Bold", fontSize=14, leading=16, alignment=TA_CENTER, textColor=WHITE),
    "panel_head": ps("panel_head", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=WHITE),
    "label": ps("label", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=DARK),
    "value": ps("value", fontSize=8.5, leading=10.5),
    "year": ps("year", fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_CENTER, textColor=INK),
    "small": ps("small", fontSize=7, leading=9, alignment=TA_CENTER, textColor=GREY),
    "small_bold": ps("small_bold", fontName="Helvetica-Bold", fontSize=7.5, leading=9, alignment=TA_CENTER, textColor=BRAND),
    "head": ps("head", fontName="Helvetica-Bold", fontSize=7.5, leading=9, alignment=TA_CENTER, textColor=WHITE),
    "cell": ps("cell", fontSize=8, leading=10, alignment=TA_CENTER),
    "cell_left": ps("cell_left", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_LEFT),
    "cell_bold": ps("cell_bold", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_CENTER, textColor=BRAND),
    "total": ps("total", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, alignment=TA_CENTER, textColor=WHITE),
    "total_left": ps("total_left", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, alignment=TA_LEFT, textColor=WHITE),
    "body": ps("body", fontSize=8.5, leading=12),
    "footer": ps("footer", fontSize=7.5, leading=10, alignment=TA_CENTER, textColor=GREY),
}


def fmt(value):
    value = Decimal(value)
    return f"{value:.0f}" if value == value.to_integral_value() else f"{value:.2f}"


def bands_for(student):
    return list(GradingBand.objects.filter(school=student.school).order_by("-min_mark"))


def level_for(percent, bands):
    # Bands are sorted from highest to lowest, so the first match is the right level.
    for band in bands:
        if percent >= band.min_mark:
            return band
    return None


def level_code(band):
    return band.level_code if band else "-"


def level_remark(band):
    return band.remark if band else ""


def classmates(student):
    if student.current_class_id is None:
        return Student.objects.filter(pk=student.pk)
    return Student.objects.filter(current_class_id=student.current_class_id)


def assign_ranks(totals):
    # Tied students share a rank and the next rank skips, e.g. 1, 2, 2, 4.
    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ranks, previous, rank = {}, None, 0
    for position, (student_id, total) in enumerate(ordered, start=1):
        if total != previous:
            rank = position
            previous = total
        ranks[student_id] = rank
    return ranks


def make_row(name, obtained, max_marks, bands):
    obtained, max_marks = Decimal(obtained), Decimal(max_marks)
    percent = (obtained / max_marks * 100).quantize(Decimal("0.01")) if max_marks else Decimal("0")
    return {
        "name": name,
        "max": max_marks,
        "obtained": obtained,
        "percent": percent,
        "level": level_for(percent, bands),
    }


def build_report(student, *, term, assessment, subjects, rank, class_size, comments, filename):
    total_max = sum((s["max"] for s in subjects), Decimal("0"))
    total_obtained = sum((s["obtained"] for s in subjects), Decimal("0"))
    percent = (total_obtained / total_max * 100).quantize(Decimal("0.01")) if total_max else Decimal("0")
    return {
        "title": f"{assessment}, {term}",
        "academic_year": term.academic_year,
        "term_name": term.name,
        "assessment": assessment,
        "subjects": subjects,
        "total_max": total_max,
        "total_obtained": total_obtained,
        "percent": percent,
        "overall": level_for(percent, bands_for(student)),
        "passed": percent >= PASS_PERCENT,
        "rank": f"{rank} of {class_size}" if rank else "-",
        "comments": comments,
        "filename": filename,
    }


def exam_report(student, exam):
    bands = bands_for(student)
    own = (Score.objects.filter(student=student, exam=exam)
           .select_related("subject").order_by("subject__name"))
    subjects = [make_row(s.subject.name, s.marks, exam.max_marks, bands) for s in own]

    totals = {
        row["student_id"]: row["total"]
        for row in Score.objects.filter(exam=exam, student__in=classmates(student))
        .values("student_id").annotate(total=Sum("marks"))
    }
    rank = assign_ranks(totals).get(student.pk)

    return build_report(
        student, term=exam.term, assessment=exam.name, subjects=subjects,
        rank=rank, class_size=len(totals), comments=None,
        filename=f"{student.reg_no}-{exam.name}.pdf".replace(" ", "-"),
    )


def term_report(student, term):
    bands = bands_for(student)
    exams = list(term.exams.all())
    exam_count = len(exams) or 1
    max_per_exam = Decimal(exams[0].max_marks) if exams else Decimal("100")
    orders = {e.pk: e.order for e in exams}

    scores = (Score.objects.filter(student__in=classmates(student), exam__term=term)
              .select_related("subject"))
    names, sums = {}, {}
    for sc in scores:
        names[sc.subject_id] = sc.subject.name
        student_sums = sums.setdefault(sc.student_id, {})
        student_sums[sc.subject_id] = student_sums.get(sc.subject_id, Decimal("0")) + sc.marks

    def averages(student_id):
        # Plain mean: each subject's total across the exams, divided by the number of exams.
        return {sid: total / exam_count for sid, total in sums.get(student_id, {}).items()}

    totals = {sid: sum(averages(sid).values(), Decimal("0")) for sid in sums}
    rank = assign_ranks(totals).get(student.pk)

    subjects = [
        make_row(names[sid], avg, max_per_exam, bands)
        for sid, avg in sorted(averages(student.pk).items(), key=lambda kv: names[kv[0]])
    ]

    comment = ReportComment.objects.filter(student=student, term=term).first()
    comments = {
        "class": comment.class_teacher_comment if comment else "",
        "head": comment.head_teacher_comment if comment else "",
    }

    return build_report(
        student, term=term, assessment="Term average", subjects=subjects,
        rank=rank, class_size=len(totals), comments=comments,
        filename=f"{student.reg_no}-term-report-{term.name}.pdf".replace(" ", "-"),
    )


def school_logo(student):
    if student.school.logo:
        path = student.school.logo.path
    else:
        path = FALLBACK_LOGO
    if os.path.exists(path):
        return Image(path, width=26 * mm, height=26 * mm, kind="proportional")
    return Paragraph("", S["small"])


def student_photo(student):
    user = student.user
    if user and user.profile_image:
        try:
            return Image(user.profile_image.path, width=32 * mm, height=38 * mm, kind="proportional")
        except Exception:
            pass
    return Paragraph("No photo", S["small"])


def render_pdf(report, student):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=report["title"],
    )

    # Header: logo | school name and motto | academic year box
    year_box = Table([
        [Paragraph("ACADEMIC YEAR", S["small"])],
        [Paragraph(escape(report["academic_year"]), S["year"])],
        [Paragraph(escape(f"TERM: {report['term_name']}"), S["small"])],
        [Paragraph(escape(report["assessment"].upper()), S["small_bold"])],
    ], colWidths=[38 * mm])
    year_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BRAND),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    title_block = [
        Paragraph(escape(student.school.name.upper()), S["school"]),
        Spacer(1, 4),
        Paragraph(MOTTO, S["motto"]),
    ]
    header = Table([[school_logo(student), title_block, year_box]],
                   colWidths=[30 * mm, 110 * mm, 40 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    banner = Table([[Paragraph("RESULTS CARD", S["banner"])]], colWidths=[180 * mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    # Student details, with the uploaded photo on the left
    dob = student.date_of_birth.strftime("%d/%m/%Y")
    class_name = student.current_class.name if student.current_class else "-"

    def label(text):
        return Paragraph(text, S["label"])

    def value(text):
        return Paragraph(escape(str(text)), S["value"])

    info = Table([
        [label("STUDENT NAME"), ":", value(student.full_name), label("DATE OF BIRTH"), ":", value(dob)],
        [label("CLASS"), ":", value(class_name), label("POSITION IN CLASS"), ":", value(report["rank"])],
        [label("ADMISSION NO."), ":", value(student.reg_no), label("ASSESSMENT"), ":", value(report["assessment"])],
    ], colWidths=[30 * mm, 4 * mm, 40 * mm, 30 * mm, 4 * mm, 32 * mm])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))

    photo_box = Table([[student_photo(student)]], colWidths=[36 * mm], rowHeights=[42 * mm])
    photo_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    student_block = Table([[photo_box, info]], colWidths=[40 * mm, 140 * mm])
    student_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))

    # Marks table
    headers = ["SUBJECT", "MAXIMUM MARKS", "MARKS OBTAINED", "PERCENTAGE (%)", "GRADE", "REMARKS"]
    data = [[Paragraph(h, S["head"]) for h in headers]]
    for s in report["subjects"]:
        data.append([
            Paragraph(escape(s["name"].upper()), S["cell_left"]),
            Paragraph(fmt(s["max"]), S["cell"]),
            Paragraph(fmt(s["obtained"]), S["cell"]),
            Paragraph(f"{fmt(s['percent'])}%", S["cell"]),
            Paragraph(level_code(s["level"]), S["cell_bold"]),
            Paragraph(escape(level_remark(s["level"])), S["cell"]),
        ])
    data.append([
        Paragraph("TOTAL", S["total_left"]),
        Paragraph(fmt(report["total_max"]), S["total"]),
        Paragraph(fmt(report["total_obtained"]), S["total"]),
        Paragraph(f"{fmt(report['percent'])}%", S["total"]),
        Paragraph(level_code(report["overall"]), S["total"]),
        Paragraph(escape(level_remark(report["overall"])), S["total"]),
    ])

    marks = Table(data, colWidths=[w * mm for w in [44, 26, 28, 28, 22, 32]], repeatRows=1)
    marks_style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("BACKGROUND", (0, -1), (-1, -1), DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(data) - 1):
        if i % 2 == 0:
            marks_style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    marks.setStyle(TableStyle(marks_style))

    # Result summary
    result_text = "PASS" if report["passed"] else "FAIL"
    result_color = GREEN.hexval() if report["passed"] else BRAND.hexval()
    summary = Table([
        [Paragraph("RESULT SUMMARY", S["panel_head"]), ""],
        [label("TOTAL MARKS"), value(fmt(report["total_max"]))],
        [label("MARKS OBTAINED"), value(fmt(report["total_obtained"]))],
        [label("PERCENTAGE"), value(f"{fmt(report['percent'])}%")],
        [label("OVERALL GRADE"), value(level_code(report["overall"]))],
        [label("RESULT"), Paragraph(f'<font color="{result_color}"><b>{result_text}</b></font>', S["value"])],
    ], colWidths=[36 * mm, 34 * mm])
    summary.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # Remarks and signatures
    comments = report["comments"] or {}
    signatures = Table([
        ["", "", ""],
        [Paragraph("CLASS TEACHER", S["small"]),
         Paragraph("HEADTEACHER", S["small"]),
         Paragraph("SCHOOL STAMP", S["small"])],
    ], colWidths=[34 * mm, 34 * mm, 34 * mm], rowHeights=[18 * mm, 6 * mm])
    signatures.setStyle(TableStyle([
        ("LINEABOVE", (0, 1), (1, 1), 0.6, INK),
        ("BOX", (2, 0), (2, 0), 0.6, GREY),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))

    remarks = Table([
        [Paragraph("CLASS TEACHER'S REMARKS", S["panel_head"])],
        [Paragraph(escape(comments.get("class") or "-"), S["body"])],
        [Paragraph("HEAD TEACHER'S REMARKS", S["panel_head"])],
        [Paragraph(escape(comments.get("head") or "-"), S["body"])],
        [signatures],
    ], colWidths=[110 * mm])
    remarks.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("BACKGROUND", (0, 2), (-1, 2), BRAND),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    bottom = Table([[summary, remarks]], colWidths=[70 * mm, 110 * mm])
    bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story = [
        header,
        Spacer(1, 6),
        banner,
        Spacer(1, 6),
        student_block,
        Spacer(1, 8),
        marks,
        Spacer(1, 8),
        bottom,
        Spacer(1, 6),
        Paragraph(f"Printed on {date.today().strftime('%d %B %Y')}", S["footer"]),
    ]
    doc.build(story)
    return buffer.getvalue()