"""
Management command to migrate data from cis future_sections tables to
future_sections app tables.

Usage:
    python manage.py migrate_future_sections_data              # Dry run
    python manage.py migrate_future_sections_data --execute    # Actually migrate
    python manage.py migrate_future_sections_data --clear      # Clear new tables first
    python manage.py migrate_future_sections_data --verify     # Verify data after migration
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Migrate future sections data from cis tables to future_sections tables'

    def add_arguments(self, parser):
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Actually execute the migration (default is dry run)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear destination tables before migrating',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify data counts after migration',
        )

    def table_exists(self, table_name):
        """Check if a table exists in the database."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, [table_name])
            return cursor.fetchone()[0]

    def get_table_count(self, table_name):
        """Get the count of records in a table."""
        if not self.table_exists(table_name):
            return None
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
            return cursor.fetchone()[0]

    def handle(self, *args, **options):
        execute = options['execute']
        clear = options['clear']
        verify = options['verify']

        # Define table mappings
        source_tables = [
            'cis_futureprojection',
            'cis_futurecourse',
            'cis_futuresection'
        ]
        dest_tables = [
            'future_sections_futureprojection',
            'future_sections_futurecourse',
            'future_sections_futuresection'
        ]

        # Check source tables exist
        self.stdout.write(self.style.HTTP_INFO('Checking source tables...'))
        source_exists = {}
        for table in source_tables:
            exists = self.table_exists(table)
            source_exists[table] = exists
            status = self.style.SUCCESS('exists') if exists else self.style.WARNING('missing')
            self.stdout.write(f'  {table}: {status}')

        if not any(source_exists.values()):
            self.stdout.write(self.style.WARNING('No source tables found. Nothing to migrate.'))
            return

        # Check destination tables exist
        self.stdout.write(self.style.HTTP_INFO('\nChecking destination tables...'))
        dest_exists = {}
        for table in dest_tables:
            exists = self.table_exists(table)
            dest_exists[table] = exists
            status = self.style.SUCCESS('exists') if exists else self.style.ERROR('missing')
            self.stdout.write(f'  {table}: {status}')

        if not all(dest_exists.values()):
            self.stdout.write(self.style.ERROR(
                '\nDestination tables do not exist. Run migrations first:\n'
                '  python manage.py makemigrations future_sections\n'
                '  python manage.py migrate'
            ))
            return

        # Count source records
        self.stdout.write(self.style.HTTP_INFO('\nSource record counts:'))
        source_counts = {}
        for table in source_tables:
            if source_exists[table]:
                count = self.get_table_count(table)
                source_counts[table] = count
                self.stdout.write(f'  {table}: {count}')

        # Count destination records (before migration)
        self.stdout.write(self.style.HTTP_INFO('\nDestination record counts (before):'))
        dest_counts_before = {}
        for table in dest_tables:
            count = self.get_table_count(table)
            dest_counts_before[table] = count
            self.stdout.write(f'  {table}: {count}')

        if not execute:
            self.stdout.write(self.style.WARNING(
                '\nDry run complete. Use --execute to perform migration.'
            ))
            return

        # Execute migration
        self.stdout.write(self.style.HTTP_INFO('\nStarting migration...'))

        try:
            with transaction.atomic():
                if clear:
                    self.stdout.write('Clearing destination tables...')
                    with connection.cursor() as cursor:
                        # Delete in reverse order due to FK constraints
                        cursor.execute('DELETE FROM future_sections_futuresection')
                        self.stdout.write(f'  Cleared future_sections_futuresection')
                        cursor.execute('DELETE FROM future_sections_futurecourse')
                        self.stdout.write(f'  Cleared future_sections_futurecourse')
                        cursor.execute('DELETE FROM future_sections_futureprojection')
                        self.stdout.write(f'  Cleared future_sections_futureprojection')

                # Migrate FutureProjection
                if source_exists['cis_futureprojection']:
                    self.stdout.write('Migrating FutureProjection...')
                    with connection.cursor() as cursor:
                        cursor.execute('''
                            INSERT INTO future_sections_futureprojection
                                (id, academic_year_id, highschool_id, created_by_id, meta, started_on)
                            SELECT id, academic_year_id, highschool_id, created_by_id, meta, started_on
                            FROM cis_futureprojection
                            ON CONFLICT (id) DO NOTHING
                        ''')
                        self.stdout.write(
                            self.style.SUCCESS(f'  Migrated {cursor.rowcount} FutureProjection records')
                        )

                # Migrate FutureCourse
                if source_exists['cis_futurecourse']:
                    self.stdout.write('Migrating FutureCourse...')
                    with connection.cursor() as cursor:
                        cursor.execute('''
                            INSERT INTO future_sections_futurecourse
                                (id, academic_year_id, teacher_course_id, term_id, meta,
                                 started_on, last_viewed_on, submitted_on, section_info)
                            SELECT id, academic_year_id, teacher_course_id, term_id, meta,
                                   started_on, last_viewed_on, submitted_on, section_info
                            FROM cis_futurecourse
                            ON CONFLICT (id) DO NOTHING
                        ''')
                        self.stdout.write(
                            self.style.SUCCESS(f'  Migrated {cursor.rowcount} FutureCourse records')
                        )

                # Migrate FutureSection
                if source_exists['cis_futuresection']:
                    self.stdout.write('Migrating FutureSection...')
                    with connection.cursor() as cursor:
                        cursor.execute('''
                            INSERT INTO future_sections_futuresection
                                (id, future_course_id, section_info, added_on)
                            SELECT id, future_course_id, section_info, added_on
                            FROM cis_futuresection
                            ON CONFLICT (id) DO NOTHING
                        ''')
                        self.stdout.write(
                            self.style.SUCCESS(f'  Migrated {cursor.rowcount} FutureSection records')
                        )

            self.stdout.write(self.style.SUCCESS('\nMigration completed successfully!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\nMigration failed: {e}'))
            raise

        # Verify if requested
        if verify:
            self.stdout.write(self.style.HTTP_INFO('\nVerifying migration...'))

            # Count destination records (after migration)
            self.stdout.write('Destination record counts (after):')
            all_match = True
            for src, dest in zip(source_tables, dest_tables):
                if source_exists[src]:
                    src_count = source_counts[src]
                    dest_count = self.get_table_count(dest)
                    match = src_count == dest_count
                    if match:
                        self.stdout.write(
                            self.style.SUCCESS(f'  {dest}: {dest_count} (matches source)')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'  {dest}: {dest_count} (source has {src_count})')
                        )
                        all_match = False

            if all_match:
                self.stdout.write(self.style.SUCCESS('\nVerification passed!'))
            else:
                self.stdout.write(self.style.WARNING(
                    '\nVerification completed with warnings. '
                    'Some records may have been skipped due to conflicts.'
                ))
