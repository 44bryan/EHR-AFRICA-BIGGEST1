/* ============================================================
   EHR Africa — Main JavaScript v2
   ============================================================ */

// ── Bootstrap / sidebar initializer ─────────────────────────────────────────
// Called on fresh DOMContentLoaded AND after every HTMX page swap.
function ehrInit() {

  /* ── Sidebar Toggle ───────────────────────────────────────── */
  const toggleBtn  = document.getElementById('sidebarToggle');
  const sidebar    = document.getElementById('sidebar');
  const backdrop   = document.getElementById('sidebar-backdrop');
  const COLLAPSED_KEY = 'ehr_sidebar_collapsed';

  const isPhone  = () => window.innerWidth <= 768;
  const isTablet = () => window.innerWidth > 768 && window.innerWidth <= 1024;
  const TABLET_EXPANDED_KEY = 'ehr_tablet_expanded';

  // Desktop (>1024px): default to collapsed unless user explicitly expanded it
  if (window.innerWidth > 1024) {
    const desktopPref = localStorage.getItem(COLLAPSED_KEY);
    if (desktopPref !== '0') {  // '0' = user explicitly expanded; anything else = collapsed
      sidebar.classList.add('collapsed');
      syncTooltips(true);
    }
  }
  // Tablets: start collapsed unless user explicitly expanded
  if (isTablet()) {
    if (localStorage.getItem(TABLET_EXPANDED_KEY) === '1') {
      sidebar.classList.add('tablet-expanded');
    }
    // tablets use icon-only by default (CSS handles it via :not(.tablet-expanded))
  }

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', function () {
      if (isPhone()) {
        // Phone: slide in/out full sidebar with backdrop overlay
        const isOpen = sidebar.classList.toggle('mobile-open');
        if (backdrop) backdrop.classList.toggle('show', isOpen);
      } else if (isTablet()) {
        // Tablet: toggle between icon-only and full sidebar
        const isExpanded = sidebar.classList.toggle('tablet-expanded');
        localStorage.setItem(TABLET_EXPANDED_KEY, isExpanded ? '1' : '0');
        syncTooltips(!isExpanded);
      } else {
        // Desktop: toggle icon-only / full sidebar; persist preference
        const isCollapsed = sidebar.classList.toggle('collapsed');
        localStorage.setItem(COLLAPSED_KEY, isCollapsed ? '1' : '0');
        syncTooltips(isCollapsed);
      }
    });
  }

  // Close mobile sidebar on backdrop click
  if (backdrop) {
    backdrop.addEventListener('click', function () {
      sidebar.classList.remove('mobile-open');
      backdrop.classList.remove('show');
    });
  }

  function syncTooltips(collapsed) {
    // When collapsed: enable tooltips; when expanded: disable them
    document.querySelectorAll('#sidebar [data-bs-toggle="tooltip"]').forEach(el => {
      const tip = bootstrap.Tooltip.getInstance(el);
      if (collapsed) {
        if (!tip) new bootstrap.Tooltip(el, { trigger: 'hover' });
      } else {
        if (tip) tip.dispose();
      }
    });
  }

  // Init tooltips based on current state
  const isCollapsedNow = sidebar && sidebar.classList.contains('collapsed');
  syncTooltips(isCollapsedNow);


  /* ── Sidebar Active Link ──────────────────────────────────── */
  // setActiveSidebarLink() is NOT called here — it runs via its own
  // DOMContentLoaded listener (initial load) and htmx:afterSettle (navigation).
  // Calling it here on htmx:afterSwap would consume _pendingSidebarActivation
  // before htmx:afterSettle gets to honour the clicked link.


  /* ── Global Patient Search ────────────────────────────────── */
  const searchInput   = document.getElementById('globalPatientSearch');
  const searchResults = document.getElementById('patientSearchResults');

  if (searchInput && searchResults) {
    let searchTimer;

    searchInput.addEventListener('input', function () {
      clearTimeout(searchTimer);
      const q = this.value.trim();
      if (q.length < 2) { searchResults.style.display = 'none'; return; }

      searchTimer = setTimeout(() => {
        fetch(`/api/patients/search/?q=${encodeURIComponent(q)}`)
          .then(r => r.json())
          .then(data => {
            if (data.results && data.results.length > 0) {
              searchResults.innerHTML = data.results.map(p => `
                <a href="${p.url}" class="dropdown-item py-2 px-3" style="border-radius:6px;">
                  <div class="fw-semibold" style="font-size:0.825rem;">${p.name}</div>
                  <div class="text-muted" style="font-size:0.72rem;">
                    ${p.patient_id} &middot; ${p.age}yr &middot; ${p.gender}
                    ${p.phone ? '&middot; ' + p.phone : ''}
                  </div>
                </a>
              `).join('');
              searchResults.style.display = 'block';
            } else {
              searchResults.innerHTML = '<div class="dropdown-item text-muted py-2 px-3" style="font-size:0.8rem;">No patients found</div>';
              searchResults.style.display = 'block';
            }
          })
          .catch(() => { searchResults.style.display = 'none'; });
      }, 280);
    });

    document.addEventListener('click', function (e) {
      if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.style.display = 'none';
      }
    });
  }


  /* ── Auto-dismiss alerts ──────────────────────────────────── */
  document.querySelectorAll('.alert.alert-dismissible').forEach(alert => {
    setTimeout(() => {
      try { bootstrap.Alert.getOrCreateInstance(alert).close(); } catch(e) {}
    }, 5000);
  });


  /* ── Confirm Modal ────────────────────────────────────────── */
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', function (e) {
      e.preventDefault();
      const modal = document.getElementById('confirmModal');
      if (!modal) return;
      document.getElementById('confirmModalBody').textContent  = this.dataset.confirm;
      document.getElementById('confirmModalForm').action = this.dataset.confirmAction || this.href;
      new bootstrap.Modal(modal).show();
    });
  });


  /* ── Global Tooltips (non-sidebar) ───────────────────────── */
  document.querySelectorAll('[data-bs-toggle="tooltip"]:not(#sidebar *)').forEach(el => {
    new bootstrap.Tooltip(el);
  });


  /* ── Form validation ──────────────────────────────────────── */
  document.querySelectorAll('.needs-validation').forEach(form => {
    form.addEventListener('submit', function (e) {
      if (!form.checkValidity()) { e.preventDefault(); e.stopPropagation(); }
      form.classList.add('was-validated');
    });
  });


  /* ── Clickable table rows (data-href) ────────────────────── */
  document.querySelectorAll('tr[data-href], .table-row-link[data-href]').forEach(function(row) {
    row.style.cursor = 'pointer';
    row.addEventListener('click', function(e) {
      // Don't navigate if the click was on a link, button, or interactive element inside the row
      if (e.target.closest('a, button, input, select, textarea, [onclick]')) return;
      var href = row.getAttribute('data-href');
      if (href) window.location.href = href;
    });
  });


  /* ── Print button ─────────────────────────────────────────── */
  document.querySelectorAll('[data-action="print"]').forEach(btn => {
    btn.addEventListener('click', () => window.print());
  });


  /* ── Close dropdowns on outside click ────────────────────── */
  document.addEventListener('click', function (e) {
    document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
      if (!menu.closest('.dropdown').contains(e.target)) {
        menu.classList.remove('show');
      }
    });
  });

} // end ehrInit


/* ═══════════════════════════════════════════════════════════════
   SIDEBAR ACTIVE LINK — module level (registered ONCE, not per swap)
   ═══════════════════════════════════════════════════════════════ */

let _sidebarClickedLink = null;
// Set to true when a sidebar link triggered the current navigation.
// Stays true until htmx:afterSettle consumes it — this means the clicked
// link stays active even when the server does a 302 redirect (e.g.
// Dashboard → /dashboard/home/ → /billing/dashboard/).
let _pendingSidebarActivation = false;

function setActiveSidebarLink() {
  // Template hint: <span id="sidebar-active-url" data-url="/path/"></span>
  // When present it overrides everything (developer forces a specific active link).
  const hintEl = document.getElementById('sidebar-active-url');
  const hintPath = (hintEl && hintEl.dataset.url) || null;
  const path = hintPath || window.location.pathname;

  const links = Array.from(document.querySelectorAll('#sidebar .sidebar-link[href]'));
  links.forEach(l => l.classList.remove('active'));

  // ① Sidebar-click wins — honour the element the user actually clicked,
  //    regardless of where the server ultimately redirected.
  //    Skipped when a template hint is present (hint takes absolute priority).
  if (!hintPath && _pendingSidebarActivation && _sidebarClickedLink && document.body.contains(_sidebarClickedLink)) {
    _sidebarClickedLink.classList.add('active');
    _scrollSidebarToLink(_sidebarClickedLink);
    _pendingSidebarActivation = false;  // consumed — next navigation uses URL detection
    return;
  }
  _pendingSidebarActivation = false;

  // ② URL-based fallback: fresh loads, back/forward, page-content navigation,
  //    and template hint overrides.
  const candidates = links.filter(link => {
    const href = link.getAttribute('href');
    if (!href || href === '#' || href.startsWith('http')) return false;
    if (href.includes('logout') || href === '/admin/') return false;
    if (href === '/') return path === '/';
    // Normalise trailing slash before prefix-matching so /billing/pos/patient/123/
    // correctly matches the /billing/pos/ sidebar link.
    const base = href.replace(/\/$/, '');
    return path === href || path === base || path.startsWith(base + '/');
  });
  if (!candidates.length) return;

  // Most-specific match wins (longest href).
  // Only highlight the FIRST occurrence — duplicate sidebar links (e.g. "My Counter"
  // appears 3 times for super-admin) should not all light up at once.
  const maxLen = Math.max(...candidates.map(l => l.getAttribute('href').length));
  const best = candidates.filter(l => l.getAttribute('href').length === maxLen);
  best[0].classList.add('active');
  _scrollSidebarToLink(best[0]);
}

function _scrollSidebarToLink(link) {
  const body = document.getElementById('sidebarBody');
  if (!body || !link) return;
  const top = link.offsetTop, h = link.offsetHeight;
  if (top < body.scrollTop || top + h > body.scrollTop + body.clientHeight) {
    body.scrollTop = top - body.clientHeight / 2 + h / 2;
  }
}

// Capture sidebar clicks before HTMX intercepts the link.
document.addEventListener('click', function (e) {
  const link = e.target.closest('#sidebar .sidebar-link[href]');
  if (link) {
    _sidebarClickedLink = link;
    _pendingSidebarActivation = true;
    // Immediate visual feedback — no waiting for HTMX settle.
    document.querySelectorAll('#sidebar .sidebar-link').forEach(l => l.classList.remove('active'));
    link.classList.add('active');
  }
}, true);

// htmx:afterSettle is the single authoritative hook.
// We deliberately do NOT listen to htmx:pushedIntoHistory because that fires
// before the DOM has settled and can consume _pendingSidebarActivation too early,
// leaving afterSettle with nothing to work with.
document.addEventListener('htmx:afterSettle', function() {
  setActiveSidebarLink();
  buildBreadcrumbs();
});

// ── Single quick-add helper (append one option to text input) ────────────────
function appendComboSel(sel, inputId) {
  var val = sel.value;
  sel.value = '';
  if (!val) return;
  var inp = document.getElementById(inputId);
  if (!inp) return;
  var cur = inp.value.trim();
  inp.value = cur ? cur + ', ' + val : val;
}

// ── Multi-select quick-add helper ────────────────────────────────────────────
// Used by consultation forms. <select multiple> lets the user Ctrl+Click to
// pick several options at once; clicking "Add" appends them all, comma-separated.
function addMultiSel(selEl, inputId) {
  if (typeof selEl === 'string') selEl = document.getElementById(selEl);
  var inp = document.getElementById(inputId);
  if (!selEl || !inp) return;
  var vals = Array.from(selEl.selectedOptions)
                  .map(function(o) { return o.value; })
                  .filter(function(v) { return v; });
  if (!vals.length) return;
  var cur = inp.value.trim();
  inp.value = cur ? cur + ', ' + vals.join(', ') : vals.join(', ');
  selEl.selectedIndex = -1;
  inp.focus();
}

// Back / forward: clear click tracking and re-detect purely from URL.
window.addEventListener('popstate', function () {
  _sidebarClickedLink = null;
  _pendingSidebarActivation = false;
  setActiveSidebarLink();
  buildBreadcrumbs();
});


/* ═══════════════════════════════════════════════════════════════
   AUTO BREADCRUMB — builds from URL + active sidebar link.
   Runs on every page load and every HTMX navigation.
   ═══════════════════════════════════════════════════════════════ */
function buildBreadcrumbs() {
  const container = document.getElementById('ehr-breadcrumb');
  if (!container) return;

  const path = window.location.pathname;
  const parts = path.split('/').filter(Boolean);
  if (!parts.length) { container.innerHTML = ''; return; }

  // Section labels — first URL segment → human-readable name
  const SECTIONS = {
    'patients':       'Patients',
    'consultations':  'Consultations',
    'investigations': 'Investigations',
    'laboratory':     'Laboratory',
    'pharmacy':       'Pharmacy',
    'billing':        'Billing & Finance',
    'appointments':   'Appointments',
    'opticals':       'Optical Shop',
    'ipd':            'In-Patient (IPD)',
    'cssd':           'CSSD',
    'hrms':           'HR & Staff',
    'qms':            'Queue',
    'reports':        'Reports',
    'accounts':       'Staff',
    'departments':    'Departments',
    'leadership':     'Management',
    'ai-assistant':   'AI Assistant',
    'prescriptions':  'Prescriptions',
    'inventory':      'Inventory',
    'reception':      'Reception',
    'feedback':       'Feedback',
  };

  // Sub-path labels — used when sidebar label is not specific enough
  const SUB_LABELS = {
    'workstation':        'Workstation',
    'register':           'Register Patient',
    'prereg':             'Pre-Registration',
    'triage':             'Triage',
    'list':               'All Records',
    'create':             'New',
    'invoice':            'Invoices',
    'pos':                'Point of Sale',
    'reconciliation':     'Reconciliation',
    'shift':              'Shifts',
    'patient-accounts':   'Patient Financial Records',
    'orders':             'Orders',
    'payroll':            'Payroll',
    'ward':               'Wards',
    'theatre':            'Theatre Board',
    'ar-aging':           'AR Aging',
    'shift-list':         'All Shifts',
    'daily':              'Daily Summary',
    'staff-hub':          'Staff Hub',
    'analytics':          'Analytics',
    'finance-dashboard':  'Finance Overview',
  };

  const section = parts[0];
  const sectionLabel = SECTIONS[section];
  if (!sectionLabel) { container.innerHTML = ''; return; }

  // Get the active sidebar link's text as the most specific label
  const activeLink = document.querySelector('#sidebar .sidebar-link.active');
  const activeLabel = activeLink ? (activeLink.querySelector('span') || activeLink).textContent.trim() : null;

  const crumbs = [];
  crumbs.push({ label: 'Home', url: '/' });

  if (parts.length === 1) {
    // Root of a section — just section name (no link needed)
    crumbs.push({ label: sectionLabel });
  } else {
    // Multi-level — section links back, current page is terminal
    crumbs.push({ label: sectionLabel, url: '/' + section + '/' });

    // Current page label: prefer active sidebar link, then sub-label map, then prettify slug
    let pageLabel = null;
    if (activeLabel && activeLabel !== sectionLabel) {
      pageLabel = activeLabel;
    } else {
      const lastPart = parts[parts.length - 1];
      pageLabel = SUB_LABELS[lastPart]
        || (isNaN(lastPart)
            ? lastPart.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            : 'Detail');
    }
    crumbs.push({ label: pageLabel });
  }

  const html = '<nav aria-label="breadcrumb" class="ehr-breadcrumb-nav mb-2">'
    + '<ol class="breadcrumb mb-0">'
    + crumbs.map((c, i) => {
        if (i === crumbs.length - 1) {
          return '<li class="breadcrumb-item active" aria-current="page">' + c.label + '</li>';
        }
        return '<li class="breadcrumb-item"><a href="' + c.url + '">' + c.label + '</a></li>';
      }).join('')
    + '</ol></nav>';

  container.innerHTML = html;
}

// Run on normal page load
document.addEventListener('DOMContentLoaded', function() {
  ehrInit();
  setActiveSidebarLink();  // initial active state on fresh/hard loads
  buildBreadcrumbs();
});

// Re-run ehrInit after every HTMX swap (re-inits tooltips, modals, etc.)
document.addEventListener('htmx:afterSwap', function() {
  ehrInit();
});

// Show a subtle loading indicator on HTMX navigation start
document.addEventListener('htmx:beforeRequest', function() {
  document.body.style.cursor = 'wait';
});
document.addEventListener('htmx:afterOnLoad', function() {
  document.body.style.cursor = '';
});

// ── Close Bootstrap dropdowns/modals before HTMX swaps ───────────────────────
// Prevents the UI from appearing frozen on tablets when navigating via HTMX
// while a dropdown or modal is open (Bootstrap doesn't auto-close them).
document.addEventListener('htmx:beforeSwap', function() {
  // Close open dropdowns
  document.querySelectorAll('.dropdown-menu.show').forEach(function(el) {
    el.classList.remove('show');
  });
  document.querySelectorAll('[data-bs-toggle="dropdown"][aria-expanded="true"]').forEach(function(el) {
    el.setAttribute('aria-expanded', 'false');
    el.classList.remove('show');
  });
  // Hide open modals
  document.querySelectorAll('.modal.show').forEach(function(el) {
    try {
      var m = bootstrap.Modal.getInstance(el);
      if (m) m.hide();
    } catch(e) {}
  });
  // Remove modal backdrop if stuck
  document.querySelectorAll('.modal-backdrop').forEach(function(el) {
    el.remove();
  });
  document.body.classList.remove('modal-open');
  document.body.style.overflow = '';
  document.body.style.paddingRight = '';
});

// ── Real-time Notification Toast Poller ──────────────────────────────────────
// Polls /notifications/poll/ every 30s. When a new unread notification arrives,
// shows a floating toast in the top-right corner with the title and a link.
// Also keeps the bell badge in the topbar accurate.
(function () {
  let _lastCount = parseInt(
    document.querySelector('#notif-bell-badge')?.textContent || '0', 10
  );
  let _seenIds = new Set();

  // Create toast container once
  const _toastContainer = document.createElement('div');
  _toastContainer.style.cssText = [
    'position:fixed', 'top:70px', 'right:16px', 'z-index:9999',
    'display:flex', 'flex-direction:column', 'gap:8px', 'max-width:340px',
  ].join(';');
  document.body.appendChild(_toastContainer);

  function _showToast(notif) {
    const isUrgent = notif.priority === 'URGENT' || notif.priority === 'HIGH';
    const toast = document.createElement('div');
    toast.className = 'shadow-lg rounded-3 p-3 bg-white border';
    toast.style.cssText = 'border-left:4px solid ' + (isUrgent ? '#ef4444' : '#0891b2') + ' !important;animation:slideInRight .25s ease;';
    toast.innerHTML = `
      <div class="d-flex justify-content-between align-items-start gap-2">
        <div class="flex-grow-1">
          <div class="fw-semibold" style="font-size:.825rem;color:#0f172a;">
            <i class="bi ${isUrgent ? 'bi-exclamation-circle-fill text-danger' : 'bi-bell-fill text-primary'} me-1"></i>
            ${notif.title}
          </div>
          ${notif.message ? `<div class="text-muted mt-1" style="font-size:.75rem;">${notif.message}</div>` : ''}
        </div>
        <button type="button" onclick="this.closest('[data-ehr-toast]').remove()"
                style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:1rem;line-height:1;padding:0;">&#215;</button>
      </div>
      ${notif.link ? `<a href="${notif.link}" class="btn btn-sm btn-outline-primary mt-2 py-0" style="font-size:.72rem;">View</a>` : ''}
    `;
    toast.setAttribute('data-ehr-toast', '1');
    _toastContainer.appendChild(toast);
    // Auto-dismiss after 8s
    setTimeout(() => toast.remove(), 8000);
  }

  function _updateBell(count) {
    let badge = document.querySelector('#notif-bell-badge');
    if (count > 0) {
      if (!badge) {
        const bell = document.querySelector('a[href*="notifications"]');
        if (bell) {
          badge = document.createElement('span');
          badge.id = 'notif-bell-badge';
          badge.className = 'position-absolute top-0 end-0 translate-middle-y badge rounded-pill';
          badge.style.cssText = 'background:#ef4444;font-size:.58rem;min-width:17px;height:17px;line-height:17px;padding:0 4px;transform:translate(30%,-30%)!important;';
          bell.style.position = 'relative';
          bell.appendChild(badge);
        }
      }
      if (badge) badge.textContent = count > 99 ? '99+' : count;
    } else if (badge) {
      badge.remove();
    }
  }

  function _poll() {
    fetch('/notifications/poll/', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null)
      .catch(() => null)
      .then(data => {
        if (!data) return;
        _updateBell(data.count);
        // Show toast if a new (unseen) notification arrived
        if (data.latest && !_seenIds.has(data.latest.id)) {
          if (data.count > _lastCount || _lastCount === 0) {
            _showToast(data.latest);
          }
          _seenIds.add(data.latest.id);
        }
        _lastCount = data.count;
      });
  }

  // Add slide-in animation CSS
  const style = document.createElement('style');
  style.textContent = '@keyframes slideInRight{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:translateX(0)}}';
  document.head.appendChild(style);

  // First poll after 10s, then every 30s
  setTimeout(() => { _poll(); setInterval(_poll, 30000); }, 10000);
})();
