/* Declarative behaviors wired by data-attributes, so no inline on*= handlers
   are needed (Content-Security-Policy forbids them). Delegated on document,
   so HTMX-swapped and fetch-injected content is covered too. */
(function () {
  // Confirm before submitting a form: <form data-confirm="Are you sure?">
  document.addEventListener('submit', function (e) {
    const msg = e.target.getAttribute && e.target.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) {
      e.preventDefault();
    }
  });

  document.addEventListener('change', function (e) {
    // Auto-submit the enclosing form: <select data-autosubmit>
    if (e.target.matches('[data-autosubmit]') && e.target.form) {
      e.target.form.submit();
    }
  });

  document.addEventListener('click', function (e) {
    // Select all text in a field: <input data-select-all>
    const selectAll = e.target.closest('[data-select-all]');
    if (selectAll) {
      selectAll.select();
      return;
    }
    // Remove the nearest matching ancestor: <button data-remove-closest=".row">
    const remover = e.target.closest('[data-remove-closest]');
    if (remover) {
      const target = remover.closest(remover.getAttribute('data-remove-closest'));
      if (target) target.remove();
    }
  });
})();
