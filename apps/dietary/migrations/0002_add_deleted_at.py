from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Patch: add missing deleted_at column to all dietary tables that inherit
    from TimeStampedModel / AuditModel.  The initial migration omitted it.
    """

    dependencies = [
        ('dietary', '0001_initial'),
    ]

    operations = [
        # DietOrder
        migrations.AddField(
            model_name='dietorder',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # NutritionalAssessment
        migrations.AddField(
            model_name='nutritionalassessment',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # MealPlan
        migrations.AddField(
            model_name='mealplan',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # DietaryRestriction (TimeStampedModel — needs is_deleted + deleted_at)
        migrations.AddField(
            model_name='dietaryrestriction',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='dietaryrestriction',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # MealItem (TimeStampedModel — needs is_deleted + deleted_at)
        migrations.AddField(
            model_name='mealitem',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='mealitem',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
