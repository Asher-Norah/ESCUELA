from decimal import Decimal

from rest_framework import serializers
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from .admin_api import IsAdminUser, current_school
from .models import Exam, Term


class TermSerializer(serializers.ModelSerializer):
    exam_count = serializers.SerializerMethodField()
    weight_total = serializers.SerializerMethodField()

    class Meta:
        model = Term
        fields = ["id", "academic_year", "name", "start_date", "end_date", "exam_count", "weight_total"]

    def get_exam_count(self, obj):
        return obj.exams.count()

    def get_weight_total(self, obj):
        return float(sum((e.weight for e in obj.exams.all()), Decimal("0")))

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError("The end date must be after the start date.")

        year = attrs.get("academic_year", getattr(self.instance, "academic_year", None))
        name = attrs.get("name", getattr(self.instance, "name", None))
        clash = Term.objects.filter(school=current_school(), academic_year=year, name=name)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A term with this name already exists for that academic year.")
        return attrs

    def create(self, validated_data):
        validated_data["school"] = current_school()
        return super().create(validated_data)


class ExamSerializer(serializers.ModelSerializer):
    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all())
    term_name = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ["id", "term", "term_name", "name", "order", "max_marks", "weight"]

    def get_term_name(self, obj):
        return str(obj.term)

    def validate(self, attrs):
        term = attrs.get("term", getattr(self.instance, "term", None))
        order = attrs.get("order", getattr(self.instance, "order", None))
        max_marks = Decimal(str(attrs.get("max_marks", getattr(self.instance, "max_marks", 100))))
        weight = Decimal(str(attrs.get("weight", getattr(self.instance, "weight", 0))))

        if max_marks <= 0:
            raise serializers.ValidationError("Maximum marks must be more than 0.")
        if weight < 0 or weight > 100:
            raise serializers.ValidationError("The weight must be between 0 and 100.")

        siblings = Exam.objects.filter(term=term)
        if self.instance is not None:
            siblings = siblings.exclude(pk=self.instance.pk)
        if siblings.filter(order=order).exists():
            raise serializers.ValidationError("Another exam in this term already uses that order number.")

        total = sum((e.weight for e in siblings), Decimal("0")) + weight
        if total > 100:
            raise serializers.ValidationError(
                f"The weights for this term would add up to {total}%. They cannot go over 100%."
            )
        return attrs


class AdminTermListView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = TermSerializer
    queryset = Term.objects.prefetch_related("exams")


class AdminTermDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = TermSerializer
    queryset = Term.objects.prefetch_related("exams")


class AdminExamListView(ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ExamSerializer

    def get_queryset(self):
        qs = Exam.objects.select_related("term").order_by("term__start_date", "order")
        term_id = self.request.query_params.get("term_id", "")
        if term_id.isdigit():
            qs = qs.filter(term_id=int(term_id))
        return qs


class AdminExamDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ExamSerializer
    queryset = Exam.objects.select_related("term")