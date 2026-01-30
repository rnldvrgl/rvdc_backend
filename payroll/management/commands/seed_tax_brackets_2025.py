"""
Management command to seed 2025 Philippine BIR tax brackets (TRAIN Law).

Tax brackets for weekly payroll computation based on TRAIN Law:
- Tax-exempt: Up to ₱4,808/week (₱20,832.99/month, ₱250,000/year)
- 15%: Over ₱4,808 up to ₱9,615/week
- 20%: Over ₱9,615 up to ₱19,231/week
- 25%: Over ₱19,231 up to ₱38,462/week
- 30%: Over ₱38,462 up to ₱153,846/week
- 35%: Over ₱153,846/week

Usage:
    python manage.py seed_tax_brackets_2025
    
    # Or via Docker:
    docker-compose exec api python manage.py seed_tax_brackets_2025
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from payroll.models import TaxBracket


class Command(BaseCommand):
    help = 'Seeds 2025 Philippine BIR tax brackets for weekly payroll (TRAIN Law)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🇵🇭 Seeding 2025 BIR Tax Brackets (TRAIN Law)...'))
        
        # Deactivate old tax brackets
        old_brackets = TaxBracket.objects.filter(is_active=True)
        if old_brackets.exists():
            count = old_brackets.update(is_active=False, effective_end=timezone.now().date())
            self.stdout.write(self.style.WARNING(f'   Deactivated {count} old tax bracket(s)'))
        
        # TRAIN Law tax brackets converted to weekly basis
        # Annual → Monthly → Weekly (÷ 12 months ÷ 4.33 weeks)
        
        brackets = [
            {
                'min_income': Decimal('0.00'),
                'max_income': Decimal('4808.00'),  # ₱250,000/year → ₱20,833/month → ₱4,808/week
                'base_tax': Decimal('0.00'),
                'rate': Decimal('0.0000'),  # 0% - Tax exempt
                'description': 'Tax-exempt (Minimum wage earners and income ≤ ₱250,000/year)'
            },
            {
                'min_income': Decimal('4808.01'),
                'max_income': Decimal('9615.00'),  # ₱400,000/year → ₱33,333/month → ₱7,692/week
                'base_tax': Decimal('0.00'),
                'rate': Decimal('0.15'),  # 15%
                'description': '15% on excess over ₱250,000/year (₱4,808/week)'
            },
            {
                'min_income': Decimal('9615.01'),
                'max_income': Decimal('19231.00'),  # ₱800,000/year → ₱66,667/month → ₱15,385/week
                'base_tax': Decimal('721.05'),  # (₱9,615 - ₱4,808) × 15%
                'rate': Decimal('0.20'),  # 20%
                'description': '₱22,500 + 20% on excess over ₱400,000/year (weekly base: ₱721.05)'
            },
            {
                'min_income': Decimal('19231.01'),
                'max_income': Decimal('38462.00'),  # ₱2,000,000/year → ₱166,667/month → ₱38,462/week
                'base_tax': Decimal('2644.25'),  # ₱721.05 + (₱19,231 - ₱9,615) × 20%
                'rate': Decimal('0.25'),  # 25%
                'description': '₱102,500 + 25% on excess over ₱800,000/year (weekly base: ₱2,644.25)'
            },
            {
                'min_income': Decimal('38462.01'),
                'max_income': Decimal('153846.00'),  # ₱8,000,000/year → ₱666,667/month → ₱153,846/week
                'base_tax': Decimal('7452.00'),  # ₱2,644.25 + (₱38,462 - ₱19,231) × 25%
                'rate': Decimal('0.30'),  # 30%
                'description': '₱402,500 + 30% on excess over ₱2,000,000/year (weekly base: ₱7,452)'
            },
            {
                'min_income': Decimal('153846.01'),
                'max_income': None,  # No upper limit
                'base_tax': Decimal('42067.20'),  # ₱7,452 + (₱153,846 - ₱38,462) × 30%
                'rate': Decimal('0.35'),  # 35%
                'description': '₱2,202,500 + 35% on excess over ₱8,000,000/year (weekly base: ₱42,067.20)'
            },
        ]
        
        created_count = 0
        self.stdout.write('')
        
        for bracket_data in brackets:
            bracket, created = TaxBracket.objects.update_or_create(
                min_income=bracket_data['min_income'],
                max_income=bracket_data['max_income'],
                effective_start='2025-01-01',
                defaults={
                    'base_tax': bracket_data['base_tax'],
                    'rate': bracket_data['rate'],
                    'effective_end': None,
                    'is_active': True,
                }
            )
            
            if created:
                created_count += 1
                
            # Display bracket info
            max_display = f"₱{bracket_data['max_income']:,.2f}" if bracket_data['max_income'] else "No limit"
            rate_display = f"{bracket_data['rate'] * 100:.0f}%"
            
            icon = '🆕' if created else '🔄'
            action = 'Created' if created else 'Updated'
            
            self.stdout.write(
                f"   {icon} {action}: ₱{bracket_data['min_income']:,.2f} - {max_display} "
                f"(Base: ₱{bracket_data['base_tax']:,.2f}, Rate: {rate_display})"
            )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✅ Successfully seeded {len(brackets)} tax brackets!'))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('📋 Tax Bracket Summary (Weekly Gross Pay):'))
        self.stdout.write('   • ₱0 - ₱4,808: Tax-exempt (0%)')
        self.stdout.write('   • ₱4,808 - ₱9,615: 15% on excess')
        self.stdout.write('   • ₱9,615 - ₱19,231: ₱721 + 20% on excess')
        self.stdout.write('   • ₱19,231 - ₱38,462: ₱2,644 + 25% on excess')
        self.stdout.write('   • ₱38,462 - ₱153,846: ₱7,452 + 30% on excess')
        self.stdout.write('   • Over ₱153,846: ₱42,067 + 35% on excess')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🎯 Next Steps:'))
        self.stdout.write('   1. Generate payroll for employees to test tax calculation')
        self.stdout.write('   2. Verify tax amounts in payslip detail page')
        self.stdout.write('   3. Check deduction breakdown shows correct BIR tax')
        self.stdout.write('')
