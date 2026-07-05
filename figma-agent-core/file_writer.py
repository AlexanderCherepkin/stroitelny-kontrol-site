import os
import re
from pathlib import Path


def _sanitize_component_name(component_name: str) -> str:
    """Проверяет и нормализует имя компонента для безопасного сохранения."""
    name = component_name.replace(".tsx", "").replace(".jsx", "").strip()
    if not name:
        raise ValueError("Component name cannot be empty.")
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", name):
        raise ValueError(
            f"Invalid component name: '{name}'. "
            "Use PascalCase alphanumeric name starting with a letter, e.g. 'BlockchainSection'."
        )
    return name


def _validate_target_dir(target_dir: str, root_dir: str = ".") -> Path:
    """
    Защита от Path Traversal: целевая директория должна находиться внутри root_dir.
    """
    abs_root = os.path.abspath(root_dir)
    abs_target = os.path.abspath(target_dir)
    common = os.path.commonpath([abs_root, abs_target])
    if common != abs_root:
        raise ValueError(
            f"Path traversal detected: target_dir '{target_dir}' resolves outside root '{root_dir}'."
        )
    return Path(abs_target)


def write_component(
    component_name: str,
    code: str,
    target_dir: str = "components",
    root_dir: str = ".",
) -> str:
    """Безопасно записывает код React/Next.js компонента в .tsx файл."""
    try:
        safe_name = _sanitize_component_name(component_name)
    except ValueError as e:
        return f"ERROR: {e}"

    try:
        target = _validate_target_dir(target_dir, root_dir)
        target.mkdir(parents=True, exist_ok=True)

        filename = f"{safe_name}.tsx"
        filepath = target / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)

        return f"SUCCESS: Component '{filename}' saved to '{target_dir}/'."
    except Exception as e:
        return f"ERROR: Failed to save file: {e}"
