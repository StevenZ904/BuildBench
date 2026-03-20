import asyncio
from build_info_retrieval import retrive_env_setup_info, list_files, get_html_content_in_markdown
from default_values import DEFAULT_VALUES
import os
import re

class Prompts:
    def __init__(self, github_repo, clone_dir, sudo_password, compiled_save_path = None, detailed_compilation_instructions_link = None, cores = 12, refine_times = 1, model_name = 'o3-mini', heuristic_refine=True, perfect_retrieval=False, RAG_retrieval=False):
        self.github_repo = github_repo
        self.clone_dir = clone_dir
        # self.compiled_save_path = compiled_save_path
        self.sudo_password = sudo_password
        self.cores = cores
        
        self.heuristic_refine = heuristic_refine
        self.perfect_retrieval = perfect_retrieval 
        self.rag_retrieval = RAG_retrieval
        self.refine_times = refine_times
        
        self.build_tools_dict, self.readme_content, self.readme_path, self.detailed_compilation_instructions, self.link_dict = retrive_env_setup_info(self.clone_dir, self.refine_times, refine=self.heuristic_refine)
        
        self.repo_name = self.github_repo.split('/')[-1].replace('.git', '')

        ### Use pre-defined ground truth compilation instructions if provided
        if self.perfect_retrieval:
            perfect_retrieval_url = DEFAULT_VALUES["PERFECT_RETRIEVAL_DICT"].get(self.repo_name, None)
            if perfect_retrieval_url:
                
                readme_pattern = r'/blob/[^/]+/README\.(md|rst|txt|markdown)$'
                
                if re.search(readme_pattern, perfect_retrieval_url, re.IGNORECASE):
                    print(f"Skipping perfect retrieval for {self.repo_name}: URL points to the main README ({perfect_retrieval_url}), which has been included in the prompts.")
                    self.detailed_compilation_instructions = ""
                else:    
                    print(f"Using perfect retrieval URL for {self.repo_name}: {perfect_retrieval_url}")
                    self.detailed_compilation_instructions = asyncio.run(get_html_content_in_markdown(perfect_retrieval_url))
            else:
                print(f"No perfect retrieval URL found for {self.repo_name}")
                self.detailed_compilation_instructions = ""

        if self.rag_retrieval:
            RAG_retrieved_docs = DEFAULT_VALUES['RAG_build_instructions'].get(self.repo_name, None)
            if RAG_retrieved_docs:
                print(f"Using RAG retrieval documents for {self.repo_name}.")
                self.detailed_compilation_instructions = RAG_retrieved_docs
            else:
                print(f"No RAG retrieval documents found for {self.repo_name}.")
                self.detailed_compilation_instructions = ""
            
        self.model_name = model_name

    def _detailed_instructions(self):
        instructions = (

            f'The current working directory and absolute path is "/app", and the repo is located at {self.clone_dir}; do not generate any placeholder path in your commands.\n'
            'The user can\'t modify your code. So do not suggest incomplete code which requires users to modify. '
            f'The compilation process is running within a Docker Container, and you already have the root access, so do not run sudo.\n'
            # 'Don\'t give remove commands (rm -rf) in your code.\n'
            f'Always use absolute paths in your commands. For example, use ls {self.clone_dir} instead of ls\n\n'
            # 'It may be a good idea that if you give at most 5 commands at a time to avoid execution timeout errors.\n'
            'The user cannot provide any other feedback or perform any other action beyond executing the code you suggest. The user can\'t modify your code. So do not suggest incomplete code which requires users to modify. '
            'Make sure to compile the target repository with debug information, and do not strip debug information after the compilation is finished;'
            'for example, adding "-g O0" to cppflag and cxxflag .\n'
            f'It is important to add a prefix or DESTDIR flag to the make command to save the compiled artifacts in the directory {self.clone_dir}, whenever possible.\n'
            f'Always execute "make install" and no "make check" after the compilation is finished to ensure the compiled artifacts are saved in the correct directory. But there is no need to run "make test". Meanwhile, feel free use no more than {self.cores} cores to speed up compilation\n'
            f'A more detailed instruction of building from source, which is retrieved from the repository, will be provided later, do your best to comply with the instructions.\n' 
            ### TODO: Wait for Autogen to fix the bug https://github.com/microsoft/autogen/issues/1587
            # "You can use the validation_pipeline tool to validate the compilation process. This tool provides a percentage indicating how many functions extracted from the binary files correspond to the source code. If the percentage is too low or null, follow these steps: 1. Remove the compiled_repo and copy a fresh repository using the remove_and_copy_directory function. 2. Analyze the validation results, adjust your previously generated commands accordingly, and retry the compilation process. Do not repeat this workflow more than once.\n"
            
            f'For any error happened during the process, you should try to fix it. You can terminate the process if you find the task is successful or impossible by sending a message with the word "terminate". But before termination, address the reason of termination, for example, "critical dependencies missing" or "This repo can only be compiled or used on IOS devices". Note that including terminate in your output would result in pre-mature termination. Do not include the word "terminate" in your output along with code blocks, as it would result in pre-mature termination. \n',
            f'\n\nDo not show appreciation in your responses, say only what is necessary. If "Thank you" or "You\'re welcome" are said in the conversation, then say TERMINATE to indicate the conversation is finished and this is your last message.'
        )
        instructions = "".join(instructions)  # Convert tuple to a single string

        # if 'o3-mini' in self.model_name or 'o4-mini' in self.model_name:
        instructions += f"""When generating bash commands. Make sure to wrap up the code blocks following the format of this example:
            ```bash
            # Comments explaining the purpose of the commands
            commands
            ```
            """
            
        return instructions
    
    def compilation_bash_command_generator_system_message(self):
        return(
            f'You are an helpful AI assistant that is an expert in compiling cloned GitHub repositories and handling compilation errors during the process by generating bash commands.\n'
            # f'Note there is no need to install the compiled binaries. You are only responsible for generating the bash commands for compilation.\n'
            # f'You are responsible to ensure that you will save the compiled artifacts in the directory {self.compiled_save_path}. You may modify the compilation commands from instructions to achieve this goal, if necessary. Sometimes, it may be useful to pass on flags like CFLAGS or LDFLAGS using "make LDFLAGS="-o (savepath)". You should check if the compiled artifacts are saved, and if so, terminate.\n'            
            f'{self._detailed_instructions()}'

        )
        
        
    def executor_system_message(self):
        return f'You are an AI assistant that can run bash commands or execute function calling and conduct the process of Github repository compilation. \n'


    def retriever_system_message(self):
        return (
            f'''You are an AI assistant whose sole task is to locate and extract precise “build from source” instructions for any open-source repository targeting Ubuntu. To do this reliably across very different projects, follow this ordered strategy:

            1. **Local inspection**  
            a. Read through the content of `README.md` (or README.rst, etc.) in full.  
            b. If you see local files named `INSTALL.md`, `BUILD.md`, `docs/`, or similar, read those next.  
            c. Search within those files for keywords like “build”, “install”, “cmake”, “configure”, “make”, etc., and extract any relevant instructions.

            2. **Learn from inbound links**  
            a. In the README or docs, collect *any* URLs that look like official docs (URLs containing “docs”, “installation”, “catboost.ai/docs”, etc.).  
            b. Fetch those URLs and scan them for Ubuntu-specific build or installation instructions.

            3. **Fallback web search**  
            If neither local files nor linked URLs contain clear build steps, perform a web search with a query of the form: ' build from source ubuntu' 
            
            —then fetch and parse the top result that appears to be an official guide or installation page.

            4. **Tool usage**  
            You may call and only call the Execution agent to use the following tools.
            - Use **read_file(path)** to open and read local files(which may needs to be validated based on the absolute path of the README file {self.readme_path}).  
            - Use **list_files(path)** to list all files in a directory.  
            - Use **search_online_using_tavily(query)** to run a search from Internet when needed.  
            - Use **get_html_content_in_markdown(url)** to read contents from a external url in Markdown format.

            Retrieval is considered as finished only if you’ve assembled a complete, step-by-step Ubuntu build procedure (including dependencies, configuration flags, commands, and any prerequisites) or the build instructions are determined non-existent. If you encounter multiple valid methods (e.g. binary vs. source), default to *source* and note any alternatives at the end. You should then send the instructions to the Bash_Command_Generator agent for compilation.
            
            Please save the retrieved instructions (or 'Build instructions cannot be found.' if you cannot find them) in a txt file at '/app/retrieved_instructions.txt'. Invoke the Execution agent with bash commands.When generating bash commands. Make sure to wrap up the code blocks following the format of this example:
            ```bash
            echo {{retrieved_instructions}} > /app/retrieved_instructions.txt
            ```

            
            Do not show appreciation in your responses, say only what is necessary. If "Thank you" or "You\'re welcome" are said in the conversation, then say TERMINATE to indicate the conversation is finished and this is your last message.'
            '''
        )
    
    
    def manager_system_message(self):
        return (f'You are an AI assistant that orchestrates building {self.github_repo} from source on Ubuntu. '
                
        f"Follow these steps in strict order:\n"
            f"1. Call the Build_Instructions_Retriever agent to find the necessary build-from-source instructions for the task.\n"
            f"2. Only after confirming that the Build_Instructions_Retriever agent has found the required information, pass it to the Bash_Command_Generator agent.\n"
            f"3. The Bash_Command_Generator agent should then generate the appropriate bash commands for compilation based on the retrieved instructions.\n"
            f"Do not skip or reorder any steps. Each step depends on the successful completion of the previous one.\n"
            'Finally, if you determinet that the compilation is finished successfully, say TERMINATE.\n'
        )
    
    # def initial_message_installation(self):

    #     return (
    #         f'I have cloned the GitHub repository, {self.github_repo} at {self.clone_dir}.\n'
    #         # f'The repository contains the following files:\n{list_files(self.docker_repo_path)}\n'
    #         f"How do I properly install all the dependencies and configure the environment to prepare for building this repository from source on Linux? Give me the only the commands along with a comments that explain them. Do not include examples."
    #         )
    
    def initial_message_retriever(self):
        return (

            f'I have cloned the GitHub repository, {self.github_repo}, and the absolute path to the cloned repository is {self.clone_dir}.\n'
            f'The repository contains the following files:\n{list_files(self.clone_dir)}\n'
            f'Please help me find the build instructions for this repository by starting off from the README. For the internal file path that may contain the build instructions, validate the path based on the absolute path and access the file content. For urls, you can accessing content of them. Finally, feel free to search the internet for the build instructions. Note that sometimes the build instructions may require you explore for a few times to find them.\n'
            f'The README content is as follows:\n{self.readme_content}\n'
            f'The README file is located at {self.readme_path}.\n'
        )
    
    def initial_message_compilation(self):
        # if len(self.build_tools_dict) == 0:
        #     build_tools_list = 'None'
        # elif len(self.build_tools_dict) == 1:
        #     build_tools_list = self.build_tools_dict.values()
        # else:
        #     build_tools_list = ', '.join(list(self.build_tools_dict.values()))

        return (
            f'I have cloned the GitHub repository, {self.github_repo}, and the absolute path to the cloned repository is {self.clone_dir}.\n'
            f'The repository contains the following files:\n{list_files(self.clone_dir)}\n'
            f"How do I compile the github repository on Linux? You may look for compilation resources if availble in the file directories as listed above or within each files via bash commands. Give me the only the commands along with a comments that explain them. Do not include examples."
            # f'The destination directory for the compiled files should be {self.compiled_save_path}.\n'
            f'There may be certain files in the directory that contains useful information about setting up the environments, such as {self.build_tools_dict.values()}.\n'
            f'The README content is as follows:\n{self.readme_content}\n'
            f'Detailed instructions of building from source are as follows:{self.detailed_compilation_instructions}.\n\n')
    
    def initial_message_manager(self):
        return (
            f'I have cloned the GitHub repository, {self.github_repo}, and the absolute path to the cloned repository is {self.clone_dir}.\n'
            f'The repository contains the following files:\n{list_files(self.clone_dir)}\n'
            
            f'The initial message you send to the Build_Instructions_Retriever agent should be as follows:\n'
            f'{self.initial_message_retriever()}\n'
            
            )
            
# def _initial_message(self):
    #     link, document_chunks = self.scrape_document(self.github_repo)
    #     ### merged Ishan and Divij's prompts
        
    #     return(
    #         f'I have cloned the GitHub repository, {self.github_repo} at {self.clone_dir}.\n'
    #         f'The repository contains the following files:\n{self.tools.list_files(self.clone_dir)}\n'
    #         f"How do I clone and compile the github repository : {link} on Ubuntu? You may look for compilation resources if availble in the Readme content: {document_chunks}. The destination directory for the compiled files should be {self.compiled_save_path}. Give me the only the commands. Do not include explanation and examples."
    #     )