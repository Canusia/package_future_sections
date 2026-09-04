from rest_framework import serializers

from cis.serializers.term import AcademicYearSerializer, TermSerializer
from cis.serializers.highschool import HighSchoolSerializer
from cis.serializers.highschool_admin import CustomUserSerializer
from cis.serializers.teacher import TeacherCourseCertificateSerializer

from .models import (
    FutureProjection, FutureCourse, FutureSection, SectionRequestReview)


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

    def _review_summary(self, obj):
        if not obj.review_round:
            return None
        rows = list(
            obj.reviews.filter(round=obj.review_round)
            .select_related('reviewer').order_by('created_on'))
        decided = [r for r in rows if r.decision]
        labels = dict(SectionRequestReview.DECISION_CHOICES)

        def _name(user):
            if not user:
                return ''
            return f'{user.first_name} {user.last_name}'.strip() or user.username

        return {
            'round': obj.review_round,
            'total': len(rows),
            'decided': len(decided),
            'approved': sum(1 for r in decided if r.decision == 'approved'),
            'not_approved': sum(
                1 for r in decided if r.decision == 'not_approved'),
            'reviewers': [
                {
                    'name': _name(r.reviewer),
                    'role': r.role,
                    'decision': labels.get(r.decision, ''),
                    'decision_code': r.decision or '',
                    'decided_on': (
                        r.decided_on.strftime('%m/%d/%Y')
                        if r.decided_on else ''),
                    'comment': r.comment or '',
                }
                for r in rows
            ],
        }

    def get_section_display(self, obj):
        try:
            info = obj.section_info or {}
            return {
                'teaching': info.get('teaching'),
                'displays': obj.section_display,
                'review': self._review_summary(obj),
                # Nested here as well as exposed top-level because
                # rest_framework_datatables strips any field the browser did
                # not name in a columns[i][data] param, and there is no
                # <th data-data="changed_teacher_sections"> to request it.
                'changed_teacher_sections':
                    self.get_changed_teacher_sections(obj),
            }
        except Exception:
            return {'teaching': None, 'displays': [], 'review': None,
                    'changed_teacher_sections': []}

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
