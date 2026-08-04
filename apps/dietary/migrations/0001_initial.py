from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('ipd', '0007_vitalsigns_fluidbalance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DietOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('diet_type', models.CharField(
                    choices=[
                        ('REGULAR', 'Regular'), ('DIABETIC', 'Diabetic'),
                        ('LOW_SALT', 'Low Salt'), ('LOW_FAT', 'Low Fat'),
                        ('HIGH_PROTEIN', 'High Protein'), ('SOFT', 'Soft/Pureed'),
                        ('LIQUID', 'Full Liquid'), ('CLEAR_LIQUID', 'Clear Liquid'),
                        ('NPO', 'NPO (Nothing by Mouth)'), ('RENAL', 'Renal'),
                        ('CARDIAC', 'Cardiac'), ('KETOGENIC', 'Ketogenic'),
                        ('GLUTEN_FREE', 'Gluten-Free'), ('VEGETARIAN', 'Vegetarian'),
                        ('OTHER', 'Other'),
                    ],
                    default='REGULAR', max_length=20
                )),
                ('diet_type_other', models.CharField(blank=True, max_length=100)),
                ('status', models.CharField(
                    choices=[
                        ('ACTIVE', 'Active'), ('ON_HOLD', 'On Hold'),
                        ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled'),
                    ],
                    default='ACTIVE', max_length=20
                )),
                ('calorie_target', models.PositiveIntegerField(blank=True, null=True)),
                ('protein_target', models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True)),
                ('fluid_restriction', models.PositiveIntegerField(blank=True, null=True)),
                ('special_instructions', models.TextField(blank=True)),
                ('review_notes', models.TextField(blank=True)),
                ('admission', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='diet_orders', to='ipd.admission'
                )),
                ('ordered_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='diet_orders_issued', to=settings.AUTH_USER_MODEL
                )),
                ('reviewed_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='diet_orders_reviewed', to=settings.AUTH_USER_MODEL
                )),
                ('created_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('updated_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='DietaryRestriction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.CharField(
                    choices=[
                        ('NUTS', 'Nuts'), ('DAIRY', 'Dairy'), ('GLUTEN', 'Gluten'),
                        ('EGGS', 'Eggs'), ('SEAFOOD', 'Seafood'), ('SOY', 'Soy'), ('OTHER', 'Other'),
                    ],
                    max_length=20
                )),
                ('description', models.CharField(max_length=200)),
                ('severity', models.CharField(
                    choices=[
                        ('MILD', 'Mild'), ('MODERATE', 'Moderate'), ('SEVERE', 'Severe / Anaphylactic'),
                    ],
                    default='MILD', max_length=20
                )),
                ('admission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='dietary_restrictions', to='ipd.admission'
                )),
                ('recorded_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL
                )),
            ],
            options={'ordering': ['category']},
        ),
        migrations.CreateModel(
            name='NutritionalAssessment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('weight_kg', models.DecimalField(decimal_places=1, max_digits=5)),
                ('height_cm', models.DecimalField(decimal_places=1, max_digits=5)),
                ('bmi', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('must_score', models.PositiveSmallIntegerField()),
                ('nutritional_status', models.CharField(
                    choices=[
                        ('NORMAL', 'Normal'), ('AT_RISK', 'At Risk'),
                        ('MALNOURISHED', 'Malnourished'), ('OBESE', 'Obese'),
                    ],
                    default='NORMAL', max_length=20
                )),
                ('appetite', models.CharField(
                    choices=[
                        ('GOOD', 'Good'), ('FAIR', 'Fair'), ('POOR', 'Poor'), ('NONE', 'None'),
                    ],
                    default='GOOD', max_length=20
                )),
                ('feeding_route', models.CharField(
                    choices=[
                        ('ORAL', 'Oral'), ('NG_TUBE', 'Nasogastric Tube'),
                        ('PEG', 'PEG Tube'), ('IV', 'Parenteral (IV)'),
                    ],
                    default='ORAL', max_length=20
                )),
                ('notes', models.TextField(blank=True)),
                ('admission', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='nutritional_assessments', to='ipd.admission'
                )),
                ('assessed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='nutritional_assessments_done', to=settings.AUTH_USER_MODEL
                )),
                ('created_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('updated_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='MealPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('plan_date', models.DateField()),
                ('total_calories', models.PositiveIntegerField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('served', models.BooleanField(default=False)),
                ('served_at', models.DateTimeField(blank=True, null=True)),
                ('diet_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='meal_plans', to='dietary.dietorder'
                )),
                ('prepared_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='meal_plans_prepared', to=settings.AUTH_USER_MODEL
                )),
                ('created_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('updated_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
            ],
            options={'ordering': ['-plan_date'], 'unique_together': {('diet_order', 'plan_date')}},
        ),
        migrations.CreateModel(
            name='MealItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('meal_time', models.CharField(
                    choices=[
                        ('BREAKFAST', 'Breakfast'), ('MID_MORNING', 'Mid-Morning Snack'),
                        ('LUNCH', 'Lunch'), ('AFTERNOON', 'Afternoon Snack'),
                        ('DINNER', 'Dinner'), ('BEDTIME', 'Bedtime Snack'),
                    ],
                    max_length=20
                )),
                ('description', models.CharField(max_length=300)),
                ('calories_kcal', models.PositiveIntegerField(blank=True, null=True)),
                ('protein_g', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('carbs_g', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('fat_g', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('meal_plan', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='dietary.mealplan'
                )),
            ],
            options={'ordering': ['meal_time']},
        ),
    ]
