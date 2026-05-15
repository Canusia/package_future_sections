"""DRF serializer + viewset for section-request review (portal-agnostic)."""
import logging

from django.core.exceptions import FieldError, ObjectDoesNotExist
from django.utils.html import escape

from rest_framework import serializers, viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated

from .helpers import visible_future_courses_for, get_faculty_review

logger = logging.getLogger(__name__)


class IsReviewer(BasePermission):
    """User has at least one Active CourseAdministrator row with a role
    in the configured reviewer_roles."""
    message = 'Reviewer role required.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # If the user can see any future courses, they're allowed to list/detail
        # (object-level visibility is enforced by the queryset).
        return visible_future_courses_for(request.user).exists()


class SectionRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    course_display = serializers.SerializerMethodField()
    highschool_name = serializers.SerializerMethodField()
    instructor_name = serializers.SerializerMethodField()
    academic_year = serializers.SerializerMethodField()
    submitted_by_name = serializers.SerializerMethodField()
    submitted_on = serializers.SerializerMethodField()
    status = serializers.CharField()
    faculty_review_status = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()

    def __init__(self, *args, detail_url_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._detail_url_name = detail_url_name

    def get_course_display(self, obj):
        try:
            course = obj.teacher_course.course
            label = course.name or f'{course.cohort.designator} {course.catalog_number}'
            return f'{label} - {course.title}'
        except (AttributeError, ObjectDoesNotExist):
            return ''

    def get_highschool_name(self, obj):
        try:
            return obj.teacher_course.teacher_highschool.highschool.name
        except (AttributeError, ObjectDoesNotExist):
            return ''

    def get_instructor_name(self, obj):
        try:
            u = obj.teacher_course.teacher_highschool.teacher.user
            return f'{u.last_name}, {u.first_name}'.strip(', ')
        except (AttributeError, ObjectDoesNotExist):
            return ''

    def get_academic_year(self, obj):
        return obj.academic_year.name if obj.academic_year else ''

    def get_submitted_on(self, obj):
        d = obj.submitted_on or obj.started_on
        return d.strftime('%m/%d/%Y') if d else ''

    def get_submitted_by_name(self, obj):
        u = obj.submitted_by
        if not u:
            return ''
        return f'{u.first_name} {u.last_name}'.strip()

    def get_faculty_review_status(self, obj):
        review = get_faculty_review(obj)
        if not review or not review.get('decision'):
            return 'Pending'
        if review['decision'] == 'approved':
            mentor_name = ((review.get('mentor') or {}).get('name') or '').strip()
            if mentor_name:
                return ('Approved'
                        f'<br><small class="text-muted">{escape(mentor_name)}</small>')
            return 'Approved'
        return 'Not Approved'

    def get_detail_url(self, obj):
        from django.urls import reverse
        name = self._detail_url_name or self.context.get('detail_url_name')
        if not name:
            return ''
        return reverse(name, args=[str(obj.id)])


class SectionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """Generic review viewset. Mounted under both faculty and CE portals;
    each mount passes its own `detail_url_name` via get_serializer_context."""
    permission_classes = [IsAuthenticated, IsReviewer]
    serializer_class = SectionRequestSerializer

    #: Override on subclass or via .as_view(detail_url_name=...) so the
    #: serializer can reverse the right portal-namespaced URL.
    detail_url_name = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['detail_url_name'] = self.detail_url_name
        return ctx

    def get_queryset(self):
        qs = visible_future_courses_for(self.request.user)
        academic_year = self.request.query_params.get('academic_year')
        if academic_year:
            qs = qs.filter(academic_year_id=academic_year)
        tab = self.request.query_params.get('tab')
        if tab in ('pending', 'reviewed'):
            want_pending = (tab == 'pending')
            ids = [
                obj.pk for obj in qs
                if (not (obj.section_info or {}).get('faculty_review', {}).get('decision'))
                   == want_pending
            ]
            qs = qs.filter(pk__in=ids)
        return qs.order_by('-started_on')

    def filter_queryset(self, queryset):
        try:
            return super().filter_queryset(queryset)
        except FieldError:
            logger.warning(
                'DataTables ORDER BY failed; falling back to default order. params=%s',
                dict(self.request.query_params),
            )
            return queryset
