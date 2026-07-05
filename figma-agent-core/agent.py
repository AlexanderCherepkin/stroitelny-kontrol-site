
import json
import os
import sys
import argparse
import ast
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
from dotenv import load_dotenv

import analyzer
import file_writer
import asset_downloader
import spec_writer


load_dotenv()


def _to_pascal_case(name: str) -> str:
    """Превращает произвольное имя Figma-ноды в валидное PascalCase-имя компонента."""
    name = name.strip()
    name = re.sub(r"[^\w\s]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    words = name.split(" ")
    result = "".join(word[:1].upper() + word[1:] for word in words if word)
    result = re.sub(r"[^A-Za-z0-9_]+", "", result)
    if not result or not result[0].isalpha():
        result = "Figma" + result
    return result


def _extract_annotation_text(annotations: List[Dict[str, Any]]) -> str:
    """Concatenate annotation labels/descriptions into a semantic hint."""
    parts: List[str] = []
    for annotation in annotations or []:
        label = annotation.get("label") or ""
        description = annotation.get("description") or ""
        if isinstance(label, str):
            parts.append(label.strip())
        if isinstance(description, str):
            parts.append(description.strip())
    return " ".join(p for p in parts if p)


def _build_semantic_summary(node: Dict[str, Any]) -> str:
    """Build a concise semantic summary from node metadata for the LLM prompt."""
    parts: List[str] = []
    semantic_name = analyzer.infer_semantic_name(node)
    parts.append(f"Semantic component name: {semantic_name}")

    description = node.get("description")
    if description:
        parts.append(f"Description: {description}")

    annotation_text = _extract_annotation_text(node.get("annotations"))
    if annotation_text:
        parts.append(f"Annotations: {annotation_text}")

    return "\n".join(parts)


def _maybe_bootstrap(filepath: str) -> bool:
    """Если JSON-контекст отсутствует и есть токен с URL, автоматически запускает bootstrap.py."""
    if Path(filepath).exists():
        return True

    token = os.environ.get("FIGMA_TOKEN")
    url = os.environ.get("FIGMA_URL")
    if not token or not url:
        return False

    print("[AGENT] Context file missing; auto-running bootstrap.py with depth=2...")
    try:
        subprocess.run(
            [sys.executable, "bootstrap.py", "--api-depth", "2"],
            check=True,
            timeout=300,
        )
        return Path(filepath).exists()
    except subprocess.CalledProcessError as e:
        print(f"[AGENT] bootstrap.py failed: {e}")
        return False
    except Exception as e:
        print(f"[AGENT] Could not auto-run bootstrap.py: {e}")
        return False


def _download_assets_for_context(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Находит isAsset ноды в текущем контексте, запрашивает URL'ы и скачивает ассеты в public/images/.
    Возвращает словарь {node_id: public_path}.
    """
    assets = asset_downloader.collect_assets_from_tree(data)
    if not assets:
        return {}

    token = os.environ.get("FIGMA_TOKEN")
    url = os.environ.get("FIGMA_URL")
    if not token or not url:
        print("[WARNING] FIGMA_TOKEN/FIGMA_URL not set; skipping asset download.")
        return {}

    file_key_match = re.search(r"/file/([^/]+)", url) or re.search(r"/design/([^/]+)", url)
    if not file_key_match:
        print("[WARNING] Could not parse Figma file key from FIGMA_URL; skipping asset download.")
        return {}
    file_key = file_key_match.group(1)

    asset_ids = [a["id"] for a in assets]
    print(f"[ASSETS] Found {len(asset_ids)} asset(s) in context. Requesting image URLs...")

    svg_ids = [a["id"] for a in assets if a.get("assetFormat") == "svg"]
    raster_ids = [a["id"] for a in assets if a.get("assetFormat") != "svg"]

    urls: Dict[str, str] = {}
    if raster_ids:
        urls.update(asset_downloader.get_image_urls_from_figma(file_key, raster_ids, token, format="png"))
    if svg_ids:
        urls.update(asset_downloader.get_image_urls_from_figma(file_key, svg_ids, token, format="svg"))

    public_paths: Dict[str, str] = {}
    for asset in assets:
        node_id = asset["id"]
        image_url = urls.get(node_id)
        if not image_url:
            print(f"[WARNING] No image URL for asset {node_id} ({asset.get('name')}).")
            continue
        fmt = asset.get("assetFormat", "png")
        public_path = asset_downloader.save_asset(node_id, asset.get("name", "asset"), fmt, image_url)
        if public_path:
            public_paths[node_id] = public_path
            print(f"[ASSETS] Saved asset {node_id} -> {public_path}")
        else:
            print(f"[WARNING] Failed to download asset {node_id}.")

    return public_paths


def _inject_asset_paths(data: Any, asset_paths: Dict[str, str]) -> Any:
    """Рекурсивно добавляет publicPath в ассет-ноды для передачи в LLM."""
    if not isinstance(data, dict):
        return data
    if data.get("isAsset") and data.get("id") in asset_paths:
        data["publicPath"] = asset_paths[data["id"]]
    for child in data.get("children", []):
        _inject_asset_paths(child, asset_paths)
    return data


TOOLS: Dict[str, Callable[..., Any]] = {
    "WRITE_FILE": file_writer.write_component,
    "FETCH_NODE": analyzer.get_node_details,
    "WRITE_SPEC": spec_writer.generate_spec,
}


class FigmaAgent:
    def __init__(self):
        self.system_prompt = (
            "You are an expert Next.js and Tailwind CSS developer acting as a Figma-to-code agent.\n"
            "You receive a Figma node tree enriched with design tokens: fills (hex/rgb), font styles, "
            "AutoLayout properties, bounding boxes, local image paths (publicPath), and semantic metadata.\n\n"
            "Semantic metadata:\n"
            "- Each node may include 'description' (author-provided intent) and 'annotations' (design comments/labels).\n"
            "- Use 'description' and 'annotations' to understand the purpose of a section/component.\n"
            "- Prefer the semantic name derived from metadata when choosing component names and HTML tags.\n\n"
            "You have access to the following tools:\n"
            "- WRITE_FILE(component_name='Name', code='''...''') — saves a generated .tsx component.\n"
            "- FETCH_NODE(node_id='123:456') — returns details of a specific Figma node by id.\n"
            "- WRITE_SPEC(node, output_path='spec.md') — generates a Markdown technical specification from the node tree.\n\n"
            "Rules for generated code:\n"
            "- Use Tailwind CSS for layout, spacing, typography and positioning.\n"
            "- Map Figma AutoLayout properties (layoutMode, itemSpacing, paddings, alignments) accurately.\n"
            "- Use REAL colors from the fills array (hex/rgb values), do not invent placeholders like bg-gray-900.\n"
            "- Use REAL font sizes and weights from style objects.\n"
            "- For image/vector nodes that have publicPath, use an <img src='/images/...' /> tag with that path.\n"
            "- Default export, valid Next.js TypeScript component.\n"
            "- Use semantic HTML tags where appropriate.\n"
            "- Name components semantically: e.g. HeroSection, PricingCard, FeatureList, NavBar, not Container1 or Frame23.\n\n"
            "When you want to inspect a node, output:\n"
            "ACTION: FETCH_NODE(node_id='662:808')\n"
            "OBSERVATION: <summarize what you learned>\n\n"
            "When you are ready to save the final component, output exactly:\n"
            "ACTION: WRITE_FILE(component_name='BlockchainSection', code='''...full TSX code...''')\n"
            "Use triple single quotes inside code= to avoid escaping issues.\n\n"
            "If you do not use ACTION: WRITE_FILE, output the final component code inside a markdown block:\n"
            "```tsx\n...\n```\n"
        )
        self.api_key = os.environ.get("LLM_API_KEY", "ollama-dummy-key")
        self.api_url = os.environ.get("LLM_API_URL", "http://localhost:11434/v1/chat/completions")
        self.model_name = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")

    def load_context(
        self,
        filepath: str,
        node_id: Optional[str] = None,
        download_assets: bool = True,
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        if not _maybe_bootstrap(filepath):
            if not Path(filepath).exists():
                print(f"[ERROR] Context file not found: {filepath}. Set FIGMA_TOKEN/FIGMA_URL or provide a mock.")
                sys.exit(1)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load context: {e}")
            sys.exit(1)

        selected_node = data
        if node_id:
            target = analyzer.find_node_by_id(data, node_id)
            if not target:
                print(f"[ERROR] Node {node_id} not found in {filepath}.")
                print("[HINT] Run 'python analyzer.py' to list available node IDs.")
                sys.exit(1)
            print(f"[AGENT] Using targeted node context: {target.get('name')} ({node_id})")
            selected_node = target

        if download_assets:
            asset_paths = _download_assets_for_context(selected_node)
            if asset_paths:
                selected_node = _inject_asset_paths(selected_node, asset_paths)

        context = json.dumps(selected_node, ensure_ascii=False, indent=2)
        print(f"[AGENT] Context size: {len(context):,} chars")
        return context, selected_node

    def call_llm(self, task: str, context_data: str, semantic_summary: str = "") -> str:
        print("[AGENT] Starting task analysis...")
        print(f"[TASK] {task}")

        is_local = self.api_key in ("ollama-dummy-key", "", "local", None)
        if is_local and "localhost" in self.api_url:
            print("[API] Sending request to local Ollama provider...")
        else:
            print("[API] Sending request to LLM provider...")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8"
        }
        user_content = f"Figma Context Data:\n{context_data}\n\n"
        if semantic_summary:
            user_content += f"Semantic Metadata:\n{semantic_summary}\n\n"
        user_content += f"Task: {task}"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content}
        ]
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1
        }

        try:
            encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            response = requests.post(self.api_url, data=encoded_payload, headers=headers, timeout=120)
        except Exception as e:
            print(f"[ERROR] Failed to communicate with LLM API: {e}")
            print("[HINT] If using Ollama, start it with: ollama serve")
            sys.exit(1)

        if response.status_code != 200:
            print(f"[ERROR] API returned status code {response.status_code}: {response.text}")
            sys.exit(1)

        try:
            ai_response = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            print(f"[ERROR] Unexpected LLM response format: {e}")
            print(f"[DEBUG] Response body: {response.text[:500]}")
            sys.exit(1)

        return ai_response

    @staticmethod
    def _split_args(args_str: str):
        parts = []
        depth = 0
        in_string = None
        escape = False
        current = []
        for ch in args_str:
            if escape:
                current.append(ch)
                escape = False
                continue
            if ch == "\\":
                current.append(ch)
                escape = True
                continue
            if in_string:
                current.append(ch)
                triple = "".join(current[-3:])
                if in_string.startswith("'''") and triple.endswith("'''"):
                    in_string = None
                elif in_string.startswith('"""') and triple.endswith('"""'):
                    in_string = None
                elif not in_string.startswith(("'''", '"""')) and ch == in_string:
                    in_string = None
                continue
            if ch in "'\"":
                in_string = ch
                current.append(ch)
                continue
            if ch in "([{":
                depth += 1
                current.append(ch)
                continue
            if ch in ")]" and depth > 0:
                depth -= 1
                current.append(ch)
                continue
            if ch == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(ch)
        if current:
            parts.append("".join(current).strip())
        return parts

    @staticmethod
    def parse_tool_call(response: str, tool_name: str) -> Optional[Dict[str, Any]]:
        marker = f"ACTION: {tool_name}("
        start = response.find(marker)
        if start == -1:
            return None
        start += len(marker)
        depth = 1
        end = start
        while end < len(response) and depth > 0:
            ch = response[end]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            end += 1
        args_str = response[start:end - 1]

        parts = FigmaAgent._split_args(args_str)
        args: Dict[str, Any] = {}
        for part in parts:
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            key = key.strip()
            value = value.strip()
            try:
                args[key] = ast.literal_eval(value)
            except Exception:
                args[key] = value
        return args if args else None

    @staticmethod
    def extract_code(response: str) -> Optional[str]:
        patterns = [
            r"```tsx\s*\n(.*?)\n```",
            r"```jsx\s*\n(.*?)\n```",
            r"```\s*\n(.*?)\n```",
        ]
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def save_raw_response(task: str, response: str) -> Path:
        output_dir = Path("agent_outputs")
        output_dir.mkdir(exist_ok=True)
        safe_task = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in task)[:60]
        filename = output_dir / f"{safe_task}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# Task\n\n{task}\n\n")
            f.write(f"# Response\n\n{response}\n")
        return filename

    def handle_tool_calls(self, response: str) -> bool:
        handled = False
        for tool_name, tool_fn in TOOLS.items():
            while True:
                args = self.parse_tool_call(response, tool_name)
                if not args:
                    break
                print(f"[TOOL] Executing {tool_name}({', '.join(args.keys())})")
                try:
                    result = tool_fn(**args)
                    print(f"[TOOL] {result}")
                    if tool_name == "WRITE_FILE" and result.startswith("SUCCESS"):
                        handled = True
                except Exception as e:
                    print(f"[TOOL ERROR] {tool_name} failed: {e}")
                marker = f"ACTION: {tool_name}("
                start = response.find(marker)
                end = response.find("\n", start)
                if end == -1:
                    end = len(response)
                response = response[:start] + response[end:]
        return handled

    def execute(
        self,
        task: str,
        context_data: str,
        output_name: Optional[str] = None,
        selected_node: Optional[Dict[str, Any]] = None,
    ):
        semantic_summary = _build_semantic_summary(selected_node) if selected_node else ""
        ai_response = self.call_llm(task, context_data, semantic_summary=semantic_summary)

        print("\n=== AI AGENT EXECUTION TRACE ===")
        print(ai_response)
        print("================================\n")

        log_path = self.save_raw_response(task, ai_response)
        print(f"[AGENT] Raw response saved to: {log_path}")

        write_file_executed = self.handle_tool_calls(ai_response)

        if write_file_executed:
            return

        # Fallback: если LLM не использовал WRITE_FILE, но выдал код в markdown-блоке.
        fallback_name = output_name
        if not fallback_name and selected_node:
            fallback_name = analyzer.infer_semantic_name(selected_node)

        if not fallback_name:
            print("[AGENT] No WRITE_FILE tool call and no output name available; component file creation skipped.")
            return

        code = self.extract_code(ai_response)
        if code:
            result = file_writer.write_component(fallback_name, code)
            print(f"[AGENT] {result}")
        else:
            print(
                f"[WARNING] Could not extract a code block from LLM response. "
                f"No component file was created for '{fallback_name}'. "
                f"Check the raw response at: {log_path}"
            )


def main():
    parser = argparse.ArgumentParser(description="Figma LLM Agent")
    parser.add_argument(
        "--task",
        default=None,
        help="Task to send to the LLM agent. Auto-generated from node name if omitted."
    )
    parser.add_argument(
        "--file",
        default="figma_node.json",
        help="Path to the Figma node JSON file"
    )
    parser.add_argument(
        "--node-id",
        default=os.environ.get("FIGMA_NODE_ID"),
        help="ID of a specific Figma node to analyze (e.g. 662:808)."
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="Component file name (without .tsx). Auto-derived from node name if omitted."
    )
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Do not download Figma images/vectors to public/images/."
    )
    parser.add_argument(
        "--spec",
        action="store_true",
        help="Generate a Markdown technical specification (spec.md) before/instead of component code."
    )
    args = parser.parse_args()

    agent = FigmaAgent()
    context, selected_node = agent.load_context(
        args.file,
        node_id=args.node_id,
        download_assets=not args.skip_assets,
    )

    output_name = args.output_name or analyzer.infer_semantic_name(selected_node)

    if args.spec:
        spec_path = spec_writer.generate_spec(selected_node, output_path="spec.md")
        print(f"[AGENT] Specification saved to: {spec_path}")
        return

    semantic_hint = _build_semantic_summary(selected_node)
    task = args.task or (
        f"Analyze the '{selected_node.get('name', 'selected')}' Figma section and create a React + Tailwind "
        f"component named '{output_name}'.\n"
        f"Use this semantic context when deciding structure and tags:\n{semantic_hint}"
    )

    print(f"[AGENT] Auto output name: {output_name}")

    agent.execute(
        task=task,
        context_data=context,
        output_name=output_name,
        selected_node=selected_node,
    )


if __name__ == "__main__":
    main()
