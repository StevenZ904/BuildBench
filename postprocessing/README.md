# Post-Processing Pipeline

This directory contains scripts for analyzing and validating compilation results produced by the BuildBench system.

## Scripts

- **`postprocessing.py`** — Main orchestration script that runs the full post-processing pipeline on compiled repositories
- **`binary_info.py`** — Extracts function and symbol information from compiled ELF binaries using pyelftools and DWARF debug info
- **`variable_info.py`** — Extracts variable information from compiled binaries for validation
- **`utils.py`** — Shared utility functions used across the pipeline
- **`count_files.py`** — Classifies and counts source files in repositories (C, C++, headers, etc.)
- **`count_result_file.py`** — Aggregates and reports compilation result statistics

## Usage

```bash
# Run post-processing on compiled results
python postprocessing.py --results_dir <path_to_compiled_results>
```

## Pipeline Flow

1. **Binary Analysis**: Extract function/symbol info from compiled ELF binaries (`binary_info.py`)
2. **Variable Extraction**: Extract variable information for deeper validation (`variable_info.py`)
3. **File Counting**: Classify and count source files per repository (`count_files.py`)
4. **Result Aggregation**: Summarize results across all repositories (`count_result_file.py`)
