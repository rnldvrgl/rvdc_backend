from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("attendance", "0015_work_request"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS attendance_status_active_idx "
                "ON attendance_dailyattendance (status) WHERE is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS attendance_status_active_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS attendance_approved_at_idx "
                "ON attendance_dailyattendance (approved_at) WHERE status = 'APPROVED' AND is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS attendance_approved_at_idx;"
            ),
        ),
    ]
