# Generated manually for enhanced notification system

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        # Add new fields to Notification model
        migrations.AddField(
            model_name='notification',
            name='priority',
            field=models.CharField(
                choices=[
                    ('low', 'Low'),
                    ('normal', 'Normal'),
                    ('high', 'High'),
                    ('urgent', 'Urgent'),
                ],
                default='normal',
                help_text='Priority level of notification',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='title',
            field=models.CharField(
                default='Notification',
                help_text='Notification title/heading',
                max_length=200,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='notification',
            name='action_url',
            field=models.CharField(
                blank=True,
                help_text='URL/route to navigate when notification is clicked',
                max_length=500,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='action_text',
            field=models.CharField(
                blank=True,
                help_text="Text for action button (e.g., 'View Service', 'View Payment')",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='read_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When notification was marked as read',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='is_archived',
            field=models.BooleanField(
                default=False,
                help_text='Whether notification has been archived',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='archived_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When notification was archived',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='expires_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When notification should expire (optional)',
                null=True,
            ),
        ),

        # Modify existing fields
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(
                choices=[
                    ('payment_received', 'Payment Received'),
                    ('payment_reminder', 'Payment Reminder'),
                    ('payment_overdue', 'Payment Overdue'),
                    ('service_created', 'New Service Created'),
                    ('service_updated', 'Service Updated'),
                    ('service_completed', 'Service Completed'),
                    ('service_cancelled', 'Service Cancelled'),
                    ('service_assigned', 'Service Assigned to You'),
                    ('stock_low', 'Low Stock Alert'),
                    ('stock_out', 'Out of Stock Alert'),
                    ('stock_reorder', 'Reorder Point Reached'),
                    ('warranty_claim_created', 'New Warranty Claim'),
                    ('warranty_claim_approved', 'Warranty Claim Approved'),
                    ('warranty_claim_rejected', 'Warranty Claim Rejected'),
                    ('warranty_expiring', 'Warranty Expiring Soon'),
                    ('free_cleaning_available', 'Free Cleaning Available'),
                    ('sale_created', 'New Sale Created'),
                    ('sale_voided', 'Sale Voided'),
                    ('system_alert', 'System Alert'),
                    ('report_ready', 'Report Ready'),
                ],
                help_text='Type of notification',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='data',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Additional structured data (IDs, links, etc.)',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='message',
            field=models.TextField(
                help_text='Notification message content',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='is_read',
            field=models.BooleanField(
                default=False,
                help_text='Whether notification has been read',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='user',
            field=models.ForeignKey(
                help_text='User who will receive this notification',
                on_delete=models.deletion.CASCADE,
                related_name='notifications',
                to='users.customuser',
            ),
        ),

        # Add indexes for performance
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['user', '-created_at'],
                name='notif_user_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['user', 'is_read'],
                name='notif_user_read_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['type'],
                name='notif_type_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(
                fields=['priority'],
                name='notif_priority_idx',
            ),
        ),
    ]
