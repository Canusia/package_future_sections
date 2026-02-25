"""
Signals for Future Sections app

Handles email notifications when FutureCourse status changes.
"""
import logging

from django.conf import settings
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.template import Context, Template
from django.template.loader import get_template

from mailer import send_html_mail

from .models import FutureCourse
from .settings.future_sections import future_sections as fs_settings

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=FutureCourse)
def future_course_status_changed(sender, instance, **kwargs):
    """
    Send email notification when FutureCourse status changes to 'reviewed'.

    Sends to both the instructor (teacher) and the submitter (if different).
    """
    # Get previous status using FieldTracker
    previous_status = instance.tracker.previous('status')
    current_status = instance.status

    # Only proceed if status changed to 'reviewed'
    if previous_status == current_status:
        return

    if current_status != 'reviewed':
        return

    # Load settings
    email_settings = fs_settings.from_db()

    # Check if notifications are enabled
    if email_settings.get('send_reviewed_notification', 'No') != 'Yes':
        return

    # Get subject and message from settings
    subject = email_settings.get('reviewed_email_subject')
    message_template = email_settings.get('reviewed_email_message')

    if not subject or not message_template:
        logger.warning('Reviewed notification enabled but subject or message not configured')
        return

    # Navigate relationship chain to get instructor details
    try:
        teacher_course = instance.teacher_course
        teacher_highschool = teacher_course.teacher_highschool
        teacher = teacher_highschool.teacher
        user = teacher.user
        highschool = teacher_highschool.highschool
        course = teacher_course.course
    except AttributeError as e:
        logger.error(f'Could not resolve FutureCourse relationships: {e}')
        return

    # Build context for template rendering
    message = Template(message_template)
    context = Context({
        'course': str(course),
        'highschool': highschool.name,
        'instructor_first_name': user.first_name,
        'instructor_last_name': user.last_name,
    })

    text_body = message.render(context)

    # Render HTML email using standard template
    template = get_template('cis/email.html')
    html_body = template.render({
        'message': text_body
    })

    # Build recipient list - include both teacher and submitter
    recipients = set()

    # Add teacher email
    teacher_email = user.email or user.secondary_email
    if teacher_email:
        recipients.add(teacher_email)

    # Add submitter email (if different from teacher)
    submitted_by = instance.meta.get('submitted_by', {})
    submitter_email = submitted_by.get('email')
    if submitter_email:
        recipients.add(submitter_email)

    if not recipients:
        logger.warning(f'No recipients for FutureCourse {instance.id} reviewed notification')
        return

    to = list(recipients)

    # DEBUG mode: redirect to test email address
    if getattr(settings, 'DEBUG', True):
        to = ['kadaji@gmail.com']

    # Send the email
    try:
        send_html_mail(
            subject,
            text_body,
            html_body,
            settings.DEFAULT_FROM_EMAIL,
            to
        )
        logger.info(f'Sent reviewed notification to {to} for FutureCourse {instance.id}')
    except Exception as e:
        logger.error(f'Failed to send reviewed notification: {e}')
