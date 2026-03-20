# Compilation Baselines

This directory contains the five baseline compilation strategies evaluated in BuildBench. Each baseline attempts to compile C/C++ repositories from source inside Docker containers, and the results are validated using a function-level matching pipeline.

## Baselines

### 1. GHCC (GitHub C/C++ Compiler)
Located in `GHCC/`. A rule-based baseline that uses heuristics to detect build systems (Make, CMake, Autoconf, etc.) and runs standard build commands without any LLM involvement.

### 2. Assemblage
Located in `Assemblage/` with the driver in `assemblage.py`. Another rule-based baseline that follows a fixed sequence of build strategies based on detected build system files.

### 3. CompileAgent
Located in `CompileAgent/`. An LLM-based multi-agent system that uses tool-augmented agents (shell execution, web search, document navigation) to iteratively compile repositories. Includes multi-agent discussion for error resolution.

### 4. LLM Baseline (Single-Turn)
Implemented in `llm_baseline.py`. Sends repository metadata (name, README, file listing) to an LLM in a single prompt and executes the generated bash commands in a Docker container. Supports OpenAI, Anthropic, HuggingFace, and Gemini models.

### 5. LLM Multi-Turn
Implemented in `llm_multi_turn.py`. Extends the single-turn baseline with iterative refinement: when a command fails, the error output is fed back to the LLM for up to `MAX_TURN` (default 10) rounds. Optionally integrates Tavily web search for build instructions.

## Directory Structure

```
compilation_baselines/
  main.py                    # Unified entry point for all baselines
  compilation_base.py        # Abstract base class for all compilation strategies
  llm_baseline.py            # Single-turn LLM baseline
  llm_multi_turn.py          # Multi-turn LLM baseline with error feedback
  assemblage.py              # Assemblage baseline driver
  utils.py                   # Shared utilities (LLM clients, file helpers, search)
  tools.py                   # Docker management, logging, file operations
  validation_pipeline.py     # Function-level validation (source vs binary matching)
  validation_helper_functions.py  # DWARF/ELF parsing helpers
  validation_entry_point.py  # CLI entry point for validation
  validation_k8s.py          # Kubernetes job orchestrator for validation at scale
  job-template.yaml          # K8s job template for validation
  Dockerfile_compilation     # Docker image for compilation containers
  Dockerfile_validation      # Docker image for validation containers
  Dockerfile_ghcc_with_compilation  # GHCC-specific Docker setup
  GHCC/                      # GHCC baseline implementation
  Assemblage/                # Assemblage baseline implementation
  CompileAgent/              # CompileAgent multi-agent system
    Config.py                # Agent configuration and prompt templates
    CompileAgent.py          # Main agent executor
    clone_repo.py            # Repository cloning utility
    Tools.py                 # Agent tools (shell, search, navigation)
    MultiAgentDiscussion.py  # Multi-agent error resolution
    MultiAgentGetInstructions.py  # Instruction extraction agent
    GoogleSearch.py          # Web search integration
    Logs.py                  # Logging utilities
    Projects.json            # Project list for CompileAgent
    .env.example             # Environment variable template
```

## Running

### Prerequisites
- Docker installed and running
- Python 3.10+
- Required packages: `pip install openai docker tavily-python tqdm python-dotenv playwright pydantic`
- API keys set via environment variables (see `CompileAgent/.env.example` for reference)

### Compilation

Run from the repository root:

```bash
# Set required environment variables
export MODEL_NAME="claude-3-7-sonnet-20250219"
export API_KEY="your-api-key"
export ANTHROPIC_API_KEY="your-anthropic-key"

# Single-turn LLM baseline
python src/compilation_baselines/main.py --compilation_method llm_baseline

# Multi-turn LLM baseline
python src/compilation_baselines/main.py --compilation_method llm_multi_turn

# Multi-turn with internet search
python src/compilation_baselines/main.py --compilation_method llm_multi_turn --search_internet

# Assemblage baseline
python src/compilation_baselines/main.py --compilation_method assemblage

# Base (rule-based) baseline
python src/compilation_baselines/main.py --compilation_method base

# Parallel compilation (e.g., 4 repos at once)
python src/compilation_baselines/main.py --compilation_method llm_baseline --parallel_num 4
```

### Validation

```bash
# Run validation only on previously compiled repos
python src/compilation_baselines/main.py --validation_only

# Or run the validation pipeline directly
python src/compilation_baselines/validation_pipeline.py
```

## Class Hierarchy

```
compilation_base (compilation_base.py)
  Abstract base class providing:
  - Docker container lifecycle management
  - Repository cloning and directory setup
  - Logging infrastructure
  - Template method pattern via run() -> compile_in_container()

    +-- llm_baseline (llm_baseline.py)
    |     Single-turn LLM compilation
    |
    +-- llm_multi_turn (llm_multi_turn.py)
    |     Multi-turn LLM compilation with error feedback
    |
    +-- Assemblage (assemblage.py)
          Rule-based build system detection and execution
```

## Notes on Modifications

The following modifications were made to the original source files for public release:

- All hardcoded absolute paths have been replaced with relative paths computed from the repository root (`BASE_DIR`).
- API keys and credentials have been removed; initialization is now lazy and does not raise errors when keys are absent.
- The `CompileAgent/.env` file containing real API keys has been replaced with `.env.example` containing empty placeholders.
- Docker image references have been generalized (e.g., `compilation_base_image:latest` instead of registry-specific tags).
- Commented-out debugging code with hardcoded paths has been cleaned up.
