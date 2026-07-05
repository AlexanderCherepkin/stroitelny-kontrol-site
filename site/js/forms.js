(function () {
  'use strict';

  function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  function validatePhone(phone) {
    const digits = phone.replace(/\D/g, '');
    return digits.length >= 11;
  }

  function showFieldError(field, message) {
    field.classList.add('is-invalid');
    const input = field.querySelector('.form__input');
    if (input) input.classList.add('is-error');

    let error = field.querySelector('.form__error');
    if (!error) {
      error = document.createElement('span');
      error.className = 'form__error';
      error.setAttribute('role', 'alert');
      field.appendChild(error);
    }
    error.textContent = message;
  }

  function clearFieldError(field) {
    field.classList.remove('is-invalid');
    const input = field.querySelector('.form__input');
    if (input) input.classList.remove('is-error');
    const error = field.querySelector('.form__error');
    if (error) error.textContent = '';
  }

  function validateConsent(checkbox) {
    const label = checkbox.closest('.checkbox');
    if (!checkbox.checked) {
      label.classList.add('is-missed');
      return false;
    }
    label.classList.remove('is-missed');
    return true;
  }

  function clearConsentError(checkbox) {
    const label = checkbox.closest('.checkbox');
    label.classList.remove('is-missed');
  }

  function collectFormData(form) {
    const data = {};
    const elements = form.querySelectorAll('input, textarea, select');
    elements.forEach(function (el) {
      if (el.type === 'checkbox') {
        data[el.name] = el.checked;
      } else if (el.type === 'file') {
        data[el.name] = el.files.length ? el.files[0].name : null;
      } else {
        data[el.name] = el.value.trim();
      }
    });
    return data;
  }

  function showToast(message) {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');
    if (!toast || !toastMessage) return;
    toastMessage.textContent = message;
    toast.hidden = false;
    requestAnimationFrame(function () {
      toast.classList.add('is-visible');
    });
    setTimeout(function () {
      toast.classList.remove('is-visible');
      setTimeout(function () {
        toast.hidden = true;
      }, 300);
    }, 3000);
  }

  function initForms() {
    const forms = document.querySelectorAll('.js-form');
    forms.forEach(function (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();

        const fields = form.querySelectorAll('.form__field');
        fields.forEach(clearFieldError);

        let isValid = true;
        let hasContact = false;

        const phoneInput = form.querySelector('.js-phone');
        const emailInput = form.querySelector('input[type="email"]');
        const consentCheckbox = form.querySelector('.js-consent');

        if (phoneInput) {
          const phoneField = phoneInput.closest('.form__field');
          if (phoneInput.value.trim() && !validatePhone(phoneInput.value)) {
            showFieldError(phoneField, 'Введите корректный номер телефона');
            isValid = false;
          } else if (validatePhone(phoneInput.value)) {
            hasContact = true;
          }
        }

        if (emailInput) {
          const emailField = emailInput.closest('.form__field');
          if (emailInput.hasAttribute('required') || emailInput.value.trim()) {
            if (!validateEmail(emailInput.value.trim())) {
              showFieldError(emailField, 'Введите корректный email');
              isValid = false;
            } else {
              hasContact = true;
            }
          }
          if (!emailInput.hasAttribute('required') && validateEmail(emailInput.value.trim())) {
            hasContact = true;
          }
        }

        if (!hasContact) {
          if (phoneInput) {
            showFieldError(phoneInput.closest('.form__field'), 'Укажите телефон или email');
          }
          if (emailInput) {
            showFieldError(emailInput.closest('.form__field'), 'Укажите телефон или email');
          }
          isValid = false;
        }

        if (consentCheckbox && !validateConsent(consentCheckbox)) {
          isValid = false;
        }

        if (!isValid) {
          const firstInvalid = form.querySelector('.is-invalid, .is-missed');
          if (firstInvalid) {
            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
            const input = firstInvalid.querySelector('.form__input, .checkbox__input');
            if (input) input.focus();
          }
          return;
        }

        const data = collectFormData(form);
        console.log('Form submitted:', data);
        showToast('Заявка отправлена. Мы свяжемся с вами в ближайшее время.');
        form.reset();
      });

      const consentCheckbox = form.querySelector('.js-consent');
      if (consentCheckbox) {
        consentCheckbox.addEventListener('change', function () {
          clearConsentError(consentCheckbox);
        });
      }
    });

    const fileInputs = document.querySelectorAll('.js-file');
    fileInputs.forEach(function (input) {
      const nameDisplay = input.closest('.form__field').querySelector('.js-file-name');
      input.addEventListener('change', function () {
        if (nameDisplay) {
          nameDisplay.textContent = input.files.length ? input.files[0].name : 'Файл не выбран';
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initForms);
  } else {
    initForms();
  }
})();
