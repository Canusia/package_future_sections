from rest_framework import serializers

from cis.serializers.term import AcademicYearSerializer, TermSerializer
from cis.serializers.highschool import HighSchoolSerializer
from cis.serializers.highschool_admin import CustomUserSerializer
from cis.serializers.teacher import TeacherCourseCertificateSerializer

from .models import FutureProjection, FutureCourse, FutureSection


class FutureProjectionSerializer(serializers.ModelSerializer):
    academic_year = AcademicYearSerializer()
    highschool = HighSchoolSerializer()
    created_by = CustomUserSerializer()
    started_on = serializers.DateField(format='%m/%d/%Y')
    confirmed_administrators = serializers.CharField(read_only=True)
    confirmed_class_sections = serializers.CharField(read_only=True)
    confirmed_choice_class_sections = serializers.CharField(read_only=True)
    confirmed_facilitator_class_sections = serializers.CharField(read_only=True)
    meta = serializers.JSONField()

    class Meta:
        model = FutureProjection
        fields = '__all__'


class FutureCourseSerializer(serializers.ModelSerializer):
    term = TermSerializer()
    academic_year = AcademicYearSerializer()
    teacher_course = TeacherCourseCertificateSerializer()
    started_on = serializers.DateField(format='%m/%d/%Y')

    class Meta:
        model = FutureCourse
        fields = '__all__'


class FutureSectionSerializer(serializers.ModelSerializer):
    future_course = FutureCourseSerializer()

    class Meta:
        model = FutureSection
        fields = '__all__'
