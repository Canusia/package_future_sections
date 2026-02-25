"""
Permission classes for the future_sections app.

These provide role-based access control for HS Admins and Instructors.
"""

from rest_framework.permissions import BasePermission

from cis.utils import user_has_highschool_admin_role, user_has_instructor_role


class IsHSAdminOrInstructor(BasePermission):
    """
    Allow access to high school administrators or instructors.
    """
    message = "You must be a high school administrator or instructor to access this resource."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return (
            user_has_highschool_admin_role(request.user) or
            user_has_instructor_role(request.user)
        )


class IsHSAdminOnly(BasePermission):
    """
    Allow access only to high school administrators.
    """
    message = "You must be a high school administrator to access this resource."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return user_has_highschool_admin_role(request.user)


class IsInstructorOnly(BasePermission):
    """
    Allow access only to instructors.
    """
    message = "You must be an instructor to access this resource."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return user_has_instructor_role(request.user)


class CanAccessCourseRequest(BasePermission):
    """
    Verify user can access a specific course certificate.

    Access rules:
    - HS Admin: Certificate must be for a highschool they manage
    - Instructor: Certificate must belong to them (their TeacherCourseCertificate)
    """
    message = "You do not have permission to access this course."

    def has_object_permission(self, request, view, obj):
        """
        Check if user can access the TeacherCourseCertificate object.

        Args:
            obj: TeacherCourseCertificate instance
        """
        from cis.models.highschool_administrator import HSAdministrator
        from cis.models.teacher import Teacher

        if not request.user.is_authenticated:
            return False

        if user_has_highschool_admin_role(request.user):
            try:
                hs_admin = HSAdministrator.objects.get(user=request.user)
                highschools = hs_admin.get_highschools()
                return obj.teacher_highschool.highschool in highschools
            except HSAdministrator.DoesNotExist:
                return False

        elif user_has_instructor_role(request.user):
            try:
                teacher = Teacher.objects.get(user=request.user)
                return obj.teacher_highschool.teacher == teacher
            except Teacher.DoesNotExist:
                return False

        return False
