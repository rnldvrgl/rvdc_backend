"""
Management command to seed 2025 Philippine government benefit rates.

Updated rates as of 2025:
- SSS: 15% total (5% employee, 10% employer) on max ₱30,000 MSC
- PhilHealth: 5% total (2.5% employee, 2.5% employer) on ₱10,000-₱100,000 ceiling
- Pag-IBIG: 2% each (capped at ₱200) on max ₱10,000 monthly
- BIR: Progressive tax rates (TRAIN Law)

Usage:
    python manage.py seed_government_benefits_2025

    # Or via Docker:
    docker-compose exec api python manage.py seed_government_benefits_2025
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from payroll.models import GovernmentBenefit


class Command(BaseCommand):
    help = 'Seeds 2025 Philippine government benefit contribution rates'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🇵🇭 Seeding 2025 Philippine Government Benefits...'))

        # Deactivate any existing benefits before creating new ones
        old_benefits = GovernmentBenefit.objects.filter(is_active=True)
        if old_benefits.exists():
            count = old_benefits.update(is_active=False, effective_end=timezone.now().date())
            self.stdout.write(self.style.WARNING(f'   Deactivated {count} old benefit(s)'))

        benefits_created = []

        # ============================================================
        # SSS - Social Security System (2025)
        # ============================================================
        # Total: 15% (5% employee, 10% employer)
        # Weekly calculation: Monthly rate ÷ 4.33 weeks
        # Max MSC: ₱30,000/month = ~₱6,928/week
        # Note: Using percentage method for flexibility

        sss, created = GovernmentBenefit.objects.update_or_create(
            benefit_type='sss',
            name='SSS Contribution - 2025',
            defaults={
                'calculation_method': 'percentage',
                'employee_share_rate': Decimal('0.05'),  # 5%
                'employer_share_rate': Decimal('0.10'),  # 10%
                'effective_start': '2025-01-01',
                'effective_end': None,
                'is_active': True,
                'description': (
                    'Social Security System contribution for 2025. '
                    'Total rate: 15% (Employee: 5%, Employer: 10%). '
                    'Maximum Monthly Salary Credit: ₱30,000. '
                    'Weekly computation applied on gross pay.'
                )
            }
        )
        benefits_created.append(('SSS', created))

        # ============================================================
        # PhilHealth - Philippine Health Insurance (2025)
        # ============================================================
        # Total: 5% (2.5% employee, 2.5% employer)
        # Salary ceiling: ₱10,000 - ₱100,000/month
        # Weekly equivalent: ~₱2,309 - ₱23,094
        # Max monthly premium: ₱5,000 total (₱2,500 each)
        # Max weekly premium: ~₱1,155 total (₱577.50 each)

        philhealth, created = GovernmentBenefit.objects.update_or_create(
            benefit_type='philhealth',
            name='PhilHealth Contribution - 2025',
            defaults={
                'calculation_method': 'percentage',
                'employee_share_rate': Decimal('0.025'),  # 2.5%
                'employer_share_rate': Decimal('0.025'),  # 2.5%
                'effective_start': '2025-01-01',
                'effective_end': None,
                'is_active': True,
                'description': (
                    'Philippine Health Insurance Corporation premium for 2025. '
                    'Total rate: 5% (Employee: 2.5%, Employer: 2.5%). '
                    'Monthly salary ceiling: ₱10,000 - ₱100,000. '
                    'Maximum weekly contribution: ~₱577.50 per party. '
                    'Applied on gross pay within ceiling limits.'
                )
            }
        )
        benefits_created.append(('PhilHealth', created))

        # ============================================================
        # Pag-IBIG - Home Development Mutual Fund (2025)
        # ============================================================
        # Rate: 2% each (employee and employer)
        # Monthly cap: ₱200 per party (based on ₱10,000 max compensation)
        # Weekly cap: ₱200 ÷ 4.33 = ~₱46.21 per party
        # Using fixed amount for simplicity at the cap

        pagibig, created = GovernmentBenefit.objects.update_or_create(
            benefit_type='pagibig',
            name='Pag-IBIG Contribution - 2025',
            defaults={
                'calculation_method': 'fixed',
                'employee_share_amount': Decimal('46.21'),  # Weekly cap
                'employer_share_amount': Decimal('46.21'),  # Weekly cap
                'effective_start': '2025-01-01',
                'effective_end': None,
                'is_active': True,
                'description': (
                    'Home Development Mutual Fund (HDMF) savings for 2025. '
                    'Rate: 2% of monthly compensation. '
                    'Maximum contribution: ₱200/month per party. '
                    'Weekly fixed amount: ₱46.21 (₱200 ÷ 4.33 weeks). '
                    'Capped at ₱10,000 monthly compensation.'
                )
            }
        )
        benefits_created.append(('Pag-IBIG', created))

        # ============================================================
        # BIR - Withholding Tax (2025 TRAIN Law)
        # ============================================================
        # Fixed amount approach - admin sets weekly withholding per employee via overrides

        bir, created = GovernmentBenefit.objects.update_or_create(
            benefit_type='bir_tax',
            name='BIR Withholding Tax - 2025 (TRAIN Law)',
            defaults={
                'calculation_method': 'fixed',
                'employee_share_rate': None,
                'employer_share_rate': None,
                'employee_share_amount': Decimal('0.00'),
                'employer_share_amount': None,
                'effective_start': '2025-01-01',
                'effective_end': None,
                'is_active': True,
                'description': (
                    'Bureau of Internal Revenue withholding tax under TRAIN Law. '
                    'Set per-employee withholding amounts via Employee Benefit Overrides.'
                )
            }
        )
        benefits_created.append(('BIR Tax', created))

        # ============================================================
        # Summary Report
        # ============================================================
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Government Benefits Seeded Successfully!'))
        self.stdout.write('')

        for name, was_created in benefits_created:
            action = 'Created' if was_created else 'Updated'
            icon = '🆕' if was_created else '🔄'
            self.stdout.write(f'   {icon} {action}: {name}')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('📋 Important Notes:'))
        self.stdout.write('   • SSS: 5% employee, 10% employer (max ₱30k MSC)')
        self.stdout.write('   • PhilHealth: 2.5% each (₱10k-₱100k ceiling)')
        self.stdout.write('   • Pag-IBIG: Fixed ₱46.21/week (₱200/month cap)')
        self.stdout.write('   • BIR Tax: Set per-employee via Benefit Overrides')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🎯 Next Steps:'))
        self.stdout.write('   1. Navigate to Settings → Government Benefits in frontend')
        self.stdout.write('   2. Verify benefit rates are displayed correctly')
        self.stdout.write('   3. Generate test payroll to confirm deductions')
        self.stdout.write('')
