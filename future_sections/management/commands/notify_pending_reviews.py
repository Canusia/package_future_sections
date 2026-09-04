"""
Notify reviewers who have not decided on outstanding section requests.

Sends email reminders to reviewers with pending (undecided) section
requests. Only runs on dates configured in the future_sections settings.

Usage:
    python manage.py notify_pending_reviews
    python manage.py notify_pending_reviews -t "2024-01-15 08:00:00"
"""
import json
import logging

from django.core.management.base import BaseCommand

from cis.signals.crontab import cron_task_done, cron_task_started
from ...models import FutureCourse

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Notify reviewers who have not decided on outstanding section requests'

    def add_arguments(self, parser):
        parser.add_argument(
            '-t', '--time',
            type=str,
            help='Scheduled time of run (YYYY-MM-DD HH:MM:SS)'
        )

    def handle(self, *args, **kwargs):
        summary = ''
        detailed_log = {}

        if kwargs.get('time'):
            time = kwargs['time']
            cron_task_started.send(
                sender=self.__class__,
                task=self.__class__,
                scheduled_time=time
            )

        # Run notification logic
        summary, detailed_log = FutureCourse.notify_pending_reviews(*args, **kwargs)

        self.stdout.write(self.style.SUCCESS(summary))

        if kwargs.get('time'):
            cron_task_done.send(
                sender=self.__class__,
                task=self.__class__,
                scheduled_time=time,
                summary=summary,
                detailed_log=json.dumps(detailed_log)
            )
