# Reproducing BuildBench Experiments

This guide walks through reproducing all experiments from the BuildBench paper, including OSS-BUILD-AGENT (Table 1, multi-agent rows) and all baselines (GHCC, Assemblage, CompileAgent, LLM Baseline).

## Prerequisites

- **Hardware**: Linux server with Docker installed (tested on Ubuntu 22.04)
- **Python**: 3.10+
- **Docker**: 20.10+ (with `docker` accessible to the current user)
- **Disk**: ~50 GB for Docker images + compiled repos
- **API Keys**: At least one of OpenAI, Anthropic, Google, or HuggingFace API keys

## 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/StevenZ904/BuildBench.git
cd BuildBench

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Verify installation

```bash
# All imports should succeed without errors
python3 -c "
import sys; sys.path.insert(0, 'src')
import agents, prompts, bash_executor, build_info_retrieval
import compilation, tools, default_values, validation_pipeline
print('All OSS-BUILD-AGENT modules imported successfully')
"

python3 -c "
import sys; sys.path.insert(0, 'src/compilation_baselines')
import compilation_base, assemblage, llm_baseline, llm_multi_turn
import tools, utils, validation_pipeline
print('All baseline modules imported successfully')
"
```

## 2. Build Docker Images

All compilation happens inside Docker containers (Ubuntu 22.04 with gcc, cmake, make, etc.).

```bash
# Build the main compilation image (used by OSS-BUILD-AGENT and baselines)
sudo docker build -t docker_image_compilation -f src/Dockerfile_compilation .

# (Optional) Build the K8S worker image if using Kubernetes
sudo docker build -t docker_image_compilation_k8s -f src/Dockerfile_k8s .

# Verify the image
docker run --rm docker_image_compilation bash -c "gcc --version | head -1 && cmake --version | head -1"
```

Expected output:
```
gcc (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0
cmake version 3.22.1
```

## 3. Download Data

The benchmark data files should already be in `data/`. If not:

```bash
pip install huggingface_hub

python3 -c "
from huggingface_hub import hf_hub_download
for f in [
    'Compilation_Bench_Validation_Set_70.csv',
    'sampled_repos_385_cleaned_higher_split.jsonl',
    'sampled_repos_149_cleaned_higher_split_compilable.jsonl',
    'compilation_label.json',
    'test_set_build_trajectories.csv',
]:
    hf_hub_download(repo_id='STEVENZHANG904/Build_Bench_Validation_Data',
                    filename=f, repo_type='dataset', local_dir='data/')
"
```

### Verify data

```bash
python3 -c "
import json, csv
repos_385 = [json.loads(l) for l in open('data/sampled_repos_385_cleaned_higher_split.jsonl')]
repos_149 = [json.loads(l) for l in open('data/sampled_repos_149_cleaned_higher_split_compilable.jsonl')]
labels = json.load(open('data/compilation_label.json'))
compilable = {k: v for k, v in labels.items() if v}
print(f'385-repo set: {len(repos_385)} repos')
print(f'149-repo compilable set: {len(repos_149)} repos')
print(f'Ground truth labels: {len(compilable)} repos with expected binaries')
"
```

Expected:
```
385-repo set: 385 repos
149-repo compilable set: 149 repos
Ground truth labels: 149 repos with expected binaries
```

## 4. Running OSS-BUILD-AGENT (Table 1, Multi-Agent Rows)

### 4.1 Single Repository

```bash
# Replace $API_KEY with your actual API key
python3 src/main.py \
  --api_key=$API_KEY \
  --model_name=claude-3-7-sonnet-20250219 \
  --github_repo=https://github.com/taviso/ctypes.sh.git \
  --random=-1 \
  --host_project_dir=$(pwd) \
  --retrieval
```

This will:
1. Clone the repo into a Docker container
2. Use the LLM-Assisted Retrieval module to find build instructions
3. Run the multi-agent compilation loop (Bash Command Generator + Executor)
4. Save compiled output to `compiled_repos/`

### 4.2 Full Benchmark (149 Compilable Repos)

```bash
# Without retrieval (Table 1: "OSS-BUILD-AGENT w/o Retrieval")
python3 src/main.py \
  --api_key=$API_KEY \
  --model_name=claude-3-7-sonnet-20250219 \
  --host_project_dir=$(pwd) \
  --data_path=data/sampled_repos_149_cleaned_higher_split_compilable.jsonl

# With LLM-Assisted Retrieval (Table 1: "OSS-BUILD-AGENT w/ LLM-Assisted Retrieval")
python3 src/main.py \
  --api_key=$API_KEY \
  --model_name=claude-3-7-sonnet-20250219 \
  --host_project_dir=$(pwd) \
  --data_path=data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --retrieval

# With Perfect Retrieval (Table 3: "Perfect Retrieval" row)
python3 src/main.py \
  --api_key=$API_KEY \
  --model_name=claude-3-7-sonnet-20250219 \
  --host_project_dir=$(pwd) \
  --data_path=data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --retrieval --perfect_retrieval

# With RAG Retrieval (Table 3: "RAG" row)
python3 src/main.py \
  --api_key=$API_KEY \
  --model_name=claude-3-7-sonnet-20250219 \
  --host_project_dir=$(pwd) \
  --data_path=data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --retrieval --RAG_retrieval
```

### 4.3 Other LLM Models (Table 1)

Replace `--model_name` and `--api_key` for each provider:

| Model | `--model_name` | API Key Source |
|-------|---------------|---------------|
| GPT-4o | `gpt-4o` | OpenAI |
| o3-mini | `o3-mini` | OpenAI |
| Claude 3.7-Sonnet | `claude-3-7-sonnet-20250219` | Anthropic |
| Gemini 2.5-flash | `gemini-2.5-flash` | Google |
| Qwen3 235B | `Qwen/Qwen3-235B-A22B-Instruct-2507:together` | Together AI |
| Qwen3 Coder 480B | `Qwen/Qwen3-Coder-480B-A35B-Instruct:novita` | Novita AI |

## 5. Running Baselines (Table 1, Baseline Rows)

### 5.1 Assemblage (Rule-Based)

```bash
cd src/compilation_baselines

python3 main.py \
  --compilation_method assemblage \
  --input_file_path ../../data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --container_image docker_image_compilation:latest \
  --parallel_num 4

cd ../..
```

### 5.2 LLM Baseline — Single Turn (Table 1, "LLM Baseline" rows)

```bash
cd src/compilation_baselines

# o3-mini
API_KEY=$OPENAI_KEY MODEL_NAME=o3-mini python3 main.py \
  --compilation_method llm_baseline \
  --input_file_path ../../data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --container_image docker_image_compilation:latest

# Claude 3.7-Sonnet
API_KEY=$ANTHROPIC_KEY MODEL_NAME=claude-3-7-sonnet-20250219 python3 main.py \
  --compilation_method llm_baseline \
  --input_file_path ../../data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --container_image docker_image_compilation:latest

cd ../..
```

### 5.3 LLM Multi-Turn Baseline

```bash
cd src/compilation_baselines

ANTHROPIC_API_KEY=$ANTHROPIC_KEY MODEL_NAME=claude-3-7-sonnet-20250219 python3 main.py \
  --compilation_method llm_multi_turn \
  --input_file_path ../../data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --container_image docker_image_compilation:latest

cd ../..
```

### 5.4 GHCC (Rule-Based)

```bash
cd src/compilation_baselines/GHCC/ghcc

# Build the GHCC Docker image
docker build -t ghcc-image -f Dockerfile .

# Run GHCC on the benchmark
python3 main.py \
  --repo-list-file ../../../../data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --clone-folder ./cloned_repos \
  --binary-folder ./binary_repos \
  --archive-folder ./archive_folder \
  --n-procs 10

cd ../../../..
```

### 5.5 CompileAgent (Multi-Agent Baseline)

```bash
cd src/compilation_baselines/CompileAgent

# Copy .env.example and fill in your API keys
cp .env.example .env
# Edit .env with your API keys

python3 CompileAgent.py \
  -j Dataset/test_data/sampled_repos_385_higher_split.json \
  -p ./cloned_repos \
  -l ./logs \
  -c False \
  --multi_process True

cd ../../..
```

## 6. Evaluation (Table 1 Metrics)

After any compilation run, evaluate the results:

### 6.1 Strict/Flexible Success (Validated Metrics)

```bash
python3 postprocessing/evaluate_success.py \
  --ground_truth data/compilation_label.json \
  --compiled_dir compiled_repos/ \
  --output compiled_results/evaluation.json
```

Expected output format:
```
Total repos: 149
Completion:       XX (XX.X%)
Strict Success:   XX (XX.X%)
Flexible Success: XX (XX.X%)
```

### 6.2 Postprocessing Analysis

```bash
python3 postprocessing/postprocessing.py \
  --compiled_dir compiled_repos/ \
  --results_dir compiled_results/
```

### 6.3 Reference Results (Table 1)

| Build Method | Completions % | Strict % | Flexible % |
|-------------|:---:|:---:|:---:|
| GHCC | 30.2 | 10.1 | 13.4 |
| Assemblage | 10.7 | 6.0 | 9.4 |
| CompileAgent (GPT-4o) | N/A | 50.7 | 56.8 |
| OSS-BUILD-AGENT w/ Retrieval (Claude 3.7) | **85.2** | **67.6** | **73.0** |

## 7. Retrieval Evaluation (Table 4)

```bash
# The retrieval module logs which URLs it accessed.
# Compare against ground truth:
python3 -c "
import csv

gt = {}
with open('data/test_set_build_trajectories.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row.get('Repo_Name')
        urls = row.get('Build Trajectory', '')
        if urls and urls.strip():
            gt[name] = [u.strip() for u in urls.split(',') if u.strip()]

print(f'{len(gt)} repos with ground truth retrieval labels')
"
```

## 8. Kubernetes Batch Execution (Optional)

For running all 149 repos in parallel on a K8S cluster:

```bash
# Build and push the K8S image
docker build -t your-registry/buildbench-k8s:latest -f src/Dockerfile_k8s .
docker push your-registry/buildbench-k8s:latest

# Launch K8S jobs
python3 orchestrator.py \
  --api_key=$API_KEY \
  --model_name=claude-3-7-sonnet-20250219 \
  --docker_image=your-registry/buildbench-k8s:latest \
  --k8s_parallelism=50 \
  --data_path=data/sampled_repos_149_cleaned_higher_split_compilable.jsonl \
  --retrieval \
  --host_project_dir=$(pwd)
```

## Environment Variables Reference

| Variable | Required | Description |
|----------|:---:|-------------|
| `API_KEY` | Yes | LLM provider API key (for OSS-BUILD-AGENT) |
| `MODEL_NAME` | Yes | Model identifier (see table in Section 4.3) |
| `ANTHROPIC_API_KEY` | For baselines | Anthropic key (for baseline multi-turn) |
| `OPENAI_KEY` | For baselines | OpenAI key (for baseline LLM methods) |
| `TAVILY_API_KEY` | Optional | Tavily key for web search in multi-turn baseline |
| `TIMEOUT_BASH` | No | Command timeout in seconds (default: 300) |
| `MAX_TURNS` | No | Max agent conversation turns (default: 10) |
| `CORES` | No | CPU cores for parallel compilation |

## Troubleshooting

**Docker permission denied**: Run `sudo usermod -aG docker $USER` and re-login.

**Import errors**: Ensure you activated the venv (`source .venv/bin/activate`) and installed all deps (`pip install -r requirements.txt`).

**pyautogen version conflicts**: The code requires `pyautogen>=0.3.1,<0.4`. Newer versions changed the import structure. Pin with: `pip install 'pyautogen>=0.3.1,<0.4'`.

**pyjoern slow first run**: pyjoern downloads ~1.8 GB of Joern binaries on first import. This is expected.

**Rate limits**: When running many repos, you may hit LLM provider rate limits. Use `--starting_index` and `--ending_index` to run in batches, or reduce parallelism.
