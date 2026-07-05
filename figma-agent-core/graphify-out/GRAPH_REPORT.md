# Graph Report - figma-agent-core  (2026-06-26)

## Corpus Check
- 33 files · ~47,533 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 908 nodes · 2115 edges · 33 communities (30 shown, 3 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 19 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9aede681`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]

## God Nodes (most connected - your core abstractions)
1. `FigmaLayoutEngine` - 39 edges
2. `run_pipeline()` - 28 edges
3. `TailwindNode` - 26 edges
4. `_run_command()` - 25 edges
5. `VisualQAEngine` - 23 edges
6. `compose_page()` - 21 edges
7. `SemanticIndex` - 20 edges
8. `SemanticMapper` - 18 edges
9. `build_content_model()` - 18 edges
10. `RegistryBuilder` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Any` --uses--> `SemanticIndex`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `Any` --uses--> `SemanticMatcher`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `Path` --uses--> `SemanticIndex`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `Path` --uses--> `SemanticMatcher`  [INFERRED]
  component_registry.py → semantic_matcher.py
- `ComponentRegistryError` --uses--> `SemanticIndex`  [INFERRED]
  component_registry.py → semantic_matcher.py

## Import Cycles
- None detected.

## Communities (33 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.10
Nodes (30): _arbitrary(), _class_for_color(), _color_to_hex(), convert_figma_node(), FigmaLayoutEngine, _has_alpha(), _has_image_fill(), _hex_to_rgba() (+22 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (20): ActionGenerator, BackendBridge, BackendSpec, Endpoint, main(), Model, ModelField, OpenApiParser (+12 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (59): CompletedProcess, _collect_top_level_sections(), main(), Any, Этап 1a: скачивание референсного скриншота Figma-фрейма через Images API., Этап 1b: построение реестра Figma-компонентов (Component Sets, Variants, Instanc, Этап 1d: обнаружение повторяющихся Figma-структур и предложение JSON/Prisma моде, Этап 1d-enrich: подбор изображений для data_model-карточек без картинок. (+51 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (10): ComponentRegistry, _is_component(), _is_component_set(), _is_instance(), Any, Path, Read every `*.mapper.json` in `mapper_dir` and index by `figma_component_id`., Return a new aggregate mapper where per-component files override aggregate entri (+2 more)

### Community 4 - "Community 4"
Cohesion: 0.10
Nodes (50): _apply_component_mappings(), _build_data_model_consts(), _build_form_hooks(), _build_handler(), _build_state_hooks(), _class_string(), _collect_all_nodes(), _collect_fonts() (+42 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (24): _asset_dest_path(), AssetDownloader, AssetExtractor, AssetOptimizer, AssetPipeline, _extract_box_size(), FontCollector, InlineSvgExtractor (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (31): _assign_component_names(), _class_string(), _collect_all_nodes(), _collect_substantial_nodes(), ComponentExtractor, ComponentGenerator, _detect_font_imports(), ExtractedComponent (+23 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (23): _build_semantic_summary(), _download_assets_for_context(), _extract_annotation_text(), FigmaAgent, _inject_asset_paths(), main(), _maybe_bootstrap(), Any (+15 more)

### Community 8 - "Community 8"
Cohesion: 0.18
Nodes (25): _build_match_index(), compose_responsive_ast(), constraint_to_classes(), detect_breakpoint_frames(), _diff_classes(), _find_figma_node(), _id_key(), _load_json() (+17 more)

### Community 9 - "Community 9"
Cohesion: 0.10
Nodes (22): DomAssertion, _expected_nodes_from_ast(), _extract_figma_fill_color(), _extract_figma_stroke_color(), _figma_color_to_hex(), _is_allowed_url(), main(), _parse_css_color() (+14 more)

### Community 10 - "Community 10"
Cohesion: 0.15
Nodes (19): cache_age_minutes(), check_figma_connection(), extract_effects(), extract_fills(), extract_text_style(), FigmaExtractor, find_node_by_id(), load_existing_cache() (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.11
Nodes (41): _apply_component_mappings(), _apply_slot(), _assign_prop_names(), build_content_model(), _build_content_model_json(), _build_data_code(), _build_page_code(), _class_string() (+33 more)

### Community 12 - "Community 12"
Cohesion: 0.21
Nodes (10): _box_area(), _boxes_overlap(), CheckResult, find_node_by_id(), load_figma_json(), main(), PreciseModeAuditor, _px() (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.24
Nodes (19): _apply_layout_adjustments(), _check_reason(), _extract_figma_id(), _find_node_by_figma_id(), _load_json(), _load_module(), main(), Any (+11 more)

### Community 14 - "Community 14"
Cohesion: 0.26
Nodes (16): check_file(), _check_import_path_safety(), _check_patterns(), _check_placeholders(), _check_project_rules(), ComplianceReport, _extract_text_literals(), _is_inside_workspace() (+8 more)

### Community 15 - "Community 15"
Cohesion: 0.27
Nodes (18): _attach_interactions(), _build_interaction(), _camel_case(), _collect_routes(), _extract_navigation_info(), _extract_overlay_info(), _extract_reaction_type(), _extract_url_info() (+10 more)

### Community 16 - "Community 16"
Cohesion: 0.25
Nodes (9): download_figma_reference(), FigmaReferenceDownloader, main(), _parse_file_key(), Any, Path, Скачивает референсный скриншот Figma-фрейма через Figma Images API., _resolve_image_url() (+1 more)

### Community 17 - "Community 17"
Cohesion: 0.30
Nodes (14): _build_page_tree(), _collect_assets(), _collect_components(), _collect_fills(), _collect_typography(), _collect_unique_values(), _extract_layout_rules(), generate_spec() (+6 more)

### Community 18 - "Community 18"
Cohesion: 0.17
Nodes (11): 1. Установка зависимостей, 2. Настройка окружения, 3. Запуск полного пайплайна, Figma Agent Core, Безопасность, Быстрый старт, Дизайн-токены и ассеты, Работа с конкретной секцией (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.50
Nodes (7): _ensure_dotenv(), FigmaConfig, is_figma_configured(), load_figma_config(), require_figma_config(), _resolve_file_key(), _resolve_node_id()

### Community 22 - "Community 22"
Cohesion: 0.09
Nodes (25): ABC, _build_provider(), _collect_image_refs(), DataModelEnricher, _extract_page_context(), _find_node_by_id(), ImageEnrichmentPipeline, ImageProvider (+17 more)

### Community 23 - "Community 23"
Cohesion: 0.20
Nodes (22): _collect_leaf_fields(), DataModelExtractor, extract_data_models(), _field_name_from_node(), _has_image_fill(), _is_image_node(), _is_text_node(), _is_visible() (+14 more)

### Community 24 - "Community 24"
Cohesion: 0.17
Nodes (22): _clean_name(), _extract_annotation_text(), find_node_by_id(), get_node_details(), infer_semantic_name(), inspect_node(), _is_generic_name(), list_top_level_nodes() (+14 more)

### Community 25 - "Community 25"
Cohesion: 0.14
Nodes (19): ComponentRegistryError, _extract_exports_and_props(), _extract_jsdoc_blocks(), _find(), _find_jsdoc_before(), InstanceEntry, _normalize_component_name(), _parse_jsdoc() (+11 more)

### Community 26 - "Community 26"
Cohesion: 0.23
Nodes (16): add_override(), apply_override(), _load_optional(), load_override_set(), MapperOverrideError, merge_overrides_into_mapper(), OverrideRule, OverrideSet (+8 more)

### Community 27 - "Community 27"
Cohesion: 0.18
Nodes (8): FigmaHTTPClient, Any, Response, Единый HTTP-клиент для Figma REST API с retry, backoff и rate-limit обработкой., Обертка над requests.Session для работы с Figma API.      Особенности:       - ц, Замедляет последовательные запросы, чтобы не провоцировать burst detection., Выполняет запрос с throttle и ручным retry по 429/Retry-After., Session

### Community 29 - "Community 29"
Cohesion: 0.22
Nodes (5): Any, Path, Return best matching existing component, score, and reason., Index existing design-system artifacts for semantic matching., SemanticIndex

### Community 30 - "Community 30"
Cohesion: 0.23
Nodes (12): collect_assets_from_tree(), download_asset(), get_image_urls_from_figma(), _load_asset_pipeline(), Path, Превращает имя ноды в безопасное имя файла., Скачивает ассет по URL и сохраняет в dest_path., Скачивает ассет и сохраняет его в public/images/.     Возвращает путь, который м (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.21
Nodes (8): ComponentMapper, _normalize_prop_name(), _normalize_prop_value(), Builds a Figma component key → React component + props mapper file., Convert an absolute file path to a project import path., Translate Figma instance variant properties to React props., Convert Figma variant property name to a React prop name (camelCase)., Normalize Figma variant value to a React prop string value.

### Community 32 - "Community 32"
Cohesion: 0.29
Nodes (8): _field_weight(), _jaccard(), _levenshtein_ratio(), _ngram_set(), _normalize_text(), Compute weighted semantic similarity between two feature dictionaries., _semantic_score(), _tokenize()

## Knowledge Gaps
- **16 isolated node(s):** `Response`, `CompletedProcess`, `Session`, `Path`, `Path` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_override_set()` connect `Community 26` to `Community 0`, `Community 25`, `Community 3`, `Community 28`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `merge_overrides_into_mapper()` connect `Community 26` to `Community 0`, `Community 25`, `Community 3`, `Community 28`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `SemanticIndex` connect `Community 29` to `Community 32`, `Community 3`, `Community 25`, `Community 28`, `Community 31`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Any` (e.g. with `SemanticIndex` and `SemanticMatcher`) actually correct?**
  _`Any` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Превращает произвольное имя Figma-ноды в валидное PascalCase-имя компонента.`, `Build a concise semantic summary from node metadata for the LLM prompt.`, `Если JSON-контекст отсутствует и есть токен с URL, автоматически запускает boots` to the rest of the system?**
  _158 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.09899396378269618 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07978142076502732 - nodes in this community are weakly interconnected._