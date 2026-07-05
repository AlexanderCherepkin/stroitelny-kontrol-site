(function () {
  'use strict';

  const PREFIX = '+7';
  const DIGITS_ONLY = /\D/g;

  function formatPhone(value) {
    const digits = value.replace(DIGITS_ONLY, '');
    const relevant = digits.startsWith('7') || digits.startsWith('8') ? digits.slice(1) : digits;

    let formatted = PREFIX;
    if (relevant.length > 0) {
      formatted += ' (' + relevant.slice(0, 3);
    }
    if (relevant.length >= 3) {
      formatted += ')';
    }
    if (relevant.length > 3) {
      formatted += ' ' + relevant.slice(3, 6);
    }
    if (relevant.length > 6) {
      formatted += '-' + relevant.slice(6, 8);
    }
    if (relevant.length > 8) {
      formatted += '-' + relevant.slice(8, 10);
    }
    return formatted.slice(0, 18);
  }

  function stripPrefix(value) {
    return value.replace(DIGITS_ONLY, '').replace(/^7|^8/, '');
  }

  function getCursorPosition(input) {
    return input.selectionStart;
  }

  function setCursorAfterPrefix(input) {
    const pos = PREFIX.length + 1;
    input.setSelectionRange(pos, pos);
  }

  function initPhoneInputs() {
    const inputs = document.querySelectorAll('.js-phone');
    inputs.forEach(function (input) {
      input.placeholder = '+7 (___) ___-__-__';
      input.addEventListener('focus', function () {
        if (!input.value) {
          input.value = PREFIX + ' ';
        }
        setCursorAfterPrefix(input);
      });

      input.addEventListener('click', function () {
        if (input.value.indexOf(PREFIX) !== 0) {
          input.value = PREFIX + ' ';
        }
        setCursorAfterPrefix(input);
      });

      input.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' || e.key === 'Delete') {
          const start = input.selectionStart;
          const end = input.selectionEnd;
          const prefixEnd = PREFIX.length + 1;
          if (start < prefixEnd && end < prefixEnd) {
            e.preventDefault();
          }
        }
      });

      input.addEventListener('input', function () {
        const raw = input.value;
        const cursor = getCursorPosition(input);
        const hadPrefix = raw.indexOf(PREFIX) === 0;

        let digits = raw.replace(DIGITS_ONLY, '');

        if (!hadPrefix) {
          if (digits.startsWith('7') || digits.startsWith('8')) {
            digits = digits.slice(1);
          }
        } else {
          digits = stripPrefix(raw);
        }

        const formatted = formatPhone(digits);
        input.value = formatted;

        let newCursor = formatted.length;
        if (cursor <= PREFIX.length + 1) {
          newCursor = PREFIX.length + 1;
        } else {
          const diff = formatted.length - raw.length;
          newCursor = Math.max(PREFIX.length + 1, Math.min(cursor + diff, formatted.length));
        }
        input.setSelectionRange(newCursor, newCursor);
      });

      input.addEventListener('blur', function () {
        if (input.value === PREFIX + ' ' || input.value === PREFIX) {
          input.value = '';
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPhoneInputs);
  } else {
    initPhoneInputs();
  }
})();
