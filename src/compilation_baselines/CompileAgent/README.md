# 🤖CompileAgent: Automated Real-World Repo-Level Compilation with Tool-Integrated LLM-based Agent System

<div align="center">
<p> 
<!--   <a href="https://arxiv.org/pdf/2505.04254"><img src="https://img.shields.io/badge/🙏-Arxiv-red" height="20px"></a> -->
  <a href="https://arxiv.org/abs/2505.04254"><img src="https://img.shields.io/badge/arXiv-2505.04254-b31b1b.svg" alt="arXiv"></a>
  <a href="https://ch3nye.top/AutoCompiler"><img src="https://img.shields.io/badge/📝-BlogPost-blue" height="20px"></a>
  <a href=""><img src="https://img.shields.io/badge/😊-ACL'25-purple" height="20px"></a>
</p> 
</div>


## 📙About

CompileAgent is a LLM-driven framework designed to automatically compile projects directly from their source code repositories. In our [post](https://ch3nye.top/AutoCompiler), we go beyond the scope of the paper by presenting extended experiments that highlight the application of CompileAgent across various downstream tasks.

## ✒️Workflow

<p align="center"><img src="./imgs/workflow.png" alt="workflow" style="width:100%;"></p>
<!-- <p align="center">Figure 1: The workflow of CompileAgent.</p> -->

- ***Step1:*** Specify the URL of the project to be compiled.
- ***Step2:*** Extracting Compilation Instructions. Specifically, the MasterAgent calls the CompileNavigator module to obtain the project's compilation instructions. It first uses the Shell and File Navigator tools to locate relevant files, and then extracts the instructions using the Instruction Extractor tool.
- ***Step3:*** Execute the Compilation Commands. If the compilation succeeds, proceed directly to Step5; if it fails, the ErrorSovler module will be invoked to perform error correction.
- ***Step4:*** Resolving Compilation Errors. For simple compilation errors, the MasterAgent handles them directly. For more complex or challenging issues, the MasterAgent invokes Multi-Agent Discussion to find solutions. During the process, if new errors are encountered, Google Search may be used to retrieve potential solutions.
- ***Step5:*** Display the result of the compilation: success or failure.

More details can be found in our [paper](https://arxiv.org/pdf/2505.04254).


## 🚀Environment Setup
```python
conda create -n CompileAgent python=3.9.0
conda activate CompileAgent
pip install -r requirements.txt
```

Building the compilation environment:
```
docker build -t autocompiler:gcc13 .
```
**NOTE:** The Dockerfile can be modified to build a compilation environment tailored to your needs.

## 🔥Quick Start
The Dataset directory includes three publicly compilable repositories that you can use for testing compilation.

`python CompileAgent.py --help`
```shell
Usage: CompileAgent.py [OPTIONS]

Compile the projects from source code with the help of AI assistant

Options:
  -j, --json_path TEXT the path to the project file to be compiled [required]
  -p, --dataset_base_path TEXT the base path to store the projects need to compile [required]
  -l, --log_path TEXT the path to store the logs of compilation [required]
  -c, --clean_copied_project BOOLEAN whether to clear the new project path after the compilation, set to True when debugging [required]
  -r, --retry INTEGER the times to retry when fail to pass checker
  -s, --strict_checker BOOLEAN if True, only return True when all target files are in the file list, otherwise return True when any target file is in the file list
  --download_proxy TEXT pass to git --config http.proxy=${}, e.g., socks5://127.0.0.1:29999, if do not set: do not use proxy
  --multi_process BOOLEAN whether to enable the multi-process to compile the projects
  --help Show this message and exit.
```
python3 CompileAgent.py -j /path/to/Dataset/test_data/debug_repo.json -p /path/to/cloned_repos -l /path/to/logs -c False --multi_process True
**NOTE:** Please configure the required LLMs api in `Config.py` before execting the `CompileAgent.py` file.

## 📜Citation
```
@misc{hu2025compileagentautomatedrealworldrepolevel,
  title={CompileAgent: Automated Real-World Repo-Level Compilation with Tool-Integrated LLM-based Agent System}, 
  author={Li Hu and Guoqiang Chen and Xiuwei Shang and Shaoyin Cheng and Benlong Wu and Gangyang Li and Xu Zhu and Weiming Zhang and Nenghai Yu},
  year={2025},
  eprint={2505.04254},
  archivePrefix={arXiv},
  primaryClass={cs.SE},
  url={https://arxiv.org/abs/2505.04254}, 
}
```
