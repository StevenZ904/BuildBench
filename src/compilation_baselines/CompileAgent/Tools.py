import os
import time
import json
import requests
import logging
import httplib2
import paramiko
import subprocess
import requests
import chardet
import httpx
import openai
import requests
import re
from tqdm import tqdm
from typing import List
from langchain.tools import tool
from googleapiclient.discovery import build
from langchain_chroma import Chroma
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.runnables import RunnableLambda
from langchain.schema.runnable import RunnablePassthrough
from langchain.prompts import PromptTemplate
from langchain.schema import StrOutputParser
from langchain.docstore.document import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from ipdb import set_trace as bp

from Config import *

class InteractiveDockerShell:
    HOSTNAME = 'buildbench'
    def __init__(self, local_path, image_name='buildbench/compilation_base_image_compileagent:1', use_proxy=False, stuck_timeout=120, cmd_timeout=3600, pre_exec=True):
        try:
            container_id = subprocess.run(f"docker run --network bridge --hostname {self.HOSTNAME} -v {local_path}:/work/ -itd {image_name} /bin/bash", 
                                          shell=True, capture_output=True).stdout.decode().strip()
            assert len(container_id)==64, "Failed to create the container."
            logging.info(f"[+] Container {container_id} created.")
            json_str = subprocess.run(f"docker inspect {container_id}", shell=True, capture_output=True).stdout.decode()
            ipaddr = json.loads(json_str)[0]['NetworkSettings']['IPAddress']
            retcode = subprocess.run(f"docker exec {container_id} /bin/bash -c 'service ssh start'", shell=True, capture_output=True).returncode
            assert retcode==0, "Failed to start the ssh service."
        except Exception as e:
            raise Exception(f"Failed to create the container, error: {str(e)}")

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(ipaddr, username='root', password='root', port=22)
        self.session = self.client.invoke_shell()
        self.session.settimeout(stuck_timeout)
        time.sleep(1)
        self.session.recv(1024) # skip the welcome message
        self.stuck_timeout = stuck_timeout
        self.cmd_timeout = cmd_timeout
        self.container_id = container_id
        self.last_line = "root@c0mpi1er-c0nta1ner:/work# "
        self.logger = []
        if pre_exec:
            self.execute_command("proxychains -q apt update")
        if use_proxy:
            self.execute_command("proxychains -q /bin/bash")

    
    def execute_command(self, command:str) -> str:
        """
        Execute a command in a interactive shell on the local machine (on Ubuntu 22.04 with root user). Initially, we are in the /work/ directory.
        @param cmd: The command to execute.
        """
        if self.session is None:
            raise Exception("No session available.")

        # clean the command
        command = command.strip()
        for wrap in ["`", "\"", "**", "```"]:
            if command.startswith(wrap) and command.endswith(wrap):
                command = command[len(wrap):-len(wrap)]

        if "git " in command and "proxychains git " not in command:
            command = command.replace("git ", "proxychains -q git ")
        if "curl " in command and "proxychains curl " not in command:
            command = command.replace("curl ", "proxychains -q curl ")
        if "wget " in command and "proxychains wget " not in command:
            command = command.replace("wget ", "proxychains -q wget ")
        if "apt install " in command:
            command = command.replace("apt install ", "apt install -y ")
        if "apt-get install " in command:
            command = command.replace("apt-get install ", "apt-get install -y ")
        if command.strip() == "^C":
            command = '\x03'
        if "make install" in command:
            return "Tips: Do not install the project, just compile it!"
        # TODO delete me
        if "make" == command.strip():
            command = "make -j32"
        # if "&& make" in command:
        #     command = command.replace("&& make", "&& make -j32")
        # if "make &&" in command and "cmake" not in command:
        #     command = command.replace("make &&", "make -j32 &&")
        # if "make" in command and "make clean" not in command and "cmake" not in command and "make -j32" not in command and 'automake' not in command and 'cd make' not in command:
        #     command = command.replace("make", "make -j32")

        self.session.send(command + '\n')

        cmd_start_time = time.time()
        start_time = time.time()
        output = ""
        while True:
            if time.time() - cmd_start_time > self.cmd_timeout or \
                time.time() - start_time > self.stuck_timeout: # execution timeout
                self.session.send('\x03')
                flag = "\nCommand execution timeout!\n"
                while self.HOSTNAME not in output:
                    if time.time() - start_time > self.stuck_timeout * 2:
                        raise Exception(f"Command timeout and cannot be stopped, cmd={command}")
                    try:
                        recv = self.session.recv(1024)
                    except:
                        flag = "\nShell has stuck by waiting input. You can still input something needed to handle this stuck, just input what needed in raw with SHELL tool.\n"
                        break
                    encode_result = chardet.detect(recv)
                    # print(f"encode_result: {encode_result}")
                    # output += recv.decode(encoding=(encode_result["encoding"] if encode_result["encoding"] != None else "utf-8"),errors="ignore")
                    output += recv.decode(encoding="utf-8",errors="ignore")
                output += flag
                # breakpoint()
                return self.omit(command, output, time.time()-cmd_start_time)
            
            if self.HOSTNAME in output: # return condition
                return self.omit(command, output, time.time()-cmd_start_time)
            # read outputs
            if self.session.recv_ready():
                while self.session.recv_ready():
                    recv = self.session.recv(1024)
                    encode_result = chardet.detect(recv)
                    # breakpoint()
                    # output += recv.decode(encoding=(encode_result["encoding"] if encode_result["encoding"] != None else "utf-8"),errors="ignore")
                    output += recv.decode(encoding="utf-8",errors="ignore")
                time.sleep(0.5)  # add a delay after receiving output
                start_time = time.time() # reset the start time
            else:
                time.sleep(0.5)

    def omit(self, command, output, duration)->str:
        '''
        omit the command from the output for special commands
        '''
        output = re.sub(r'\x1B[@-_][0-?]*[ -/]*[@-~]', '', output) # remove the ANSI escape characters
        output = self.last_line + output
        self.logger.append([command,output,duration]) # log the command and output in raw
        # get last line of the output
        self.last_line = output.split("\n")[-1]
        # omit output
        if command.startswith("make"):
            return "\n".join(output.split("\n")[-50:])
        elif command.startswith("configure") or command.startswith("./configure"):
            return "\n".join(output.split("\n")[-30:])
        elif command.startswith("cmake"):
            return "\n".join(output.split("\n")[-30:])
        else:
            if len(output)>8000:
                output = output[:4000]+"\n......\n"+output[-4000:]
            return output

    def close(self):
        logging.info("[-] Stopping docker container, please wait a second...")
        if self.client:
            self.client.close()
        if self.container_id:
            subprocess.run(f"docker stop {self.container_id}", shell=True)
            subprocess.run(f"docker rm {self.container_id}", shell=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# RAG and Model decision
class SearchCompilationInstruction:
    def __init__(self, directory_path: str, project_name: str, threshold=0.80, use_proxy=False):
        self.vectorstore = None
        self.similarity_threshold = threshold
        self.directory_path = directory_path
        self.project_name = project_name
        self.vec_store = f"vec_store/{self.project_name}" 
        self.compilation_ins_doc = []
        self.logger = [] # loggger search_instruction
        self.logger1 = [] # search_instrcution_from_files_logger
        self.logger2 = [] # search_url_from_files_logger
        self.logger3 = [] # search_instrcution_from_url_logger
        self.use_proxy = use_proxy
        self.startswith_list = ["readme","build","install","contributing","how-to"]
        self.endswith_list = [".markdown"]
        self.file_name = []
        self.keywords = ["compile","build","compilation"]
        self.keywords_files = []
        # find possible compilation instruction documents
        for root, dirs, files in os.walk(self.directory_path):
            for file in files:
                if any(file.lower().startswith(f"{prefix}") for prefix in self.startswith_list):
                    self.compilation_ins_doc.append(os.path.join(root,file))
                if any(file.lower().endswith(f"{suffix}") for suffix in self.endswith_list):
                    self.compilation_ins_doc.append(os.path.join(root,file))
                if file.lower in self.file_name:
                    self.compilation_ins_doc.append(os.path.join(root,file))

    def read_files(self, doc_path_list: list) -> list:
        documents = []
        for file_path in doc_path_list:
            try:
                with open(file_path,'r',errors="ignore") as fp:
                    documents.append(
                        Document(page_content=fp.read(), metadata={"source":file_path})
                    )
            except Exception as e:
                logging.error(f"[!] Failed to read {file_path}:\n{e}")
        return documents

    def setup_rag(self, docs) -> bool:
        if docs != []:
            try:
                start_time = time.time()
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=3000, chunk_overlap=200, add_start_index=True
                )
                all_splits = text_splitter.split_documents(docs)
                emb_function = OpenAIEmbeddings(
                        base_url=OPENAI_BASE_URL,
                        model=OPENAI_EMBEDDING_MODEL,
                        api_key=OPENAI_API_KEY,
                        # http_client=httpx.Client(proxies=self.use_proxy) if self.use_proxy else None,
                    )
                if os.path.exists(self.vec_store):
                    self.vectorstore = Chroma(persist_directory=self.vec_store, embedding_function=emb_function)
                    return True, 0
                else:
                    self.vectorstore = Chroma.from_documents(
                        documents=all_splits,
                        embedding=emb_function,
                        persist_directory=self.vec_store
                    )
                end_time = time.time()
                return True, (end_time-start_time)
            except Exception as e:
                logging.error(f"[!] Failed to build vectorstore:\n{e}")
                return False, 0
        return False, 0
    
    def get_relevant_docs(self, query):
        # retriver = self.vectorstore.as_retriever(search_type="similarity",search_kwargs={"k":6})
        docs_and_scores = self.vectorstore.similarity_search_with_score(query) 
        relevant_docs = [
            Document(page_content=doc.page_content,metadata=doc.metadata)
            for doc, score in docs_and_scores
            if score >= self.similarity_threshold
        ] # TODO check the score, if descending order
        return relevant_docs

    def search_instruction(self,rag_ok):
        self.logger = []
        if rag_ok:
            query = "How to compile/build the project?"
            docs = self.get_relevant_docs(query)
            if docs:
                try:
                    llm = ChatOpenAI(
                        base_url=DEEPSEEK_BASE_URL,
                        api_key=DEEPSEEK_API_KEY,
                        model=DEEPSEEK_MODEL,
                        temperature=1,
                    )
                    template = """You are an experienced software development engineer and specialized in extracting compilation commands. The documents from a project repository will be provided and you need to carefully identify relevant compilation/building instructions. If no compilation commands are found, respond with "No compilation commands found." If found, list the compilation commands concisely, clearly, and professionally without any additional explanations.
                    Documents: {text}
                    Answer: """
                    _template = """You are an experienced software development engineer and specialized in building a project from source code. The documents from a project repository will be provided, and you need to carefully analyze them and output the useful information about "how to compile the project". If there is no such information, output "<NOT-FOUND-INSTRUCTION>" Make sure the output is concisely, clearly, and professionally without any additional explanations.
                    Documents: {text}
                    Output: """
                    context = "\n".join(doc.page_content for doc in docs)
                    # if len(context)>=32000:
                    #     context = context[:32000]
                    prompt = PromptTemplate.from_template(template=template)
                    rag_chain=(
                        {"text":RunnableLambda(lambda x :context)}
                        | prompt
                        | llm
                        | StrOutputParser()
                    )
                    answer = rag_chain.invoke({})
                    self.logger.append([
                            template.format(text=context),
                            answer,
                            [[doc.metadata,doc.page_content] for doc in docs],
                            {"ori_content_len":len(context),"answer_len":len(answer)}
                        ])
                    return answer
                except Exception as e:
                    logging.error(f"[!] Failed search instruction:\n{e}")
                    return "Search failed due to unknown reason."

        return "Not found possible compilation guidance from files stored in the local path."
    
    def search_url_from_files(self, *args, **kwargs):
        """
        Retrieve the URL associated with the compilation instructions.
        This function doesn't take any arguments.
        """
        query = "From which URL can I find the compilation instructions?"
        docs = self.get_relevant_docs(query)
        if docs:
            try:
                llm = ChatOpenAI(
                    base_url=DEEPSEEK_BASE_URL,
                    api_key=DEEPSEEK_API_KEY,
                    model=DEEPSEEK_MODEL,
                    temperature=1,
                )
                template = """You are an experienced software development engineer and specialized in identifying URLs related to compilation commands. Analyze the given text and extract any URLs specifically associated with obtaining or referencing compilation instructions. If no relevant URLs are found, simply state 'No relevant URLs found.' Ensure the result is accurate, concise, and professional.
                Text: {text}
                Answer: """
                context = "\n".join(doc.page_content for doc in docs)
                # if len(context)>32000:
                #     context = context[:32000]
                prompt = PromptTemplate.from_template(template=template)
                rag_chain=(
                    {"text":RunnableLambda(lambda x :context)}
                    | prompt
                    | llm
                    | StrOutputParser()
                )
                answer = rag_chain.invoke({})
                self.logger2.append([
                    template.format(text=context),
                    answer,
                    [[doc.metadata,doc.page_content] for doc in docs],
                    {"ori_content_len":len(context),"answer_len":len(answer)}
                ])
                return answer
            except Exception as e:
                logging.error(f"[!] Failed search url:\n{e}")
                return "Search failed due to unknown reason."
            
        return "Not found any relevant URL from files stored in the local path."
    
    def get_url_content(self, url):
        ua = UserAgent()
        headers = {
            "User-Agent": ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        proxies = {
            "http": self.use_proxy,
            "https": self.use_proxy
        }

        try:
            response = requests.get(url,headers=headers,proxies=proxies)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            texts = soup.get_text(separator="\n",strip=True)
            return [Document(page_content=texts,meta_data={"source":url})]
        except Exception as e:
            logging.error(e)
            return f"Request url error: {url}"

    def search_instruction_by_agent(self, file_path: str) -> str:
        '''
        A tool for finding out the compilation instruction from a document file stored in a project repository.
        @param file_path: The absolute path of the document file, e.g. /work/README.md
        '''
        file_path = file_path.strip()
        if ", " in file_path:
            return "The input should be a single file path"
        if not os.path.isabs(file_path):
            return "The file path should be absolute path."
        real_file_path = file_path.replace("/work", self.directory_path).strip()
        if not os.path.exists(real_file_path):
            return f"File {file_path} does not exist."

        try:
            with open(real_file_path,'r') as f:
                content = f.read()
                if len(content)>32000:
                    content = content[:32000]
            llm = ChatOpenAI(
                base_url=DEEPSEEK_BASE_URL,
                api_key=DEEPSEEK_API_KEY,
                model=DEEPSEEK_MODEL,
                temperature=1,
            )
            template = """You are an experienced software development engineer and specialized in building a project from source code. The content of a file from a project repository will be provided, and you need to carefully analyze and output the useful information about "how to compile the project on linux". The output should be an extraction of the compilation guide section of the file, complete with compilation-related information. If there is no such information, output "<NOT-FOUND-INSTRUCTION>". Make sure the output is complete, accurate, and without additional explanations.
            Document: {file_path}
            {text}
            Output: """
            prompt = PromptTemplate.from_template(template=template)
            chain = ( prompt | llm | StrOutputParser() )
            logging.info(f"[+] Invoke SearchCompilationInstruction for file: {real_file_path}")
            answer = chain.invoke({"text":content,'file_path':file_path})
            self.logger.append([
                real_file_path, 
                template.format(text=content,file_path=file_path), 
                answer, 
                {"ori_content_len":len(content),"answer_len":len(answer)}
                ])
            return answer
        except Exception as e:
            logging.error(f"[!] Failed search file: {real_file_path}\n{str(e)}")
            return "Search failed due to unknown reason."
        
    def search_instruction_from_files(self, *args, **kwargs):
        """
        Retrive the project's compilation instructions from the documentation.
        This function doesn't take any arguments.
        """
        if self.compilation_ins_doc != []:
            files_content = self.read_files(self.compilation_ins_doc)
            rag_ok,duration = self.setup_rag(docs=files_content)
            result = self.search_instruction(rag_ok)
            self.logger1 = self.logger
            self.logger1.append(duration)
            return result
        return "No compilation commands found."

    def search_instruction_from_url(self, url: str, *args, **kwargs):
        """
        Read the content of the URL and retrieve the project's compilation instructions.
        @param url: The URL of the content to be read.
        """
        if url:
            texts = self.get_url_content(url=url)
            rag_ok = self.setup_rag(docs=texts)
            result = self.search_instruction(rag_ok)
            self.logger3 = self.logger
            return result
        return "No compilation commands found."
