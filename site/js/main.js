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

    function update() {
      if (window.scrollY > 10) {
        header.style.boxShadow = '0 4px 6px -1px rgb(0 0 0 / 0.1)';
      } else {
        header.style.boxShadow = '';
      }
    }

    window.addEventListener('scroll', update, { passive: true });
    update();
  }

  function initHeroOffset() {
    const header = document.querySelector('.header');
    const hero = document.querySelector('.hero');
    const menu = document.getElementById('nav-menu');
    if (!header || !hero) return;

    function update() {
      const height = header.offsetHeight;
      hero.style.marginTop = height + 'px';
      if (menu) {
        menu.style.top = height + 'px';
      }
    }

    window.addEventListener('resize', update, { passive: true });
    update();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initMobileMenu();
      initSmoothScroll();
      initHeaderShadow();
      initHeroOffset();
    });
  } else {
    initMobileMenu();
    initSmoothScroll();
    initHeaderShadow();
    initHeroOffset();
  }
})();
