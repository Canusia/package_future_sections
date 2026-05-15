"""
One-shot: populate cycle_terms from the existing single academic_year setting.

For tenants upgrading from the AY-only schema. Run once after deploying the
per-term cycle feature. Idempotent: skips if cycle_terms is already set.
"""
from django.core.management.base import BaseCommand
from cis.models.settings import Setting
from cis.models.term import Term


class Command(BaseCommand):
    help = "Populate cycle_terms from the existing academic_year setting."

    def handle(self, *args, **opts):
        try:
            setting = Setting.objects.get(key='cis_future_sections')
        except Setting.DoesNotExist:
            self.stdout.write('No cis_future_sections setting found; nothing to migrate.')
            return

        cfg = setting.value or {}
        if cfg.get('cycle_terms'):
            self.stdout.write('cycle_terms already set; skipping.')
            return

        ay_id = cfg.get('academic_year')
        if not ay_id:
            self.stdout.write('No academic_year on the setting; nothing to migrate.')
            return

        term_ids = list(Term.objects.filter(
            academic_year__id=ay_id,
        ).values_list('id', flat=True))
        cfg['cycle_terms'] = [str(tid) for tid in term_ids]
        # lookback_terms stays empty — CE Staff must pick explicitly.
        setting.value = cfg
        setting.save()
        self.stdout.write(
            f'Set cycle_terms to {len(term_ids)} term(s) from AY {ay_id}. '
            f'Reminder: set lookback_terms manually in CE Portal > Settings.'
        )
