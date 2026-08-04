from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel, AuditModel


class DietType(models.TextChoices):
    REGULAR = 'REGULAR', 'Regular'
    DIABETIC = 'DIABETIC', 'Diabetic'
    LOW_SALT = 'LOW_SALT', 'Low Salt'
    LOW_FAT = 'LOW_FAT', 'Low Fat'
    HIGH_PROTEIN = 'HIGH_PROTEIN', 'High Protein'
    SOFT = 'SOFT', 'Soft/Pureed'
    LIQUID = 'LIQUID', 'Full Liquid'
    CLEAR_LIQUID = 'CLEAR_LIQUID', 'Clear Liquid'
    NPO = 'NPO', 'NPO (Nothing by Mouth)'
    RENAL = 'RENAL', 'Renal'
    CARDIAC = 'CARDIAC', 'Cardiac'
    KETOGENIC = 'KETOGENIC', 'Ketogenic'
    GLUTEN_FREE = 'GLUTEN_FREE', 'Gluten-Free'
    VEGETARIAN = 'VEGETARIAN', 'Vegetarian'
    OTHER = 'OTHER', 'Other'


class MealTime(models.TextChoices):
    BREAKFAST = 'BREAKFAST', 'Breakfast'
    MID_MORNING = 'MID_MORNING', 'Mid-Morning Snack'
    LUNCH = 'LUNCH', 'Lunch'
    AFTERNOON = 'AFTERNOON', 'Afternoon Snack'
    DINNER = 'DINNER', 'Dinner'
    BEDTIME = 'BEDTIME', 'Bedtime Snack'


class DietOrderStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    ON_HOLD = 'ON_HOLD', 'On Hold'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class AllergyCategory(models.TextChoices):
    NUTS = 'NUTS', 'Nuts'
    DAIRY = 'DAIRY', 'Dairy'
    GLUTEN = 'GLUTEN', 'Gluten'
    EGGS = 'EGGS', 'Eggs'
    SEAFOOD = 'SEAFOOD', 'Seafood'
    SOY = 'SOY', 'Soy'
    OTHER = 'OTHER', 'Other'


class NutritionalStatus(models.TextChoices):
    NORMAL = 'NORMAL', 'Normal'
    AT_RISK = 'AT_RISK', 'At Risk'
    MALNOURISHED = 'MALNOURISHED', 'Malnourished'
    OBESE = 'OBESE', 'Obese'


class DietOrder(AuditModel):
    """Physician diet order for an admitted patient."""
    admission = models.ForeignKey(
        'ipd.Admission', on_delete=models.PROTECT, related_name='diet_orders'
    )
    diet_type = models.CharField(max_length=20, choices=DietType.choices, default=DietType.REGULAR)
    diet_type_other = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=DietOrderStatus.choices, default=DietOrderStatus.ACTIVE)
    calorie_target = models.PositiveIntegerField(null=True, blank=True, help_text='kcal/day')
    protein_target = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True, help_text='g/day')
    fluid_restriction = models.PositiveIntegerField(null=True, blank=True, help_text='mL/day')
    special_instructions = models.TextField(blank=True)
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='diet_orders_issued'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='diet_orders_reviewed'
    )
    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_diet_type_display()} — {self.admission}"


class DietaryRestriction(TimeStampedModel):
    """Food allergies and intolerances recorded for an admitted patient."""
    admission = models.ForeignKey(
        'ipd.Admission', on_delete=models.CASCADE, related_name='dietary_restrictions'
    )
    category = models.CharField(max_length=20, choices=AllergyCategory.choices)
    description = models.CharField(max_length=200)
    severity = models.CharField(max_length=20, choices=[
        ('MILD', 'Mild'), ('MODERATE', 'Moderate'), ('SEVERE', 'Severe / Anaphylactic')
    ], default='MILD')
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )

    class Meta:
        ordering = ['category']

    def __str__(self):
        return f"{self.get_category_display()} — {self.description}"


class NutritionalAssessment(AuditModel):
    """Nutritionist assessment (MUST score, BMI, status)."""
    admission = models.ForeignKey(
        'ipd.Admission', on_delete=models.PROTECT, related_name='nutritional_assessments'
    )
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1)
    height_cm = models.DecimalField(max_digits=5, decimal_places=1)
    bmi = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    must_score = models.PositiveSmallIntegerField(
        help_text='Malnutrition Universal Screening Tool (0–6)'
    )
    nutritional_status = models.CharField(
        max_length=20, choices=NutritionalStatus.choices, default=NutritionalStatus.NORMAL
    )
    appetite = models.CharField(max_length=20, choices=[
        ('GOOD', 'Good'), ('FAIR', 'Fair'), ('POOR', 'Poor'), ('NONE', 'None')
    ], default='GOOD')
    feeding_route = models.CharField(max_length=20, choices=[
        ('ORAL', 'Oral'), ('NG_TUBE', 'Nasogastric Tube'), ('PEG', 'PEG Tube'), ('IV', 'Parenteral (IV)')
    ], default='ORAL')
    notes = models.TextField(blank=True)
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='nutritional_assessments_done'
    )

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.weight_kg and self.height_cm:
            h_m = float(self.height_cm) / 100
            self.bmi = round(float(self.weight_kg) / (h_m * h_m), 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Assessment — {self.admission} ({self.get_nutritional_status_display()})"


class MealPlan(AuditModel):
    """Daily meal plan generated for a patient."""
    diet_order = models.ForeignKey(DietOrder, on_delete=models.PROTECT, related_name='meal_plans')
    plan_date = models.DateField()
    total_calories = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='meal_plans_prepared'
    )
    served = models.BooleanField(default=False)
    served_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-plan_date']
        unique_together = ('diet_order', 'plan_date')

    def __str__(self):
        return f"Meal Plan {self.plan_date} — {self.diet_order.admission}"


class MealItem(TimeStampedModel):
    """Individual meal within a daily meal plan."""
    meal_plan = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name='items')
    meal_time = models.CharField(max_length=20, choices=MealTime.choices)
    description = models.CharField(max_length=300)
    calories_kcal = models.PositiveIntegerField(null=True, blank=True)
    protein_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    carbs_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    fat_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ['meal_time']

    def __str__(self):
        return f"{self.get_meal_time_display()} — {self.description}"
