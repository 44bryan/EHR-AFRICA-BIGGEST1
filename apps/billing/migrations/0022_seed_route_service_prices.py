"""
Seed ServicePrice entries for auto-billing on patient routing.
These are the default prices for billable routing destinations.
Admins can edit prices via Django admin / Settings page.
"""
from django.db import migrations


def seed_route_prices(apps, schema_editor):
    ServicePrice = apps.get_model('billing', 'ServicePrice')

    entries = [
        {
            'code': 'SVC-REFRACTION',
            'name': 'Refraction (Optometry)',
            'category': 'INVEST',
            'price': 5000,
        },
        {
            'code': 'SVC-CYCLO',
            'name': 'Cycloplegic Refraction',
            'category': 'INVEST',
            'price': 7500,
        },
        {
            'code': 'SVC-VA-CHECK',
            'name': 'Visual Acuity Assessment',
            'category': 'INVEST',
            'price': 2000,
        },
        {
            'code': 'SVC-ORTHOPTICS',
            'name': 'Orthoptic Assessment',
            'category': 'INVEST',
            'price': 10000,
        },
        {
            'code': 'SVC-CONTACT-LENS',
            'name': 'Contact Lens Fitting',
            'category': 'OPTICAL',
            'price': 15000,
        },
        {
            'code': 'SVC-LOW-VISION',
            'name': 'Low Vision Assessment',
            'category': 'INVEST',
            'price': 10000,
        },
        {
            'code': 'SVC-COUNSELING',
            'name': 'Patient Counseling Session',
            'category': 'CONSULT',
            'price': 5000,
        },
    ]

    for entry in entries:
        ServicePrice.objects.get_or_create(
            code=entry['code'],
            defaults={
                'name': entry['name'],
                'category': entry['category'],
                'price': entry['price'],
                'is_active': True,
            },
        )


def reverse(apps, schema_editor):
    ServicePrice = apps.get_model('billing', 'ServicePrice')
    ServicePrice.objects.filter(code__startswith='SVC-').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0021_alter_cashdesk_id_alter_cashdesk_is_deleted_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_route_prices, reverse),
    ]
