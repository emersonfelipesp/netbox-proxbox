/**
 * export-secrets-modal.js
 *
 * Handles the "Export with secrets" modal:
 *  - v1/v2 token version toggle (show/hide sections, toggle required attributes)
 *  - Populates the v1 token dropdown from the NetBox Token API
 *  - Quick-add token: creates a v1 token via the plugin endpoint and fills the dropdown
 *  - Copy-to-clipboard for the newly created token plaintext
 *  - Client-side validation before form submit
 */

const MODAL_ID = 'proxmox-export-secrets-modal';
const TOKEN_API_URL = '/api/users/tokens/?version=1&enabled=true&limit=0';

const modal = document.getElementById(MODAL_ID);
if (modal) {
  const form = modal.querySelector('#export-secrets-form');
  const v1Radio = modal.querySelector('#token_version_v1');
  const v2Radio = modal.querySelector('#token_version_v2');
  const v1Section = modal.querySelector('#v1-token-section');
  const v2Section = modal.querySelector('#v2-token-section');
  const tokenSelect = modal.querySelector('#id_token_id');
  const quickAddBtn = modal.querySelector('#btn-quick-add-token');
  const quickAddWarning = modal.querySelector('#quick-add-warning');
  const quickAddPlaintext = modal.querySelector('#id_quick_add_plaintext');
  const copyBtn = modal.querySelector('#btn-copy-token');
  const tokenKeyInput = modal.querySelector('#id_token_key');
  const tokenSecretInput = modal.querySelector('#id_token_secret');

  // ── Version toggle ────────────────────────────────────────────────────────

  function showV1() {
    v1Section.classList.remove('d-none');
    v2Section.classList.add('d-none');
    if (tokenSelect) tokenSelect.required = true;
    if (tokenKeyInput) { tokenKeyInput.required = false; tokenKeyInput.value = ''; }
    if (tokenSecretInput) { tokenSecretInput.required = false; tokenSecretInput.value = ''; }
  }

  function showV2() {
    v1Section.classList.add('d-none');
    v2Section.classList.remove('d-none');
    if (tokenSelect) tokenSelect.required = false;
    if (tokenKeyInput) tokenKeyInput.required = true;
    if (tokenSecretInput) tokenSecretInput.required = true;
  }

  v1Radio.addEventListener('change', () => { if (v1Radio.checked) showV1(); });
  v2Radio.addEventListener('change', () => { if (v2Radio.checked) showV2(); });

  // ── Populate v1 dropdown ──────────────────────────────────────────────────

  async function loadV1Tokens() {
    try {
      const resp = await fetch(TOKEN_API_URL, {
        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const results = data.results || [];

      // Preserve any already-added quick-add option.
      const existingOptions = Array.from(tokenSelect.options).filter(
        o => o.dataset.quickAdd === 'true'
      );

      tokenSelect.innerHTML = '';

      if (existingOptions.length > 0) {
        existingOptions.forEach(o => tokenSelect.appendChild(o));
        const sep = document.createElement('option');
        sep.disabled = true;
        sep.textContent = '──────────────';
        tokenSelect.appendChild(sep);
      }

      if (results.length === 0 && existingOptions.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.disabled = true;
        opt.selected = true;
        opt.textContent = 'No v1 tokens found — use Quick add below';
        tokenSelect.appendChild(opt);
      } else {
        results.forEach(token => {
          const opt = document.createElement('option');
          opt.value = token.id;
          const label = token.display || token.key || `Token #${token.id}`;
          opt.textContent = token.description
            ? `${label} — ${token.description}`
            : label;
          tokenSelect.appendChild(opt);
        });
      }
    } catch (err) {
      tokenSelect.innerHTML = '';
      const opt = document.createElement('option');
      opt.value = '';
      opt.disabled = true;
      opt.selected = true;
      opt.textContent = 'Failed to load tokens — enter manually or Quick add';
      tokenSelect.appendChild(opt);
    }
  }

  modal.addEventListener('shown.bs.modal', () => {
    // Reset to v1 view on each open.
    if (v1Radio.checked) {
      showV1();
      loadV1Tokens();
    }
  });

  // ── Quick add token ───────────────────────────────────────────────────────

  quickAddBtn.addEventListener('click', async () => {
    const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]').value;
    const quickAddUrl = quickAddBtn.dataset.quickAddUrl;

    quickAddBtn.disabled = true;
    quickAddBtn.textContent = 'Creating…';

    try {
      const resp = await fetch(quickAddUrl, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
          'Accept': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
      });
      const data = await resp.json();

      if (!resp.ok) {
        alert(`Failed to create token: ${data.error || resp.status}`);
        return;
      }

      // Prepend as first option and select it.
      const opt = document.createElement('option');
      opt.value = data.id;
      opt.dataset.quickAdd = 'true';
      const label = data.display || `Token #${data.id}`;
      opt.textContent = `${label} [new — delete after export]`;
      opt.selected = true;
      tokenSelect.prepend(opt);

      // Show plaintext in warning banner.
      if (quickAddPlaintext) quickAddPlaintext.value = data.plaintext || '';
      if (quickAddWarning) quickAddWarning.classList.remove('d-none');

    } catch (err) {
      alert(`Unexpected error: ${err.message}`);
    } finally {
      quickAddBtn.disabled = false;
      quickAddBtn.innerHTML = '<i class="mdi mdi-plus" aria-hidden="true"></i> Quick add token';
    }
  });

  // ── Copy to clipboard ─────────────────────────────────────────────────────

  if (copyBtn && quickAddPlaintext) {
    copyBtn.addEventListener('click', () => {
      if (!quickAddPlaintext.value) return;
      navigator.clipboard.writeText(quickAddPlaintext.value).then(() => {
        const originalIcon = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="mdi mdi-check" aria-hidden="true"></i>';
        setTimeout(() => { copyBtn.innerHTML = originalIcon; }, 1500);
      });
    });
  }

  // ── Client-side submit validation ─────────────────────────────────────────

  form.addEventListener('submit', (e) => {
    if (v1Radio.checked) {
      const selected = tokenSelect.value;
      if (!selected) {
        e.preventDefault();
        tokenSelect.setCustomValidity('Select a v1 token or use Quick add to create one.');
        tokenSelect.reportValidity();
        return;
      }
      tokenSelect.setCustomValidity('');
    } else if (v2Radio.checked) {
      const key = (tokenKeyInput && tokenKeyInput.value || '').trim();
      const secret = (tokenSecretInput && tokenSecretInput.value || '').trim();
      if (!key || !secret) {
        e.preventDefault();
        const target = !key ? tokenKeyInput : tokenSecretInput;
        target.setCustomValidity('Both token key and token secret are required.');
        target.reportValidity();
        return;
      }
      if (tokenKeyInput) tokenKeyInput.setCustomValidity('');
      if (tokenSecretInput) tokenSecretInput.setCustomValidity('');
    }
  });

  // Reset custom validity on input change.
  if (tokenSelect) {
    tokenSelect.addEventListener('change', () => tokenSelect.setCustomValidity(''));
  }
  if (tokenKeyInput) {
    tokenKeyInput.addEventListener('input', () => tokenKeyInput.setCustomValidity(''));
  }
  if (tokenSecretInput) {
    tokenSecretInput.addEventListener('input', () => tokenSecretInput.setCustomValidity(''));
  }

  // Initialise the correct section on page load (in case the page was refreshed
  // with the modal already open, though this is rare with Bootstrap modals).
  if (v2Radio.checked) showV2(); else showV1();
}
