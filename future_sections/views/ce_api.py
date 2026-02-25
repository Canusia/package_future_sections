"""
CE Portal API ViewSets for Future Sections
"""
import json
import logging

from rest_framework import viewsets, serializers

from cis.utils import CIS_user_only
from cis.serializers.class_section import FutureCourseSerializer, FutureProjectionSerializer
from cis.serializers.teacher import TeacherCourseCertificateSerializer

from cis.models.crontab import CronLog
from ..models import FutureCourse, FutureProjection
from ..settings.future_sections import future_sections as fs_settings

from cis.models.teacher import TeacherCourseCertificate

logger = logging.getLogger(__name__)


class NotificationLogSerializer(serializers.ModelSerializer):
    summary = serializers.SerializerMethodField()
    detailed_log = serializers.SerializerMethodField()

    class Meta:
        model = CronLog
        fields = ['id', 'run_scheduled_for', 'run_started_on', 'run_completed_on', 'summary', 'detailed_log']

    def get_summary(self, obj):
        return obj.meta.get('summary', '')

    def get_detailed_log(self, obj):
        try:
            if obj.log_file:
                content = obj.log_file.read()
                obj.log_file.seek(0)
                return json.loads(content)
        except Exception:
            pass
        return {}


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for notification run history from CronLog"""
    serializer_class = NotificationLogSerializer
    permission_classes = [CIS_user_only]

    def get_queryset(self):
        return CronLog.objects.filter(
            cron__command='notify_pending_section_requests'
        ).order_by('-run_scheduled_for')


class PendingFutureClassSectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for pending future class sections (not yet responded to)"""
    serializer_class = TeacherCourseCertificateSerializer
    permission_classes = [CIS_user_only]

    def get_queryset(self):
        fs_setting_config = fs_settings.from_db()

        highschool_id = self.request.GET.get('highschool_id')
        academic_year_id = self.request.GET.get('academic_year')
        term_id = self.request.GET.get('term')
        teacher_id = self.request.GET.get('teacher_id')

        received_records = FutureCourse.objects.filter(
            academic_year__id=academic_year_id
        ).values_list('teacher_course__certificate_id', flat=True)

        records = TeacherCourseCertificate.objects.filter(
            course__status__in=fs_setting_config.get('course_status'),
            status__in=fs_setting_config.get('teacher_course_status')
        ).exclude(
            certificate_id__in=received_records
        )

        if highschool_id:
            records = records.filter(
                teacher_highschool__highschool__id=highschool_id
            )

        if teacher_id:
            records = records.filter(
                teacher_highschool__teacher__id=teacher_id
            )

        return records


class FutureProjectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for future projections by high school"""
    serializer_class = FutureProjectionSerializer
    permission_classes = [CIS_user_only]

    def get_queryset(self):
        highschool_id = self.request.GET.get('highschool_id')
        academic_year_id = self.request.GET.get('academic_year')

        records = FutureProjection.objects.filter(
            academic_year__id=academic_year_id
        )

        if highschool_id:
            records = records.filter(
                highschool__id=highschool_id
            )

        return records


class FutureClassSectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for future class sections"""
    serializer_class = FutureCourseSerializer
    permission_classes = [CIS_user_only]

    def get_queryset(self):
        highschool_id = self.request.GET.get('highschool_id')
        academic_year_id = self.request.GET.get('academic_year')
        term_id = self.request.GET.get('term')
        teacher_id = self.request.GET.get('teacher_id')
        offering_type = self.request.GET.get('offering_type')
        teacher_course_type = self.request.GET.get('teacher_course_type')

        if academic_year_id == '':
            records = FutureCourse.objects.filter()
        else:
            records = FutureCourse.objects.filter(
                academic_year__id=academic_year_id
            )

        if highschool_id:
            records = records.filter(
                teacher_course__teacher_highschool__highschool__id=highschool_id
            )

        if teacher_id:
            records = records.filter(
                teacher_course__teacher_highschool__teacher__id=teacher_id
            )

        if teacher_course_type:
            if teacher_course_type == 'applicant':
                records = records.filter(
                    teacher_course__status__iexact=teacher_course_type
                )

        if offering_type:
            if offering_type == 'not_teaching':
                records = records.filter(
                    section_info__teaching="no"
                )
            if offering_type == 'offering':
                records = records.filter(
                    section_info__teaching="yes"
                )

        # Filter by review status
        status = self.request.GET.get('status')
        if status:
            records = records.filter(status=status)

        return records
