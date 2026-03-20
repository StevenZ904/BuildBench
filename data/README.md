# BuildBench Data

## Validation Dataset

The file `Compilation_Bench_Validation_Set_70.csv` contains 70 repositories used for validation, sourced from [HuggingFace](https://huggingface.co/datasets/STEVENZHANG904/Build_Bench_Validation_Data).

### Schema

| Column | Description |
|--------|-------------|
| `Repo_Name` | Repository name |
| `Github_Url` | GitHub URL |
| `Github_Stars` | Star count at time of collection |
| `Compilable?` | Whether the repository is compilable (Yes/No) |
| `build_instruction_trajectory` | Comma-separated list of URLs forming the build instruction trajectory |
| `Build Instructions in Readme?` | Whether build instructions are in the README |
| `License` | Repository license |
| `build_instruction_trajectory_json` | JSON-structured build instruction trajectory with steps |

## Benchmark Repository Lists

### JSONL Files

The benchmark datasets are JSONL files with the following schema:

```json
{"name": "repo", "full_name": "owner/repo", "html_url": "https://github.com/owner/repo", "stargazers_count": 79, "size": 6263, "language": "C", "description": "...", "created_at": "...", "pushed_at": "...", "default_branch": "master", "license": "MIT"}
```

| File | Repos | Description |
|------|-------|-------------|
| `sampled_repos_385_cleaned_higher_split.jsonl` | 385 | Full benchmark set (all sampled repos) |
| `sampled_repos_149_cleaned_higher_split_compilable.jsonl` | 149 | Compilable subset (test set) |

### Ground Truth Labels

| File | Description |
|------|-------------|
| `compilation_label.json` | Expert-labeled expected binary file names per repo (149 compilable repos have entries, 236 have empty lists) |
| `test_set_build_trajectories.csv` | Ground-truth build instruction URLs for retrieval evaluation (136 repos with clear labels) |

## Download Instructions

All datasets are also available on [HuggingFace](https://huggingface.co/datasets/STEVENZHANG904/Build_Bench_Validation_Data):

```bash
pip install huggingface_hub

from huggingface_hub import hf_hub_download

for filename in [
    "Compilation_Bench_Validation_Set_70.csv",
    "sampled_repos_385_cleaned_higher_split.jsonl",
    "sampled_repos_149_cleaned_higher_split_compilable.jsonl",
    "compilation_label.json",
    "test_set_build_trajectories.csv",
]:
    hf_hub_download(
        repo_id="STEVENZHANG904/Build_Bench_Validation_Data",
        filename=filename,
        repo_type="dataset",
        local_dir="data/"
    )
```
