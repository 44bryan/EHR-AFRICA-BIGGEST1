from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
from .models import User, UserRole
from .forms import LoginForm, UserCreateForm, UserEditForm, ProfileForm
from apps.core.middleware import AuditMiddleware


def _require_super_admin(user):
    return user.is_super_admin or user.is_admin_staff


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.totp_enabled:
                # Stash user PK in session — do NOT call login() yet
                request.session['_2fa_user_id'] = str(user.pk)
                request.session['_2fa_next'] = request.GET.get('next', '')
                return redirect('accounts:two_fa_verify')
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name}!')
            return redirect(request.GET.get('next', 'dashboard:home'))
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm(request)

    return render(request, 'accounts/login.html', {'form': form})


@csrf_exempt
def logout_view(request):
    # Accept both GET and POST; csrf_exempt because logging out is always safe
    logout(request)
    response = redirect('accounts:login')
    response['HX-Redirect'] = '/accounts/login/'
    return response


@login_required
def password_change_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            import django.utils.timezone as tz
            user.must_change_password = False
            user.last_password_change = tz.now()
            user.save(update_fields=['must_change_password', 'last_password_change'])
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully.')
            return redirect('dashboard:home')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'accounts/password_change.html', {'form': form})


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'accounts/profile.html', {'form': form})


@login_required
def user_list_view(request):
    if not (request.user.is_medical_director or request.user.is_admin_staff):
        return HttpResponseForbidden()

    users = User.objects.select_related('department').order_by('last_name', 'first_name')
    role_filter = request.GET.get('role', '')
    dept_filter = request.GET.get('department', '')

    if role_filter:
        users = users.filter(role=role_filter)
    if dept_filter:
        users = users.filter(department_id=dept_filter)

    from apps.departments.models import Department
    return render(request, 'accounts/user_list.html', {
        'users': users,
        'departments': Department.objects.filter(is_active=True),
        'roles': User.role.field.choices,
        'role_filter': role_filter,
        'dept_filter': dept_filter,
    })


@login_required
def user_create_view(request):
    if not (request.user.is_medical_director or request.user.is_admin_staff):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = UserCreateForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Staff account created successfully.')
            return redirect('accounts:staff_hub')
    else:
        initial = {}
        preset_role = request.GET.get('role')
        if preset_role:
            initial['role'] = preset_role
        form = UserCreateForm(initial=initial)

    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Create Staff Account'})


@login_required
def user_edit_view(request, pk):
    if not (request.user.is_medical_director or request.user.is_admin_staff):
        return HttpResponseForbidden()

    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Staff account updated.')
            return redirect('accounts:staff_hub')
    else:
        form = UserEditForm(instance=user)

    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Edit Staff Account', 'edit_user': user})


@login_required
def staff_hub_view(request):
    """Super Admin staff management hub — full overview + quick actions."""
    if not _require_super_admin(request.user):
        return HttpResponseForbidden()

    from apps.departments.models import Department

    search = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '')
    dept_filter = request.GET.get('department', '')
    status_filter = request.GET.get('status', '')

    users = User.objects.select_related('department').order_by('role', 'last_name')

    if search:
        from django.db.models import Q
        users = users.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(employee_id__icontains=search)
        )
    if role_filter:
        users = users.filter(role=role_filter)
    if dept_filter:
        users = users.filter(department_id=dept_filter)
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    # Role-grouped counts for the stat strip
    role_counts = User.objects.values('role').annotate(count=Count('id'))
    role_count_map = {r['role']: r['count'] for r in role_counts}

    # Group roles into categories for the quick-create panel
    role_categories = [
        {
            'label': 'Executive / Leadership',
            'icon': 'bi-award',
            'color': 'dark',
            'roles': [
                UserRole.CEO, UserRole.MEDICAL_DIRECTOR, UserRole.ADMIN_DIRECTOR,
                UserRole.FINANCE_DIRECTOR,
            ],
        },
        {
            'label': 'Doctors / Clinical',
            'icon': 'bi-stethoscope',
            'color': 'primary',
            'roles': [
                UserRole.OPHTHALMOLOGIST,
                UserRole.RETINA_SPECIALIST, UserRole.GLAUCOMA_SPECIALIST,
                UserRole.PEDIATRIC_OPHTHALMOLOGIST, UserRole.PEDIATRIC_REFRACTIONIST,
                UserRole.CATARACT_SURGEON, UserRole.CORNEA_SPECIALIST,
                UserRole.OCULOPLASTICS_SURGEON, UserRole.NEURO_OPHTHALMOLOGIST,
                UserRole.UVEITIS_SPECIALIST, UserRole.OPTOMETRIST,
                UserRole.LOW_VISION_SPECIALIST, UserRole.INTERN,
            ],
        },
        {
            'label': 'Nursing & Allied Clinical',
            'icon': 'bi-heart-pulse',
            'color': 'danger',
            'roles': [
                UserRole.NURSE, UserRole.THEATRE_NURSE,
                UserRole.WARD_NURSE, UserRole.COUNSELING_NURSE,
                UserRole.ANAESTHETIST,
            ],
        },
        {
            'label': 'Technical / Paramedical',
            'icon': 'bi-tools',
            'color': 'warning',
            'roles': [
                UserRole.INVESTIGATION_TECHNICIAN, UserRole.LAB_TECHNICIAN,
                UserRole.PHARMACIST, UserRole.OPTICAL_DISPENSER,
                UserRole.CSSD_TECHNICIAN,
            ],
        },
        {
            'label': 'Administrative',
            'icon': 'bi-building',
            'color': 'success',
            'roles': [
                UserRole.RECEPTIONIST, UserRole.ADMISSION_OFFICER,
                UserRole.BILLING_OFFICER, UserRole.CASHIER,
                UserRole.MEDICAL_RECORDS, UserRole.GATEKEEPER, UserRole.ADMIN,
            ],
        },
    ]

    # Attach display labels and counts to each role
    role_label_map = dict(UserRole.choices)
    for cat in role_categories:
        cat['role_list'] = [
            {
                'value': r,
                'label': role_label_map.get(r, r),
                'count': role_count_map.get(r, 0),
            }
            for r in cat['roles']
        ]

    return render(request, 'accounts/staff_hub.html', {
        'users': users,
        'total_staff': User.objects.filter(is_active=True).count(),
        'inactive_staff': User.objects.filter(is_active=False).count(),
        'departments': Department.objects.filter(is_active=True),
        'all_roles': UserRole.choices,
        'role_categories': role_categories,
        'search': search,
        'role_filter': role_filter,
        'dept_filter': dept_filter,
        'status_filter': status_filter,
    })


@login_required
@require_POST
def toggle_user_active_view(request, pk):
    """Super Admin: toggle a staff member's active status."""
    if not _require_super_admin(request.user):
        return HttpResponseForbidden()

    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('accounts:staff_hub')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    action = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f'{user.full_name} has been {action}.')
    return redirect('accounts:staff_hub')


@login_required
def reset_staff_password_view(request, pk):
    """Super Admin: set a new password for any staff member."""
    if not _require_super_admin(request.user):
        return HttpResponseForbidden()

    staff = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = SetPasswordForm(staff, request.POST)
        if form.is_valid():
            form.save()
            staff.must_change_password = True
            staff.save(update_fields=['must_change_password'])
            messages.success(request, f'Password reset for {staff.full_name}. They will be prompted to change it on next login.')
            return redirect('accounts:staff_hub')
    else:
        form = SetPasswordForm(staff)

    return render(request, 'accounts/reset_password.html', {'form': form, 'staff': staff})


# ── Two-Factor Authentication (TOTP) ─────────────────────────────────────────

def two_fa_verify_view(request):
    """Step 2 of login — verify TOTP code when 2FA is enabled."""
    user_id = request.session.get('_2fa_user_id')
    if not user_id:
        return redirect('accounts:login')

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return redirect('accounts:login')

    error = None
    if request.method == 'POST':
        import pyotp
        code = request.POST.get('otp_code', '').strip().replace(' ', '')
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code, valid_window=1):
            # Clear pending session keys
            request.session.pop('_2fa_user_id', None)
            next_url = request.session.pop('_2fa_next', '') or 'dashboard:home'
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name}!')
            return redirect(next_url)
        else:
            error = 'Invalid or expired code. Please try again.'

    return render(request, 'accounts/two_fa_verify.html', {
        'user_name': user.first_name,
        'error': error,
    })


@login_required
def two_fa_setup_view(request):
    """Allow a logged-in user to enable TOTP 2FA on their account."""
    import pyotp, qrcode, qrcode.image.svg
    from io import BytesIO
    import base64

    user = request.user
    error = None
    success = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'generate':
            # Generate new secret and store temporarily in session
            secret = pyotp.random_base32()
            request.session['_2fa_pending_secret'] = secret

        elif action == 'confirm':
            secret = request.session.get('_2fa_pending_secret')
            code = request.POST.get('otp_code', '').strip().replace(' ', '')
            if not secret:
                error = 'Session expired. Please start again.'
            else:
                totp = pyotp.TOTP(secret)
                if totp.verify(code, valid_window=1):
                    user.totp_secret = secret
                    user.totp_enabled = True
                    user.save(update_fields=['totp_secret', 'totp_enabled'])
                    request.session.pop('_2fa_pending_secret', None)
                    messages.success(request, 'Two-factor authentication enabled successfully.')
                    return redirect('accounts:profile')
                else:
                    error = 'Code incorrect — please scan the QR code again and retry.'

        elif action == 'disable':
            code = request.POST.get('otp_code', '').strip().replace(' ', '')
            if user.totp_enabled:
                totp = pyotp.TOTP(user.totp_secret)
                if totp.verify(code, valid_window=1):
                    user.totp_secret = ''
                    user.totp_enabled = False
                    user.save(update_fields=['totp_secret', 'totp_enabled'])
                    messages.success(request, 'Two-factor authentication disabled.')
                    return redirect('accounts:profile')
                else:
                    error = 'Incorrect code. 2FA not disabled.'

    # Build QR code for display
    secret = request.session.get('_2fa_pending_secret') or (user.totp_secret if user.totp_enabled else None)
    qr_data_url = None
    if secret:
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name='EHR Africa — Cameroon Eye Hospital',
        )
        img = qrcode.make(totp_uri)
        buf = BytesIO()
        img.save(buf, format='PNG')
        qr_data_url = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    return render(request, 'accounts/two_fa_setup.html', {
        'user': user,
        'secret': secret,
        'qr_data_url': qr_data_url,
        'pending': bool(request.session.get('_2fa_pending_secret')),
        'error': error,
    })


# ─────────────────────────────────────────────────────────────────────────────
# System Module Settings (Super Admin only)
# ─────────────────────────────────────────────────────────────────────────────

_MODULE_META = [
    # (field_name, icon, title, description, tier)
    # tier: 'core' | 'clinical' | 'operational' | 'engagement'
    ('module_ai',        'bi-robot',           'AI Assistant',
     'Groq-powered clinical AI: drug checker, diagnostic support, case summaries.',
     'clinical'),
    ('module_qms',       'bi-ticket-perforated','Queue Management System',
     'Patient token queue, TV display, department routing & waiting-time analytics.',
     'clinical'),
    ('module_pharmacy',  'bi-capsule',          'Pharmacy',
     'Dispensing, drug stock, expiry alerts and prescription fulfilment.',
     'clinical'),
    ('module_laboratory','bi-eyedropper',       'Laboratory',
     'Test requests, results entry, critical-value alerts and reporting.',
     'clinical'),
    ('module_ipd',       'bi-hospital',         'Inpatient / Surgical (IPD)',
     'Ward admissions, bed management, surgical bookings and theatre scheduling.',
     'clinical'),
    ('module_opticals',  'bi-eyeglasses',       'Optical Dispensary',
     'Frame & lens inventory, spectacle prescriptions, optical sales.',
     'clinical'),
    ('module_cssd',      'bi-shield-check',     'CSSD — Sterilisation',
     'Instrument tracking, sterilization cycle logging and dispatch management.',
     'operational'),
    ('module_inventory', 'bi-box-seam',         'Inventory & Pilferage Protection',
     'Medical supply stock, requisitions, pilferage alerts and reorder management.',
     'operational'),
    ('module_hrms',      'bi-people',           'HR Management (HRMS)',
     'Staff records, leave management, payroll and performance tracking.',
     'operational'),
    ('module_outreach',  'bi-geo-alt',          'Outreach & Community',
     'Outreach campaign planning, community screening records and field reports.',
     'engagement'),
    ('module_feedback',  'bi-star-half',        'Patient Feedback & NPS',
     'Post-visit satisfaction surveys, NPS tracking and service recovery.',
     'engagement'),
    ('module_leads',     'bi-funnel',           'Lead Management (CRM)',
     'Track prospective patients, referral sources and conversion analytics.',
     'engagement'),
]


@login_required
def system_modules_view(request):
    """Super-admin module toggle page."""
    from .models import HospitalConfig
    user = request.user
    if not user.is_super_admin:
        return HttpResponseForbidden('Super Administrator access required.')

    cfg = HospitalConfig.get()

    if request.method == 'POST':
        for field, *_ in _MODULE_META:
            setattr(cfg, field, field in request.POST)
        # Appearance settings
        from .models import SystemTheme, QueueBoardType
        theme = request.POST.get('system_theme', SystemTheme.TEAL)
        if theme in dict(SystemTheme.choices):
            cfg.system_theme = theme
        board = request.POST.get('queue_board_type', QueueBoardType.TOKEN)
        if board in dict(QueueBoardType.choices):
            cfg.queue_board_type = board
        cfg.save()
        messages.success(request, 'Settings saved successfully.')
        return redirect('accounts:system_modules')

    # Group modules by tier for display
    tiers = {}
    for field, icon, title, desc, tier in _MODULE_META:
        tiers.setdefault(tier, []).append({
            'field': field,
            'icon': icon,
            'title': title,
            'desc': desc,
            'enabled': getattr(cfg, field, True),
        })

    tier_order = [
        ('clinical',    'Clinical Modules',    'bi-heart-pulse',    'Modules used by doctors, nurses and clinical staff.'),
        ('operational', 'Operational Modules', 'bi-gear',           'Back-office and operations management.'),
        ('engagement',  'Engagement Modules',  'bi-chat-heart',     'Patient relationship, feedback and outreach.'),
    ]

    from .models import SystemTheme
    return render(request, 'accounts/system_modules.html', {
        'tiers': [(key, label, icon, desc, tiers.get(key, [])) for key, label, icon, desc in tier_order],
        'cfg': cfg,
        'theme_choices': SystemTheme.choices,
    })
