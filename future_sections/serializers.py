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
    submitted_by = CustomUserSerializer()
    started_on = serializers.DateField(format='%m/%d/%Y')
    course_display = serializers.SerializerMethodField()
    section_display = serializers.SerializerMethodField()

    class Meta:
        model = FutureCourse
        fields = '__all__'

    def get_course_display(self, obj):
        from .settings.future_sections import future_sections as fs_settings
        try:
            fs_config = fs_settings.from_db()
            template = fs_config.get('course_display_template', '{course_title}')
            course = obj.teacher_course.course
            return template.format(
                course_name=course.name or '',
                course_title=course.title,
                credit_hours=course.credit_hours,
            )
        except Exception:
            return obj.teacher_course.course.title if obj.teacher_course else ''

    def get_section_display(self, obj):
        try:
            teaching = obj.section_info.get('teaching') if obj.section_info else None
            return {
                'teaching': teaching,
                'displays': obj.section_display,
            }
        except Exception:
            return {'teaching': None, 'displays': []}


class FutureSectionSerializer(serializers.ModelSerializer):
    future_course = FutureCourseSerializer()

    class Meta:
        model = FutureSection
        fields = '__all__'
