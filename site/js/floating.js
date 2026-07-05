(function () {
  'use strict';

  const COOKIE_KEY = 'ask_cookie_consent';

  function getCookie(name) {
    const value = '; ' + document.cookie;
    const parts = value.split('; ' + name + '=');
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  function setCookie(name, value, days) {
    const expires = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
    document.cookie = name + '=' + encodeURIComponent(value) + '; expires=' + expires + '; path=/; SameSite=Lax';
  }

  function initCookieBanner() {
    const banner = document.getElementById('cookie-banner');
    const acceptBtn = document.getElementById('cookie-accept');
    if (!banner || !acceptBtn) return;

    if (getCookie(COOKIE_KEY)) return;

    banner.classList.add('is-visible');

    acceptBtn.addEventListener('click', function () {
      setCookie(COOKIE_KEY, 'accepted', 365);
      banner.classList.remove('is-visible');
    });
  }

  function initPhoneReveal() {
    const revealButtons = document.querySelectorAll('.phone-block__reveal');
    revealButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        const block = btn.closest('.phone-block');
        block.classList.add('is-revealed');
        btn.setAttribute('aria-expanded', 'true');
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initCookieBanner();
      initPhoneReveal();
    });
  } else {
    initCookieBanner();
    initPhoneReveal();
  }
})();
