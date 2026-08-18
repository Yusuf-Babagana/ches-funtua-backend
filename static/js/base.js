/* Base site JS — no framework, small progressive-enhancement helpers only.
 * Business-critical validation/authorization stays server-side; this file
 * only handles UI affordances (mobile sidebar, toast auto-dismiss, confirm
 * prompts on destructive actions). */
(function () {
    'use strict';

    // Auto-dismiss toasts after 5s.
    document.querySelectorAll('.toast').forEach(function (toast) {
        setTimeout(function () {
            toast.style.transition = 'opacity .2s ease';
            toast.style.opacity = '0';
            setTimeout(function () { toast.remove(); }, 200);
        }, 5000);
    });

    // Mobile dashboard sidebar toggle. Markup: a button[data-sidebar-toggle],
    // the sidebar itself (#dash-sidebar) and an overlay (#dash-overlay).
    var toggleBtn = document.querySelector('[data-sidebar-toggle]');
    var sidebar = document.getElementById('dash-sidebar');
    var overlay = document.getElementById('dash-overlay');

    function openSidebar() {
        if (sidebar) sidebar.classList.add('is-open');
        if (overlay) overlay.classList.add('is-open');
    }
    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('is-open');
        if (overlay) overlay.classList.remove('is-open');
    }
    if (toggleBtn) toggleBtn.addEventListener('click', openSidebar);
    if (overlay) overlay.addEventListener('click', closeSidebar);

    // Generic "confirm before submitting" for destructive forms/buttons:
    // <button data-confirm="Drop this course?">...
    document.addEventListener('click', function (e) {
        var el = e.target.closest('[data-confirm]');
        if (el && !window.confirm(el.getAttribute('data-confirm'))) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, true);
})();
