(function (root) {
  'use strict';

  // HID keyboard-wedge scanners send physical key positions. Windows may render
  // these as Persian letters; reconstruct US-ASCII ONLY in dedicated scan fields.
  // Do not globally remap keyboard input: Persian waybill entry must be untouched.
  var scanFields = { v16ScanInput: true, v19WaybillCode: true, v22QrScanInput: true };
  var punctuation = {
    Minus: ['-', '_'], Equal: ['=', '+'], BracketLeft: ['[', '{'],
    BracketRight: [']', '}'], Backslash: ['\\', '|'], Semicolon: [';', ':'],
    Quote: ["'", '"'], Backquote: ['`', '~'], Comma: [',', '<'],
    Period: ['.', '>'], Slash: ['/', '?'], Space: [' ', ' '],
    NumpadDecimal: ['.', '.'], NumpadSubtract: ['-', '-'],
    NumpadAdd: ['+', '+']
  };

  function usCharacter(event) {
    var code = String(event.code || ''), shift = !!event.shiftKey, i;
    if (/^Key[A-Z]$/.test(code))
      return shift ? code.slice(3) : code.slice(3).toLowerCase();
    if (/^Digit[0-9]$/.test(code)) {
      i = Number(code.slice(5));
      return shift ? ')!@#$%^&*('[i] : String(i);
    }
    if (/^Numpad[0-9]$/.test(code)) return code.slice(6);
    if (punctuation[code]) return punctuation[code][shift ? 1 : 0];
    // Some remote/HID implementations omit code. Accept only ASCII key text,
    // never guess a reverse Persian keyboard mapping for unknown layouts.
    if (!code && /^[A-Za-z0-9._-]$/.test(event.key || '')) return event.key;
    return null;
  }

  function insertCharacter(el, character) {
    var a = typeof el.selectionStart === 'number' ? el.selectionStart : el.value.length;
    var b = typeof el.selectionEnd === 'number' ? el.selectionEnd : a;
    if (el.maxLength >= 0 && el.value.length - (b - a) + character.length > el.maxLength)
      return false;
    if (typeof el.setRangeText === 'function')
      el.setRangeText(character, a, b, 'end');
    else
      el.value = el.value.slice(0, a) + character + el.value.slice(b);
    if (typeof el.dispatchEvent === 'function')
      el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }

  function isValidScan(value) {
    return /^ABV16\.[ZB]\.[A-Za-z0-9_-]+$/.test(value) ||
      /^[0-9۰-۹٠-٩]{1,9}$/.test(value);
  }

  function submitReleaseScan(doc, host) {
    var el = doc.getElementById('v22QrScanInput');
    if (!el) return false;
    var value = String(el.value || '').trim(), status = doc.getElementById('v22Msg');
    if (!value) return false;
    el.value = '';
    if (!isValidScan(value)) {
      if (status) {
        status.textContent = 'اسکن ناقص یا نامعتبر است؛ دوباره اسکن کنید.';
        if (status.classList) status.classList.add('is-error');
      }
      el.focus();
      return false;
    }
    if (!host || typeof host.barresanReleaseScan !== 'function') {
      if (status) status.textContent = 'بخش ترخیص آماده نیست؛ صفحه را دوباره باز کنید.';
      el.focus();
      return false;
    }
    host.barresanReleaseScan(value);
    el.focus();
    return true;
  }

  function install(doc, host) {
    if (!doc || !doc.addEventListener) return;
    doc.addEventListener('keydown', function (event) {
      var el = event.target;
      if (!el || !scanFields[el.id] || el.disabled || el.readOnly) return;
      if (event.ctrlKey || event.altKey || event.metaKey || event.isComposing) return;
      if (el.id === 'v22QrScanInput' &&
          (event.key === 'Enter' || event.code === 'Enter')) {
        event.preventDefault();
        event.stopPropagation();
        submitReleaseScan(doc, host);
        return;
      }
      // Existing Enter handlers still issue/receive/handover each complete scan.
      if (event.key === 'Enter' || event.code === 'Enter') return;
      if (event.key === 'Tab' || event.code === 'Tab' ||
          event.key === 'Backspace' || event.code === 'Backspace' ||
          event.key === 'Delete' || event.code === 'Delete') return;
      var char = usCharacter(event);
      if (char === null) return;
      event.preventDefault();
      event.stopPropagation();
      insertCharacter(el, char);
    }, true);
    var submit = doc.getElementById('v22QrSubmit');
    if (submit && submit.addEventListener)
      submit.addEventListener('click', function () { submitReleaseScan(doc, host); });
  }

  if (typeof module !== 'undefined' && module.exports)
    module.exports = { usCharacter: usCharacter, insertCharacter: insertCharacter,
      isValidScan: isValidScan, submitReleaseScan: submitReleaseScan, install: install };
  if (root && root.document) install(root.document, root);
})(typeof window === 'undefined' ? null : window);
