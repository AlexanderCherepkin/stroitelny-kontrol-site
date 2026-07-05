"""Единый HTTP-клиент для Figma REST API с retry, backoff и rate-limit обработкой."""

from __future__ import annotations

import time
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class FigmaHTTPClient:
    """Обертка над requests.Session для работы с Figma API.

    Особенности:
      - централизованный retry c exponential backoff;
      - обработка HTTP 429 с учетом заголовка Retry-After;
      - искусственная задержка между запросами для снижения burst-нагрузки;
      - один shared Session/adapter для connection reuse.
    """

    DEFAULT_MAX_RETRIES = 5
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_REQUEST_DELAY = 1.0
    DEFAULT_STATUS_FORCELIST = (429, 500, 502, 503, 504)

    def __init__(
        self,
        token: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        timeout: float = 60.0,
    ) -> None:
        self.token = token
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.request_delay = request_delay
        self.timeout = timeout
        self._last_request_time: Optional[float] = None
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"X-Figma-Token": self.token})
        # urllib3 retry не умеет читать Retry-After для 429 точно, поэтому
        # финальная обработка 429 делается вручную ниже. Здесь retry только
        # для транзиентных сетевых ошибок и 5xx.
        retries = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _throttle(self) -> None:
        """Замедляет последовательные запросы, чтобы не провоцировать burst detection."""
        if self.request_delay <= 0 or self._last_request_time is None:
            self._last_request_time = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Выполняет запрос с throttle и ручным retry по 429/Retry-After."""
        timeout = kwargs.pop("timeout", self.timeout)
        attempt = 0
        while True:
            self._throttle()
            response = self._session.request(method, url, timeout=timeout, **kwargs)
            if response.status_code != 429:
                return response
            # 429 handling: читаем Retry-After, иначе exponential backoff.
            attempt += 1
            if attempt > self.max_retries:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    wait = float(retry_after)
                except (ValueError, TypeError):
                    wait = self.backoff_factor * (2 ** (attempt - 1))
            else:
                wait = self.backoff_factor * (2 ** (attempt - 1))
            # Небольшой запас, чтобы не задевать границу.
            wait += 1.0
            print(f"[FIGMA RATE LIMIT] 429 received. Retry {attempt}/{self.max_retries}. "
                  f"Waiting {wait:.1f}s...")
            time.sleep(wait)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def close(self) -> None:
        self._session.close()
