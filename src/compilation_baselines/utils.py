import os
import re
import requests
import asyncio
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel
import subprocess
from time import time, sleep
from urllib.parse import urlparse, unquote
from playwright.async_api import async_playwright
from markdownify import markdownify as md
from openai import OpenAI
from tavily import TavilyClient

from dotenv import load_dotenv
load_dotenv()
        
OPENAI_API_KEY = os.environ.get('OPENAI_KEY')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
MODEL_NAME = os.environ.get('MODEL_NAME', 'claude-3-7-sonnet-20250219')

openai_client = None
if ANTHROPIC_API_KEY:
    openai_client = OpenAI(api_key=ANTHROPIC_API_KEY, base_url="https://api.anthropic.com/v1/")
elif OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None
class Extract_Build_Information_and_Links(BaseModel):
    Build_Instructions: str
    External_URLs: list[str]
    Internal_Paths: list[str]
    

class Extract_Build_Information_and_External_Links(BaseModel):
    Build_Instructions: str
    External_URLs: list[str]
    
class Extract_Url_Summary_and_External_Links(BaseModel):
    ### Prepared for RAG
    Build_Instructions: str
    External_URLs: list[str]
    Internal_Paths: list[str]



async def get_html_content_in_markdown(url: str, timeout: int = 300000):
    """
    Retrieves the fully rendered HTML content of a given URL.
    Waits until the client-side redirection (if any) is complete.
    
    Parameters:
        url (str): The URL to navigate to.
        timeout (int): Timeout in milliseconds for navigation and waiting.
        
    Returns:
        str: The HTML content of the page if successful, or an empty string on failure.
    """
    headers = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/115.0.0.0 Safari/537.36")
    }
    response = requests.get(url, headers=headers, allow_redirects=True)
        
    if response.status_code == 200:
        # soup = BeautifulSoup(response.text, 'html.parser')
        # paragraphs = soup.find_all('p')
        # content = ' '.join([p.text for p in paragraphs])
        html_content = response.text

    else:
        print("****** USING PLAYWRIGHT TO GET HTML CONTENT ******")
        async with async_playwright() as p:
            # Launch the browser
            browser = await p.chromium.launch(headless=True)
            # Set a user agent to mimic a typical desktop browser
            user_agent = headers["User-Agent"]
            # Create a new browser context with the custom user agent
            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            try:
                # Navigate to the URL with DOMContentLoaded event as a checkpoint.
                response = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                if response is None:
                    print("Navigation failed: No response received.")
                    return ""
                
                # Allow a brief pause for any client-side redirection to occur.
                await asyncio.sleep(1)
                
                html_content = await page.content()
            except TimeoutError as e:
                print("Page navigation or redirection timed out:", e)
            finally:
                await context.close()
                await browser.close()
        
    if html_content is None:
        print(f"Error accessing the external link {url}")
        html_content = "No content found due to error"

    # Convert HTML to Markdown
    markdown = md(html_content)
    return markdown

def search_online_using_tavily(repo_full_name):
    '''
    Search online using tavily, returning only the content of the url from the top 1 result
    '''
    query = f'How to build the {repo_full_name} repository from Github from source?'
    response = tavily_client.search(
        query=query,
        max_results=1
    )
    url = response['results'][0]['url']
    content = asyncio.run(get_html_content_in_markdown(url))
    return content


def list_files(path: str) -> list[str]:
    """
    List files in a Github repository directory, excluding hidden files and directories.
    """
    def remove_elements(lst, remove_list):
        return [value for value in lst if value.lower() not in remove_list]
    
    return remove_elements(
        lst = os.listdir(path),
        remove_list = [
            '.git',
            '.github',
            '.gitmodules',
            'tests',
            'license',
            'changelog.md',
            'redistributed.md',
            '.dockerignore',
            'dockerfile',
            'docker-compose.yml',
        ]
    )
    
def find_files(path: str, extension: str, list_root_dir = False) -> list[str]:
    """
    Find files with a specific extension in a directory and its subdirectories.
    """
    found_files = []
    if list_root_dir:
        for file in os.listdir(path):
            if file.endswith(extension):
                found_files.append(os.path.join(path, file))
    else: 
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(extension):
                    found_files.append(os.path.join(root, file))
    return found_files

def is_url(link: str) -> bool:
    """
    Determine if a given string is a valid URL.
    """
    parsed = urlparse(link)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def extract_links(text: str) -> Dict[str, List[str]]:
    """
    Extract external and internal links from the text based on specified patterns.
    """
    patterns = {
        'external': r'\[external\]\s*\[(https?://[^\]]+)\]',
        'internal': r'\[internal\]\s*\[([^\]]+)\]'
    }
    return {key: list(set(re.findall(pattern, text, re.IGNORECASE))) 
            for key, pattern in patterns.items()}

def read_file(path: str) -> str:
    try:
        content = open(path, 'r').read().strip()
    except Exception as e:
        print(f"Error reading file: {e}")
        return "Error reading file"
    return content


def summarize_text(text: str, system_prompt = None, timeout_min: int = 0, refine: bool = False, response_format = Extract_Build_Information_and_Links, final_refine = False, readme_path = None, base_url = None) -> dict:
    if readme_path is not None:
        readme_dir = os.path.dirname(os.path.abspath(readme_path))
    else:
        if base_url is not None:
            readme_dir = f"{base_url}/README.md"
        else:
            readme_dir = None
            
            
    base_system_prompt = """
        You are an expert at extracting only the most relevant information (such as build instructions, dependency requirements) for building a repository from source for Linux based on provided documentation. Oftentimes, the steps of compilation or building from source for Linux should have already been included in the this file, otherwise, they may be stored in one other local files or external links. 

        """
        
    if system_prompt is None:
        ### By default, summarizing README if the system prompt is not provided
        system_prompt = base_system_prompt+f""" 
        Additionally, identify external or internal links within the documentation following the above objective. 
        For external URLs, extract the full url of links that are useful according to the above criterions.
        For internal file paths, use {readme_dir} as the base path to complete the partial paths. Besides, refine the internal paths to ensure they are valid paths. For example, the /docs/HowToGuides/GettingStarted.md#installing-dependencies should be completed as {readme_dir}/docs/HowToGuides/GettingStarted.md, as the section name after # would interfere with the validity of the path.
        
                
        If you determine that there is no information directly related to building from source on Ubuntu like community support, License, Contribution, installation instructions for other use cases (such as Python etc.) or other irrelevant information, simply fill the field of "Build_Instructions" with "No build instructions found" but still try to find useful urls or internal links for External_URLs and Internal_Paths.

        """ 
        # """
        # Include these links in your output by wrapping them in the following format to denote their type:

        # ###[external][URL]###
        # ###[internal][URL or Path]###
        # """
        if refine:
            system_prompt += """
            You are previously given this task, and we extracted the texts from the external and internal links you provided. Now, based on the texts contained in the links, you should refine your output. If you think the previously extracted links are good enough and the build from source instruction has been included in the response, you can say: 'No need to refine the output'.
            
            """
        if final_refine:
            system_prompt = base_system_prompt


    try:
        
        # response = client.chat.completions.create(
        #     model = MODEL_NAME,
        #     messages = [
        #         {'role': 'system', 'content': system_prompt},
        #         {'role': 'user', 'content': text},
        #     ]
        # )
        # output = response.choices[0].message.content.strip()
        # if 'I am sorry' in output.lower(): ### If the LLM is not able to generate a response, return None
        #     output = None

        
        ### Using OpenAI's response format for structured output
        response = openai_client.beta.chat.completions.parse(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_format=response_format,
        )
        output = response.choices[0].message.parsed

    except Exception as e:
        print('When summarizing text:', e)
        output = {}
        
    return output



async def summarize_link(url: str) -> str:
    markdown_html_content = await get_html_content_in_markdown(url)
    try:
        response = summarize_text(
            text=markdown_html_content,
            system_prompt = f"""
            You are an expert at extracting only the relevant information (such as build instructions, dependency requirements) needed to build a C/C++ repository from source on Linux. Your output should include only content directly related to the build-from-source process. Exclude any information or links related to community support, licensing, developer/API documentation, contribution guidelines, or installation instructions for alternative use cases (such as Python, R, CLI, etc.). When extracting links, include only those directly related to building from source. If any link is partial, complete it using the base URL {url}.

            """
            
            # """
            # Include these links in your output by wrapping them in the following format to denote their type:

            # ###[external][URL]###
            # """,
            ,
            response_format = Extract_Build_Information_and_External_Links 
        )
        # print("*"*50)
        # print(response)
        # print("*"*50)
        return response

    except Exception as e:
        print(f"Error summarizing link: {e}")
        return "Error summarizing link"
    
def rag_summarize_link(all_link_data:str, repo_name):
    ### Write me an openai demo
    response = openai_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": f"You are an expert at picking up the most important urls from a list of urls and their content summaries. The target is to pick the only url that contains the direct steps of building a github repository called {repo_name} from the source on a Ubuntu system. If none of the urls contains the direct step of building from source (not the installation instructions for other use cases), please say: 'No build instructions found'. Otherwise, return only the url and nothing else"},
            {"role": "user", "content": all_link_data},
        ],
    )
    output = response.choices[0].message.content.strip()
    return output

def get_readme_path(build_tools_dict = None, repo_dir = None):
    if build_tools_dict is not None and build_tools_dict.get('readme') is not None:
        readme_files = build_tools_dict['readme'] 
    else:
        readme_files = find_files(repo_dir, '.md', list_root_dir=True)

    readme_content = ""    
    if len(readme_files) == 0:
        readme_content = "No readme file found"
        readme_full_path = None
        print("Exception: No readme file found")
        print("But we will still continue with the process")
    else:
        readme_path = None
        for file in readme_files:
            if 'readme.md' in file.lower():
                readme_path = file
                break
        
        if readme_path != None:
            readme_full_path = os.path.join(repo_dir, readme_path)
        else:
            readme_path = readme_files[0]
            readme_full_path = os.path.join(repo_dir, readme_path)
    
    if readme_full_path is not None:
        readme_content = read_readme(readme_full_path )       
    return readme_full_path, readme_content

def read_readme(readme_path:str) -> str:
    """
    Reads the content of a README file and returns it as a string,
    preserving all hyperlinks.

    Args:
        readme_path (str): The file path to the README file.

    Returns:
        str: The content of the README file.

    Raises:
        FileNotFoundError: If the README file does not exist at the given path.
        IOError: If there is an error reading the file.
    """

    if not os.path.isfile(readme_path):
        raise FileNotFoundError(f"The file '{readme_path}' does not exist.")

    try:
        with open(readme_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
        return content
    except IOError as e:
        raise IOError(f"An error occurred while reading '{readme_path}': {e}")
    

def get_build_dict(repo_dir):
    files = os.listdir(repo_dir) # List of files in the repo
    # print("files in the repo", files)
    build_tools_dict = {}

    build_systems = {
        "make": ["makefile"],
        "cmake": ["cmakelists.txt"],
        #  "travisci": [".travis.yml"],
        #  "circleci": ["config.yml"],
        #  "rake": ["rakefile"],
        # "sln": [".sln"],
        "autoconf": ["configure"],
        # "java": ["build.gradle", "gradlew", "pom.xml"],
        "ninja": ["ninja", "build.ninja"],
        # "bootstrap": ["bootstrap"],
        # 'meson': ['meson.build'],
        'readme': ['readme.md', 'readme.txt', 'readme.rst'],
        'install': ['install', 'install.md'],
        'build': ['build.md', 'build.txt'], 
        }    
    
    # Check if the file is a build file, if so, save the file name in the build_tools_dict
    for fname in files:
        for build_tool, file_keywords in build_systems.items():
            for file_keyword in file_keywords:
                if file_keyword in fname.strip().lower():
                    if build_tools_dict.get(build_tool) is None:
                        build_tools_dict.update({build_tool: [fname]})
                    else:
                        build_tools_dict[build_tool].append(fname)
                    # Save the build tool and the file name in the build_tools_dict
                
  
    return build_tools_dict

def clone_repository(repo_url, clone_repo_dir):
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    clone_repo_dir = os.path.join(clone_repo_dir, repo_name)
    if not os.path.exists(clone_repo_dir):
        try:
            cmd = ["git", "clone","--depth=1", repo_url, clone_repo_dir]
            max_attempts = 3
            delay = 30  # seconds
            attempt = 1
            
            while attempt <= max_attempts:
                print( f"Cloning {repo_url}... (Attempt {attempt}/{max_attempts})")
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                if result.returncode == 0:
                    print(f"Successfully cloned {repo_url}.")
                    break
                else:
                    print(f"Failed to clone {repo_url}:\n{result.stderr.decode('utf-8')}")

                    # If we still have attempts left, sleep and retry
                    if attempt < max_attempts:
                        print(f"Retrying in {delay} seconds...")
                        sleep(delay)
                        delay *= 2  # Exponential backoff
                    else:
                        print(f"Exceeded maximum retry attempts ({max_attempts}). Exiting.")
                        raise Exception(f"Exceeded maximum retry attempts ({max_attempts}). Exiting.")
                attempt += 1
                        
        except Exception as e:
            print(f"Failed to clone {repo_url}: {e}")
        return clone_repo_dir
    else:
        print(f"Repository {repo_name} already exists in {clone_repo_dir}")    
        return clone_repo_dir
# def validate_internal_path(readme_path:str, path: str) -> bool:
#     """
#     Validate the internal path.
#     """
#     ### NOTE: This is a temporary fix to validate the internal path
#     if path[0] == '/':
#         path = path[1:]
#     readme_dir = os.path.dirname(os.path.abspath(readme_path))
#     abs_path = os.path.join(readme_dir, path)
#     abs_path = os.path.normpath(abs_path)
#     if os.path.exists(abs_path):
#         return abs_path
#     else:
#         print(f"Validated Path {abs_path} from original path {path} not found, returning original path")
#         return path

# def extract_and_process_internal_links(readme_path: str, links: dict, text: str = None) -> Dict[str, List[str]]:
#     """
#     process internal links.
#     """
#     # links = extract_links(text)
    
#     internal_links = links.get('internal', [])
    
#     for link in internal_links:
#         if is_url(link):
#             links['external'].append(link)
#             internal_links.remove(link)
#         else:
#             abs_path = validate_internal_path(readme_path, link)
#             if os.path.exists(abs_path):
#                 if os.path.isdir(abs_path):
#                     internal_links.remove(link)
#                     print("The path is a directory, removing it from the internal links")
#                 else:
#                     internal_links.remove(link)
#                     internal_links.append(abs_path)
#                     print("The validated path is correct, replacing the original path with the validated path")
#             else:
#                 print(f"[Path not found] {abs_path}")
#                 # resolved.append(f"[Path not found] {abs_path}")

#     return {
#         'external': links.get('external', []),
#         'internal': internal_links
#     }

if __name__ == "__main__":
    repo_dir = './cloned_repos/catboost'
    readme_path, readme_content = get_readme_path(build_tools_dict=None, repo_dir=repo_dir)
    print(readme_path)
    # print(readme_content)