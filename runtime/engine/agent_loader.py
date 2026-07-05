from __future__ import annotations

import re
from pathlib import Path

from ..contracts.agent_spec import AgentSpec, ContractSpec, DecisionStep, FailureMode, Parameter


class AgentLoader:
    def __init__(self, agent_loop_root: Path):
        self.root = Path(agent_loop_root)
        if not self.root.exists():
            raise FileNotFoundError(f"Agent loop root not found: {self.root}")

    def load_agent(self, relative_path: str) -> AgentSpec:
        full_path = self.root / relative_path
        if not full_path.suffix:
            full_path = full_path.with_suffix(".md")
        if not full_path.exists():
            raise FileNotFoundError(f"Agent spec not found: {full_path}")
        content = full_path.read_text(encoding="utf-8")
        return self._parse(full_path, content)

    def load_all_agents(self) -> dict[str, AgentSpec]:
        agents: dict[str, AgentSpec] = {}
        for md_file in self.root.rglob("*.md"):
            if md_file.name == "ARCHITECTURE.md":
                continue
            try:
                spec = self.load_agent(str(md_file.relative_to(self.root)))
                key = str(md_file.relative_to(self.root)).replace("\\", "/")
                agents[key] = spec
            except Exception:
                continue
        return agents

    def _parse(self, path: Path, content: str) -> AgentSpec:
        name = self._extract_name(content)
        role = self._extract_section(content, "Role")
        contract = self._parse_contract(content)
        decision_flow = self._parse_decision_flow(content)
        failure_modes = self._parse_failure_modes(content)

        return AgentSpec(
            name=name,
            role=role,
            contract=contract,
            decision_flow=decision_flow,
            failure_modes=failure_modes,
            source_path=path,
        )

    def _extract_name(self, content: str) -> str:
        m = re.match(r"^#\s+(.+)", content.strip())
        return m.group(1).strip() if m else "Unknown"

    def _extract_section(self, content: str, heading: str) -> str:
        pattern = rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)"
        m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    def _parse_contract(self, content: str) -> ContractSpec:
        contract_block = self._extract_section(content, "Contract")
        receives = self._parse_params(contract_block, "Receives")
        returns = self._parse_params(contract_block, "Returns")
        side_effects = self._parse_list_items(contract_block, "Side Effects")
        return ContractSpec(receives=receives, returns=returns, side_effects=side_effects)

    def _parse_params(self, block: str, label: str) -> list[Parameter]:
        params: list[Parameter] = []
        section = self._extract_subsection(block, label)
        if not section:
            return params

        for line in section.split("\n"):
            line = line.strip()
            m = re.match(r"^- `(\w+)`:\s*(.+?)(?:\s*—\s*(.*))?$", line)
            if m:
                params.append(Parameter(
                    name=m.group(1),
                    type_hint=m.group(2).strip(),
                    description=m.group(3).strip() if m.group(3) else "",
                ))
        return params

    def _parse_list_items(self, block: str, label: str) -> list[str]:
        section = self._extract_subsection(block, label)
        if not section:
            return []
        items: list[str] = []
        for line in section.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:].strip())
        return items

    def _extract_subsection(self, block: str, heading: str) -> str:
        pattern = rf"^###\s+{re.escape(heading)}\s*\n(.*?)(?=^###\s|\Z)"
        m = re.search(pattern, block, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    def _parse_decision_flow(self, content: str) -> list[DecisionStep]:
        steps: list[DecisionStep] = []
        section = self._extract_section(content, "Decision Flow")
        if not section:
            return steps

        lines = section.split("\n")
        i = 0
        step_header_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*(?:\s*[—–-]\s*(.*))?$")

        while i < len(lines):
            line = lines[i].rstrip()
            m = step_header_pattern.match(line)
            if m:
                number = int(m.group(1))
                title = m.group(2).strip()
                desc_parts: list[str] = []
                if m.group(3):
                    desc_parts.append(m.group(3).strip())

                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip()
                    # Next top-level step stops collection
                    if step_header_pattern.match(next_line):
                        break
                    # New top-level section stops collection
                    if re.match(r"^##\s", next_line):
                        break
                    # Failure Modes table header stops collection
                    if "| Condition" in next_line and next_line.strip().startswith("|"):
                        break
                    # Skip leading empty lines before body starts
                    if not desc_parts and not next_line.strip():
                        i += 1
                        continue
                    # Collect body line, fully stripped
                    stripped = next_line.strip()
                    if stripped:
                        desc_parts.append(stripped)
                    i += 1

                description = " ".join(desc_parts) if desc_parts else ""
                steps.append(DecisionStep(
                    number=number, title=title, description=description
                ))
                continue
            i += 1

        return steps

    def _parse_failure_modes(self, content: str) -> list[FailureMode]:
        modes: list[FailureMode] = []
        section = self._extract_section(content, "Failure Modes")
        if not section:
            return modes

        lines = section.split("\n")
        in_table = False
        for line in lines:
            line = line.strip()
            if line.startswith("|") and "Condition" in line:
                in_table = True
                continue
            if in_table and line.startswith("|---"):
                continue
            if in_table and line.startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    modes.append(FailureMode(condition=parts[0], response=parts[1]))
            elif in_table and not line.startswith("|"):
                break
        return modes
