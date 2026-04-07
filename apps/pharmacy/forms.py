from django import forms
from .models import Drug, DrugStock, Dispensing, DispensingItem, DrugCategory, DrugForm


class DrugCreateForm(forms.ModelForm):
    class Meta:
        model = Drug
        fields = [
            'name', 'generic_name', 'brand_name', 'category', 'form',
            'strength', 'unit', 'barcode', 'description',
            'is_active', 'requires_prescription',
            'reorder_level', 'cost_price', 'selling_price',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'generic_name': forms.TextInput(attrs={'class': 'form-control'}),
            'brand_name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'form': forms.Select(attrs={'class': 'form-select'}),
            'strength': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0.5%, 5mg'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. bottle, tube, tablet'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
        }


class AddStockForm(forms.ModelForm):
    class Meta:
        model = DrugStock
        fields = ['batch_number', 'expiry_date', 'quantity_received', 'supplier', 'purchase_price', 'notes']
        widgets = {
            'batch_number': forms.TextInput(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'quantity_received': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'supplier': forms.TextInput(attrs={'class': 'form-control'}),
            'purchase_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def save(self, commit=True, drug=None, user=None):
        instance = super().save(commit=False)
        if drug:
            instance.drug = drug
        instance.quantity_remaining = instance.quantity_received
        if user:
            instance.created_by = user
        if commit:
            instance.save()
        return instance


class DispensingItemForm(forms.Form):
    """Form to add a single drug item to an open dispensing record."""
    drug = forms.ModelChoiceField(
        queryset=Drug.objects.filter(is_active=True, is_deleted=False).order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_drug'}),
        empty_label='— Select Drug —',
    )
    stock_batch = forms.ModelChoiceField(
        queryset=DrugStock.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_stock_batch'}),
        required=False,
        empty_label='— Auto (FEFO) —',
        help_text='Leave blank to use the nearest-expiry batch automatically.',
    )
    quantity_dispensed = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
    )
    unit_price = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        help_text='Defaults to drug selling price.',
    )
    instructions = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1 drop OD twice daily x 7 days'}),
    )

    def __init__(self, *args, drug_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.utils import timezone
        if drug_id:
            self.fields['stock_batch'].queryset = DrugStock.objects.filter(
                drug_id=drug_id,
                is_deleted=False,
                quantity_remaining__gt=0,
                expiry_date__gte=timezone.localdate(),
            ).order_by('expiry_date')

    def clean(self):
        cleaned = super().clean()
        drug = cleaned.get('drug')
        qty = cleaned.get('quantity_dispensed')
        batch = cleaned.get('stock_batch')
        from django.utils import timezone

        if drug and qty:
            if batch:
                if batch.quantity_remaining < qty:
                    raise forms.ValidationError(
                        f'Only {batch.quantity_remaining} units available in this batch.'
                    )
            else:
                from django.db.models import Sum as DSum
                total = DrugStock.objects.filter(
                    drug=drug, is_deleted=False, quantity_remaining__gt=0,
                    expiry_date__gte=timezone.localdate()
                ).aggregate(t=DSum('quantity_remaining'))['t'] or 0
                if total < qty:
                    raise forms.ValidationError(
                        f'Insufficient stock. Only {total} units available for {drug.name}.'
                    )
        return cleaned
