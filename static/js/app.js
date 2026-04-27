/* ============================================================
   StuffApp — Client-side JavaScript
   ============================================================ */

'use strict';


// ---------------------------------------------------------------------------
// iOS 18 Apple Intelligence: suppress the "Writing Tools" popover
// (Proofread / Rewrite / Summarize) that appears whenever text is
// selected in an editable field. The writingsuggestions="false"
// attribute opts that field out of the AI menu without affecting
// keyboard, autocorrect, or normal selection. Apply it to every
// input/textarea once on page load and again whenever new editable
// elements show up (e.g. modal openers).
// ---------------------------------------------------------------------------
function suppressWritingSuggestions(root) {
  (root || document)
    .querySelectorAll('input, textarea, [contenteditable]')
    .forEach(el => el.setAttribute('writingsuggestions', 'false'));
}
document.addEventListener('DOMContentLoaded', () => suppressWritingSuggestions());
// Catch dynamically-inserted inputs (lookup review modal, autosave
// row inserts, etc.) the same way without rebinding individual code
// paths.
new MutationObserver(records => {
  for (const rec of records) {
    rec.addedNodes.forEach(n => {
      if (n.nodeType !== 1) return;
      if (n.matches && n.matches('input, textarea, [contenteditable]')) {
        n.setAttribute('writingsuggestions', 'false');
      }
      if (n.querySelectorAll) suppressWritingSuggestions(n);
    });
  }
}).observe(document.documentElement, { childList: true, subtree: true });


// ---------------------------------------------------------------------------
// File upload preview
// ---------------------------------------------------------------------------

/**
 * Called when a file input changes.
 * Shows an image preview if the selected file is an image.
 */
function handleFileChange(input) {
  const previewId = input.dataset.preview;
  if (!previewId) return;
  const preview = document.getElementById(previewId);
  if (!preview) return;

  const file = input.files && input.files[0];
  if (!file) return;

  if (file.type.startsWith('image/')) {
    const reader = new FileReader();
    reader.onload = function (e) {
      preview.src = e.target.result;
      preview.classList.remove('file-thumb-hidden');
      preview.style.display = 'block';
    };
    reader.readAsDataURL(file);

    // Update adjacent label button text
    const label = input.closest('label');
    if (label) {
      // Keep file input, update text node
      const textNode = [...label.childNodes].find(n => n.nodeType === 3);
      if (textNode) textNode.textContent = 'Replace ';
    }
  } else {
    // Non-image (PDF etc.) — just indicate file is selected
    preview.classList.add('file-thumb-hidden');
    // Show a small doc indicator if possible
    const group = input.closest('.file-group');
    if (group) {
      let indicator = group.querySelector('.new-file-indicator');
      if (!indicator) {
        indicator = document.createElement('span');
        indicator.className = 'new-file-indicator';
        indicator.style.cssText = 'font-size:.8rem;color:#30d158;font-weight:600;';
        input.closest('label').insertAdjacentElement('afterend', indicator);
      }
      indicator.textContent = `✓ ${file.name}`;
    }
  }
}

// ---------------------------------------------------------------------------
// Auto-save indication (dirty tracking)
// ---------------------------------------------------------------------------

let formDirty = false;

function setupDirtyTracking() {
  const form = document.getElementById('detailForm');
  if (!form) return;

  const saveBtn = document.getElementById('saveBtn');

  const markDirty = () => {
    if (formDirty) return;
    formDirty = true;
    if (saveBtn) {
      saveBtn.textContent = 'Save *';
      saveBtn.style.background = '#ff9f0a';
    }
  };

  form.querySelectorAll('input, textarea, select').forEach(el => {
    if (el.type === 'file') {
      el.addEventListener('change', markDirty);
    } else {
      el.addEventListener('input', markDirty);
      el.addEventListener('change', markDirty);
    }
  });

  form.addEventListener('submit', () => {
    formDirty = false;
    if (saveBtn) {
      saveBtn.textContent = 'Saving…';
      saveBtn.disabled = true;
    }
  });
}

// ---------------------------------------------------------------------------
// Warn on unload if dirty
// ---------------------------------------------------------------------------

function setupBeforeUnload() {
  window.addEventListener('beforeunload', (e) => {
    if (formDirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}

// ---------------------------------------------------------------------------
// Search input: clear on Escape
// ---------------------------------------------------------------------------

function setupSearch() {
  const input = document.getElementById('searchInput');
  if (!input) return;
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      input.value = '';
      input.form && input.form.submit();
    }
  });
}

// ---------------------------------------------------------------------------
// Flash auto-dismiss
// ---------------------------------------------------------------------------

function setupFlashAutoDismiss() {
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach(flash => {
    setTimeout(() => {
      flash.style.transition = 'opacity .4s ease';
      flash.style.opacity = '0';
      setTimeout(() => flash.remove(), 400);
    }, 3500);
  });
}

// ---------------------------------------------------------------------------
// Keyboard shortcuts
// ---------------------------------------------------------------------------

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Cmd/Ctrl + S → save form
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      const form = document.getElementById('detailForm');
      if (form) {
        e.preventDefault();
        form.requestSubmit();
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Complication checkbox visual feedback (already handled by CSS :has())
// Provide fallback for older browsers
// ---------------------------------------------------------------------------

function setupComplicationFallback() {
  const checks = document.querySelectorAll('.complication-check');
  if (!CSS.supports('selector(:has(input:checked))')) {
    checks.forEach(label => {
      const input = label.querySelector('input[type=checkbox]');
      if (!input) return;
      const update = () => {
        if (input.checked) {
          label.classList.add('checked');
        } else {
          label.classList.remove('checked');
        }
      };
      input.addEventListener('change', update);
      update();
    });
    // Add fallback CSS
    const style = document.createElement('style');
    style.textContent = `.complication-check.checked { background: var(--blue, #0a84ff); border-color: var(--blue, #0a84ff); color: #fff; }`;
    document.head.appendChild(style);
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  setupDirtyTracking();
  setupBeforeUnload();
  setupSearch();
  setupFlashAutoDismiss();
  setupKeyboardShortcuts();
  setupComplicationFallback();
});
