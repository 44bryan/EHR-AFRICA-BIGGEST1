#!/usr/bin/env python
"""Inspect sub-categories, service prices, and budget model on production."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ehr_project.settings.base')
django.setup()

from apps.billing.models import ServiceSubCategory, ServicePrice, Budget
from django.db.models import Count

print("=== SUB-CATEGORIES ===")
for sc in ServiceSubCategory.objects.filter(is_deleted=False).order_by('category', 'name'):
    print(f"{sc.id}|{sc.category}|{sc.name}|{sc.code or '-'}")

print("\n=== SERVICE PRICE CATEGORIES ===")
cats = (ServicePrice.objects.filter(is_deleted=False)
        .values('category').annotate(c=Count('id')).order_by('category'))
for c in cats:
    print(f"  {c['category']}: {c['c']} items")

print("\n=== SERVICE PRICES (all, grouped by category) ===")
for sp in ServicePrice.objects.filter(is_deleted=False).order_by('category', 'name'):
    print(f"{sp.category}|{sp.name}|sub={sp.sub_category_id or 'NONE'}")

print("\n=== BUDGET MODEL FIELDS ===")
for f in Budget._meta.get_fields():
    fname = f.name
    ftype = type(f).__name__
    choices = ''
    if hasattr(f, 'choices') and f.choices:
        choices = str(f.choices)
    print(f"  {fname}: {ftype} {choices}")
