"""Convert the pre-quorum single-decision JSON into SectionRequestReview rows.

The `section_info['faculty_review']` key is left in place rather than
deleted: it costs nothing and is a cheap backstop if a tenant's conversion
turns out to have mismapped anything.
"""
from django.db import migrations
from django.utils.dateparse import parse_datetime


def _rows_from(review):
    """Oldest first: history entries, then the current decision."""
    entries = list(review.get('history') or [])
    entries.append(review)
    return [e for e in entries if e.get('decision')]


def convert_legacy_reviews(apps):
    FutureCourse = apps.get_model('future_sections', 'FutureCourse')
    SectionRequestReview = apps.get_model(
        'future_sections', 'SectionRequestReview')
    User = apps.get_model('cis', 'CustomUser')

    for fc in FutureCourse.objects.all():
        review = (fc.section_info or {}).get('faculty_review')
        if not review:
            continue
        if SectionRequestReview.objects.filter(future_course=fc).exists():
            continue

        latest = 0
        for index, entry in enumerate(_rows_from(review), start=1):
            user = User.objects.filter(pk=entry.get('reviewer_id')).first()
            if not user:
                continue
            SectionRequestReview.objects.create(
                future_course=fc, reviewer=user, round=index,
                role=entry.get('role') or 'Faculty',
                decision=entry.get('decision') or '',
                comment=entry.get('comment') or '',
                decided_on=parse_datetime(entry.get('reviewed_on') or '')
                if entry.get('reviewed_on') else None,
            )
            latest = index

        if latest:
            fc.review_round = latest
            fc.save(update_fields=['review_round'])


def forwards(apps, schema_editor):
    convert_legacy_reviews(apps)


def backwards(apps, schema_editor):
    """No-op on purpose.

    `SectionRequestReview` rows are derived data, and the
    `section_info['faculty_review']` JSON they were derived from is
    deliberately never deleted — so reversing this migration loses
    nothing by leaving the rows in place. Forward re-application is
    already idempotent (see the `exists()` guard in
    `convert_legacy_reviews`), so reverse-then-forward lands back in the
    same state.

    Deleting rows here would also be actively wrong: by the time anyone
    reverses this migration, the table can hold rows created by the live
    quorum review workflow, not just ones this migration produced, and
    there is nothing that distinguishes the two. Deleting indiscriminately
    would wipe live review history along with the legacy conversion.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('cis', '__first__'),
        ('future_sections', '0005_sectionrequestreview'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
