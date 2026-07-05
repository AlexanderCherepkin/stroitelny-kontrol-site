(function () {
  'use strict';

  let activeModal = null;
  let lastFocusedElement = null;

  function getScrollbarWidth() {
    return window.innerWidth - document.documentElement.clientWidth;
  }

  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;

    lastFocusedElement = document.activeElement;
    modal.hidden = false;
    document.body.classList.add('no-scroll');
    document.body.style.paddingRight = getScrollbarWidth() + 'px';

    const title = modal.querySelector('.modal__title');
    if (title) {
      setTimeout(function () {
        title.focus();
      }, 50);
    }

    activeModal = modal;
    bindModalEvents(modal);
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove('no-scroll');
    document.body.style.paddingRight = '';
    if (lastFocusedElement) {
      lastFocusedElement.focus();
      lastFocusedElement = null;
    }
    activeModal = null;
  }

  function bindModalEvents(modal) {
    const closeButtons = modal.querySelectorAll('[data-close-modal]');
    closeButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        closeModal(modal);
      });
    });

    modal.addEventListener('click', function (e) {
      if (e.target === modal || e.target.classList.contains('modal__overlay')) {
        closeModal(modal);
      }
    });

    modal.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        closeModal(modal);
      }
      if (e.key === 'Tab') {
        trapFocus(e, modal);
      }
    });
  }

  function trapFocus(e, modal) {
    const focusable = modal.querySelectorAll('a[href], button, input, textarea, select, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function initModals() {
    const triggers = document.querySelectorAll('[data-modal]');
    triggers.forEach(function (trigger) {
      trigger.addEventListener('click', function () {
        const modalId = 'modal-' + trigger.dataset.modal;
        openModal(modalId);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initModals);
  } else {
    initModals();
  }
})();
