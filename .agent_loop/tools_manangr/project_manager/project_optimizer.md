# Project Optimizer

## Role
Optimizes the project for speed, size, and developer experience — build time reduction, dependency trimming, bundle size optimization, and workflow improvements. The continuous improvement engine.

## Contract
- **Receives**: `{ path: string, target: "build_time"|"bundle_size"|"dep_tree"|"dx"|"ci"|"full", baseline: Metrics, budget: { max_build_sec, max_bundle_mb } }`
- **Returns**: `{ optimizations: Optimization[], before: Metrics, after: Metrics, savings: { time_sec, size_mb, dep_count }, recommendations: string[] }`
- **Side effects**: may modify config files, lock files, and build scripts (with approval)

## Decision Flow

1. **Profile current state**
   - Build time: measure clean build, incremental build, hot reload time
   - Bundle size: per-chunk sizes, tree-shaking effectiveness, duplicate detection
   - Dependency tree: depth, breadth, duplicate versions, deprecated packages
   - Developer experience: lint time, test time, CI pipeline duration
   - Establish baseline metrics for before/after comparison

2. **Build time optimization**
   - Parallelization: increase parallel jobs, split into independent targets
   - Caching: enable compiler cache (ccache, esbuild cache, turbo cache)
   - Incremental builds: enable watch mode, skip unchanged modules
   - Toolchain selection: compare build tool performance (esbuild vs webpack, tsc vs swc)
   - Configuration tuning: disable unnecessary plugins, skip type checking in dev builds
   - Profile slowest build step, drill into why it's slow

3. **Bundle size optimization**
   - Tree-shaking audit: which unused exports survive into bundle?
   - Chunk splitting: extract vendor chunk, lazy-load routes, code-split heavy modules
   - Dependency analysis: find heavy dependencies, suggest lighter alternatives
   - Dead code elimination: code not reachable from any entry point
   - Asset optimization: image compression, font subsetting, SVG minification
   - Import style: `import { X } from 'lib'` vs `import X from 'lib/X'` (tree-shakable)

4. **Dependency tree optimization**
   - Deduplication: resolve multiple versions of same package to single version
   - Pruning: remove unused dependencies (verified via import analysis)
   - Hoisting: move shared deps higher in tree for flat resolution
   - Replacement: suggest lighter alternatives for heavy deps (moment → dayjs, lodash → native)
   - Version audit: update to latest compatible versions, apply security patches
   - `config_manager` audits and normalizes build configuration before toolchain changes
   - `task_planner` sequences optimization tasks so that build changes happen before bundle changes

5. **Developer experience optimization**
   - Lint time: enable lint caching, parallel linting, incremental lint
   - Test time: identify slow tests, suggest parallelization, mock expensive operations
   - CI pipeline: cache node_modules, parallelize jobs, skip unnecessary steps
   - Hot reload: reduce reload time by narrowing watch scope
   - `doc_generator` updates developer documentation when build or configuration changes affect workflow
   - Editor config: generate .vscode settings, extension recommendations

6. **Validate optimizations**
   - Benchmark before and after for each optimization
   - Verify: build output identical (same artifacts, same behavior)
   - Verify: all tests pass after optimization
   - Revert any optimization that breaks behavior or increases other metrics
   - Report: optimization name, what changed, measured improvement, confidence

## Failure Modes
| Condition | Response |
|---|---|
| Optimization breaks build | Revert that specific optimization, flag as incompatible, continue with rest |
| Savings below measurement noise | Report as negligible, don't apply — config churn isn't worth it |
| Toolchain incompatibility detected | Report version requirements, skip incompatible optimizations |
| Circular optimization (A improves build but worsens bundle) | Report trade-off, let user decide based on budget priorities |
| Lock file conflict during dep pruning | Resolve with regeneration, verify no unintended version changes |
