(function () {
  'use strict';

  function initMobileMenu() {
    const toggle = document.querySelector('.nav__toggle');
    const menu = document.getElementById('nav-menu');
    if (!toggle || !menu) return;

    toggle.addEventListener('click', function () {
      const isOpen = menu.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });

    menu.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        menu.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (link) {
      link.addEventListener('click', function (e) {
        const href = link.getAttribute('href');
        if (href === '#') return;
        const target = document.querySelector(href);
        if (target) {
          e.preventDefault();
          const headerHeight = document.querySelector('.header').offsetHeight;
          const top = target.getBoundingClientRect().top + window.pageYOffset - headerHeight;
          window.scrollTo({ top: top, behavior: 'smooth' });
        }
      });
    });
  }

  function initHeaderShadow() {
    const header = document.querySelector('.header');
    if (!header) return;

    let ticking = false;
    function update() {
      const scrolled = window.scrollY > 10;
      header.classList.toggle('header--scrolled', scrolled);
      ticking = false;
    }

    window.addEventListener('scroll', function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    }, { passive: true });
    update();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initMobileMenu();
      initSmoothScroll();
      initHeaderShadow();
    });
  } else {
    initMobileMenu();
    initSmoothScroll();
    initHeaderShadow();
  }
})();
