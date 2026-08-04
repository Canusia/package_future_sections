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
    changed_teacher_sections = serializers.SerializerMethodField()

    class Meta:
        model = FutureCourse
        fields = '__all__'

    def get_course_display(self, obj):
        from .settings.future_sections import future_sections as fs_settings
        from .utils import render_course_display
        try:
            fs_config = fs_settings.from_db()
            template = fs_config.get('course_display_template', '{course_title}')
            return render_course_display(template, obj.teacher_course.course)
        except Exception:
            return obj.teacher_course.course.title if obj.teacher_course else ''

    def get_section_display(self, obj):
        try:
            info = obj.section_info or {}
            review = info.get('faculty_review') or {}
            faculty_review = None
            if review.get('decision'):
                mentor = review.get('mentor') or {}
                faculty_review = {
                    'decision': review.get('decision'),
                    'mentor_name': mentor.get('name', ''),
                }
            return {
                'teaching': info.get('teaching'),
                'displays': obj.section_display,
                'faculty_review': faculty_review,
            }
        except Exception:
            return {'teaching': None, 'displays': [], 'faculty_review': None}

    def get_changed_teacher_sections(self, obj):
        """Sections flagged 'teacher changed', for the CE outreach action.

        The CE index renders sections from pre-formatted display strings, so
        the structured values the compose box needs are surfaced here.
        """
        info = obj.section_info or {}
        out = []
        for index, section in enumerate(info.get('sections', []) or []):
            if (section or {}).get('teacher_changed') != 'yes':
                continue
            out.append({
                'index': index,
                'term_name': section.get('term_name', '') or '',
                'new_teacher_name': section.get('new_teacher_name', '') or '',
                'new_teacher_email': section.get('new_teacher_email', '') or '',
            })
        return out


class FutureSectionSerializer(serializers.ModelSerializer):
    future_course = FutureCourseSerializer()

    class Meta:
        model = FutureSection
        fields = '__all__'
