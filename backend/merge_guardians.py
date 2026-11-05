from django.db.models import Count
from school.models import Guardian

dupes = Guardian.objects.values("phone").annotate(n=Count("id")).filter(n__gt=1)
for row in dupes:
    records = list(Guardian.objects.filter(phone=row["phone"]).order_by("pk"))
    keep, others = records[0], records[1:]
    for g in others:
        keep.students.add(*g.students.all())
        g.delete()
    print("Merged", row["phone"], "into record", keep.pk, "children:", [s.reg_no for s in keep.students.all()])

print("Done.")
