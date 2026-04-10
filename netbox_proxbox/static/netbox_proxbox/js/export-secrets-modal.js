/**
 * export-secrets-modal.js
 *
 * Handles the "Export with secrets" modal:
 *  - v1/v2 token version toggle (show/hide sections, toggle required attributes)
 *  - v1 sub-mode: select existing token OR enter manually (mutually exclusive)
 *  - Populates the v1 token dropdown from the NetBox Token API
 *  - Quick-add token: creates a v1 token via the plugin endpoint and fills the dropdown
 *  - Copy-to-clipboard for the newly created token plaintext
 *  - Client-side validation before form submit
 */

(function () {
  'use strict';

  const MODAL_ID = 'proxmox-export-secrets-modal';
  const TOKEN_API_URL = '/api/users/tokens/?version=1&enabled=true&limit=0';

  function init() {
    const modal = document.getElementById(MODAL_ID);
    if (!modal) return;

    const form = modal.querySelector('#export-secrets-form');
    const v1Radio = modal.querySelector('#token_version_v1');
    const v2Radio = modal.querySelector('#token_version_v2');
    const v1Section = modal.querySelector('#v1-token-section');
    const v2Section = modal.querySelector('#v2-token-section');
    const tokenSelect = modal.querySelector('#id_token_id');
    const v1ManualInput = modal.querySelector('#id_v1_manual_token');
    const v1SelectRadio = modal.querySelector('#v1_mode_select');
    const v1ManualRadio = modal.querySelector('#v1_mode_manual');
    const v1SelectGroup = modal.querySelector('#v1-select-group');
    const v1ManualGroup = modal.querySelector('#v1-manual-group');
    const quickAddBtn = modal.querySelector('#btn-quick-add-token');
    const quickAddWarning = modal.querySelector('#quick-add-warning');
    const quickAddPlaintext = modal.querySelector('#id_quick_add_plaintext');
    const copyBtn = modal.querySelector('#btn-copy-token');
    const tokenKeyInput = modal.querySelector('#id_token_key');
    const tokenSecretInput = modal.querySelector('#id_token_secret');

    // ── v1/v2 version toggle ──────────────────────────────────────────────

    function showV1() {
      v1Section.classList.remove('d-none');
      v2Section.classList.add('d-none');
      syncV1SubMode();
      if (tokenKeyInput) { tokenKeyInput.required = false; tokenKeyInput.value = ''; }
      if (tokenSecretInput) { tokenSecretInput.required = false; tokenSecretInput.value = ''; }
    }

    function showV2() {
      v1Section.classList.add('d-none');
      v2Section.classList.remove('d-none');
      if (tokenSelect) tokenSelect.required = false;
      if (v1ManualInput) v1ManualInput.required = false;
      if (tokenKeyInput) tokenKeyInput.required = true;
      if (tokenSecretInput) tokenSecretInput.required = true;
    }

    if (v1Radio) v1Radio.addEventListener('change', () => { if (v1Radio.checked) showV1(); });
    if (v2Radio) v2Radio.addEventListener('change', () => { if (v2Radio.checked) showV2(); });

    // ── v1 sub-mode: select existing vs manual ────────────────────────────

    function syncV1SubMode() {
      const selectMode = v1SelectRadio && v1SelectRadio.checked;
      if (v1SelectGroup) v1SelectGroup.classList.toggle('d-none', !selectMode);
      if (v1ManualGroup) v1ManualGroup.classList.toggle('d-none', selectMode);
      if (tokenSelect) tokenSelect.required = selectMode;
      if (v1ManualInput) v1ManualInput.required = !selectMode;
    }

    if (v1SelectRadio) v1SelectRadio.addEventListener('change', syncV1SubMode);
    if (v1ManualRadio) v1ManualRadio.addEventListener('change', syncV1SubMode);

    // ── Populate v1 dropdown ──────────────────────────────────────────────

    let tokensLoaded = false;

    async function loadV1Tokens() {
      if (!tokenSelect) return;
      try {
        const resp = await fetch(TOKEN_API_URL, {
          headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin',
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        const results = data.results || [];

        // Preserve any already-added quick-add option.
        const quickAddOpts = Array.from(tokenSelect.options).filter(
          function (o) { return o.dataset.quickAdd === 'true'; }
        );

        tokenSelect.innerHTML = '';

        if (quickAddOpts.length > 0) {
          quickAddOpts.forEach(function (o) { tokenSelect.appendChild(o); });
          var sep = document.createElement('option');
          sep.disabled = true;
          sep.textContent = '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500';
          tokenSelect.appendChild(sep);
        }

        if (results.length === 0 && quickAddOpts.length === 0) {
          var opt = document.createElement('option');
          opt.value = '';
          opt.disabled = true;
          opt.selected = true;
          opt.textContent = 'No v1 tokens found \u2014 use Quick add or enter manually';
          tokenSelect.appendChild(opt);
        } else {
          if (quickAddOpts.length === 0) {
            // Add a placeholder first option.
            var placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.disabled = true;
            placeholder.selected = true;
            placeholder.textContent = 'Choose a token\u2026';
            tokenSelect.appendChild(placeholder);
          }
          results.forEach(function (token) {
            var opt = document.createElement('option');
            opt.value = token.id;
            var label = token.display || token.key || ('Token #' + token.id);
            opt.textContent = token.description ? label + ' \u2014 ' + token.description : label;
            tokenSelect.appendChild(opt);
          });
        }
        tokensLoaded = true;
      } catch (err) {
        console.error('[export-secrets-modal] Failed to load v1 tokens:', err);
        tokenSelect.innerHTML = '';
        var opt = document.createElement('option');
        opt.value = '';
        opt.disabled = true;
        opt.selected = true;
        opt.textContent = 'Failed to load tokens \u2014 enter manually or Quick add';
        tokenSelect.appendChild(opt);
      }
    }

    modal.addEventListener('shown.bs.modal', function () {
      if (v1Radio && v1Radio.checked) showV1();
      if (!tokensLoaded) loadV1Tokens();
    });

    // ── Quick add token ───────────────────────────────────────────────────

    if (quickAddBtn) {
      quickAddBtn.addEventListener('click', function () {
        var csrfInput = form.querySelector('[name=csrfmiddlewaretoken]');
        var csrfToken = csrfInput ? csrfInput.value : '';
        var quickAddUrl = quickAddBtn.dataset.quickAddUrl;

        quickAddBtn.disabled = true;
        quickAddBtn.textContent = 'Creating\u2026';

        fetch(quickAddUrl, {
          method: 'POST',
          headers: {
            'X-CSRFToken': csrfToken,
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          },
          credentials: 'same-origin',
        })
        .then(function (resp) {
          return resp.json().then(function (data) { return { ok: resp.ok, status: resp.status, data: data }; });
        })
        .then(function (result) {
          if (!result.ok) {
            alert('Failed to create token: ' + (result.data.error || result.status));
            return;
          }

          // Switch to select mode if in manual mode.
          if (v1SelectRadio && !v1SelectRadio.checked) {
            v1SelectRadio.checked = true;
            syncV1SubMode();
          }

          // Prepend as first option and select it.
          var opt = document.createElement('option');
          opt.value = result.data.id;
          opt.dataset.quickAdd = 'true';
          var label = result.data.display || ('Token #' + result.data.id);
          opt.textContent = label + ' [new \u2014 delete after export]';
          opt.selected = true;
          // Deselect other options.
          Array.from(tokenSelect.options).forEach(function (o) { o.selected = false; });
          tokenSelect.prepend(opt);
          opt.selected = true;

          // Show plaintext in warning banner.
          if (quickAddPlaintext) quickAddPlaintext.value = result.data.plaintext || '';
          if (quickAddWarning) quickAddWarning.classList.remove('d-none');
        })
        .catch(function (err) {
          alert('Unexpected error: ' + err.message);
        })
        .finally(function () {
          quickAddBtn.disabled = false;
          quickAddBtn.innerHTML = '<i class="mdi mdi-plus" aria-hidden="true"></i> Quick add token';
        });
      });
    }

    // ── Copy to clipboard ─────────────────────────────────────────────────

    if (copyBtn && quickAddPlaintext) {
      copyBtn.addEventListener('click', function () {
        if (!quickAddPlaintext.value) return;
        navigator.clipboard.writeText(quickAddPlaintext.value).then(function () {
          var original = copyBtn.innerHTML;
          copyBtn.innerHTML = '<i class="mdi mdi-check" aria-hidden="true"></i>';
          setTimeout(function () { copyBtn.innerHTML = original; }, 1500);
        });
      });
    }

    // ── Client-side submit validation ─────────────────────────────────────

    form.addEventListener('submit', function (e) {
      if (v1Radio && v1Radio.checked) {
        var isManual = v1ManualRadio && v1ManualRadio.checked;
        if (isManual) {
          var raw = (v1ManualInput.value || '').trim();
          if (!raw) {
            e.preventDefault();
            v1ManualInput.setCustomValidity('Enter a v1 token value.');
            v1ManualInput.reportValidity();
            return;
          }
          v1ManualInput.setCustomValidity('');
        } else {
          var selected = tokenSelect.value;
          if (!selected) {
            e.preventDefault();
            tokenSelect.setCustomValidity('Select a v1 token or switch to manual entry.');
            tokenSelect.reportValidity();
            return;
          }
          tokenSelect.setCustomValidity('');
        }
      } else if (v2Radio && v2Radio.checked) {
        var key = (tokenKeyInput ? tokenKeyInput.value : '').trim();
        var secret = (tokenSecretInput ? tokenSecretInput.value : '').trim();
        if (!key || !secret) {
          e.preventDefault();
          var target = !key ? tokenKeyInput : tokenSecretInput;
          target.setCustomValidity('Both token key and token secret are required.');
          target.reportValidity();
          return;
        }
        if (tokenKeyInput) tokenKeyInput.setCustomValidity('');
        if (tokenSecretInput) tokenSecretInput.setCustomValidity('');
      }
    });

    // Reset custom validity on input change.
    [tokenSelect, tokenKeyInput, tokenSecretInput, v1ManualInput].forEach(function (el) {
      if (!el) return;
      var evt = el.tagName === 'SELECT' ? 'change' : 'input';
      el.addEventListener(evt, function () { el.setCustomValidity(''); });
    });

    // Initial state.
    if (v2Radio && v2Radio.checked) showV2(); else showV1();
  }

  // Run init when the DOM is ready.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
