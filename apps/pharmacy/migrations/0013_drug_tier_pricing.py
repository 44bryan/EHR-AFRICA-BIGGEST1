"""
Add tier-based pricing fields to Drug model.
Each service tier (Standard, Express, VIP, Executive VIP, Staff, Outreach)
has its own selling price. Insurance uses cost_price + markup %.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0012_international_standards_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='drug',
            name='price_express',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Express / Fast-Track tier price', max_digits=10),
        ),
        migrations.AddField(
            model_name='drug',
            name='price_vip',
            field=models.DecimalField(decimal_places=2, default=0, help_text='VIP tier price', max_digits=10),
        ),
        migrations.AddField(
            model_name='drug',
            name='price_executive_vip',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Executive VIP tier price', max_digits=10),
        ),
        migrations.AddField(
            model_name='drug',
            name='price_staff',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Staff / employee price', max_digits=10),
        ),
        migrations.AddField(
            model_name='drug',
            name='price_outreach',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Outreach / community campaign price', max_digits=10),
        ),
        migrations.AddField(
            model_name='drug',
            name='insurance_markup_pct',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Markup % on cost_price for insured patients (e.g. 30 = cost + 30%)', max_digits=5),
        ),
    ]
