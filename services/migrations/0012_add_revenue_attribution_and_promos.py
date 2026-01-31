# Generated manually for two-stall architecture implementation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0011_applianceitemused_expense_and_more'),
    ]

    operations = [
        # Add revenue tracking fields to Service model
        migrations.AddField(
            model_name='service',
            name='main_stall_revenue',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Revenue attributed to Main stall (labor + aircon units)',
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='sub_stall_revenue',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Revenue attributed to Sub stall (parts)',
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='total_revenue',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Total service revenue (main + sub)',
                max_digits=10,
            ),
        ),

        # Add promo field to ServiceAppliance (track original labor amount)
        migrations.AddField(
            model_name='serviceappliance',
            name='labor_original_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Original labor fee before promo discount (e.g., free installation)',
                max_digits=10,
                null=True,
            ),
        ),

        # Add promo fields to ApplianceItemUsed (track free quantity)
        migrations.AddField(
            model_name='applianceitemused',
            name='free_quantity',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Quantity given free as part of promotion',
            ),
        ),
        migrations.AddField(
            model_name='applianceitemused',
            name='promo_name',
            field=models.CharField(
                blank=True,
                help_text="Name of applied promotion (e.g., 'Free 10ft Copper Tube Promo')",
                max_length=100,
            ),
        ),
    ]
