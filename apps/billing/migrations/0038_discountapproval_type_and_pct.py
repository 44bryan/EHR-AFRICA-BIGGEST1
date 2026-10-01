from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0037_seed_cash_payment_gl_accounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='discountapproval',
            name='discount_type',
            field=models.CharField(
                choices=[('PERCENTAGE', 'Percentage (%)'), ('AMOUNT', 'Fixed Amount (FCFA)')],
                default='AMOUNT',
                help_text='Percentage (%) or Fixed Amount (FCFA)',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='discountapproval',
            name='requested_pct',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Percentage entered by cashier (only set when discount_type=PERCENTAGE)',
                max_digits=5,
                null=True,
            ),
        ),
        # Ensure REJECTED is a valid status value (was missing from original choices)
        migrations.AlterField(
            model_name='discountapproval',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending Supervisor Review'),
                    ('APPROVED', 'Approved'),
                    ('REJECTED', 'Rejected'),
                ],
                default='PENDING',
                max_length=20,
            ),
        ),
    ]
