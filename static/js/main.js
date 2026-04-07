/* ============================================================
   EHR Africa — Main JavaScript v2
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  /* ── Sidebar Toggle ───────────────────────────────────────── */
  const toggleBtn  = document.getElementById('sidebarToggle');
  const sidebar    = document.getElementById('sidebar');
  const backdrop   = document.getElementById('sidebar-backdrop');
  const COLLAPSED_KEY = 'ehr_sidebar_collapsed';

  // Restore collapsed state on desktop
  if (window.innerWidth > 768 && localStorage.getItem(COLLAPSED_KEY) === '1') {
    sidebar.classList.add('collapsed');
    syncTooltips(true);
  }

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', function () {
      if (window.innerWidth <= 768) {
        // Mobile: slide in/out with backdrop
        const isOpen = sidebar.classList.toggle('mobile-open');
        if (backdrop) backdrop.classList.toggle('show', isOpen);
      } else {
        // Desktop: icon-only collapse
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
  function setActiveSidebarLink() {
    const path = window.location.pathname;
    const links = Array.from(document.querySelectorAll('#sidebar .sidebar-link[href]'));

    // Clear all active states first
    links.forEach(l => l.classList.remove('active'));

    // Skip logout and external links
    const candidates = links.filter(link => {
      const href = link.getAttribute('href');
      if (!href || href === '#' || href.startsWith('http')) return false;
      if (href.includes('logout') || href === '/admin/') return false;
      if (href === '/') return path === '/';
      return path === href || path.startsWith(href + '/') || path.startsWith(href);
    });

    if (!candidates.length) return;

    // Pick the most specific match (longest href)
    const maxLen = Math.max(...candidates.map(l => l.getAttribute('href').length));
    candidates
      .filter(l => l.getAttribute('href').length === maxLen)
      .forEach(l => l.classList.add('active'));
  }

  setActiveSidebarLink();


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

});
