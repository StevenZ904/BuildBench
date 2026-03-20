from googlesearch import search
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema import StrOutputParser
from langchain.agents import AgentExecutor,Tool
from langchain.agents import create_react_agent
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
import requests
import logging
import os

from Config import *

os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT

proxy = 'socks5://127.0.0.1:29999'

def google_search(question):
    """
    Search relevant information with the question.
    @param question: the question that you wanted to search
    """
    search_results = search(question, num_results=5, proxy=proxy, advanced=True)

    results = ""
    id = 1
    for result in search_results:
        results += f"""{id}. Title: {result.title}\n{id}. Description: {result.description}\n{id}. URL: {result.url}"""
        id += 1

    template = """You are a Search Result Analysis Expert, specializing in evaluating and ranking web pages based on relevance and quality. Your task is to analyze a set of search results and identify the top 3 most relevant URL for the given query.
    Role: Search Result Analysis Expert
    Objective: Determine the 3 most relevant URL from a list of search results for a specific query.
    Evaluation Criteria:

    1. Query-Content Alignment (40%):
    Exact and partial keyword matches in title and description
    Semantic relevance to the query's intent
    Comprehensiveness of topic coverage

    2. Information Quality (30%):
    Depth and specificity of information suggested by the description
    Recency and timeliness of the content (if discernible)
    Uniqueness of insights offered

    3. Source Credibility (20%):
    Domain authority and reputation
    Professional or academic affiliation (if apparent)
    Presence of author expertise indicators

    4. User Experience Factors (10%):
    Clarity and structure of the presented information
    Accessibility and readability of the content
    Potential for multimedia or interactive elements

    Input Format:
    Query: {question}
    Results:

    {results}

    Instructions:

    1. Carefully read the query and all search results.
    2. Apply the evaluation criteria to each result, mentally noting strengths and weaknesses.
    3. Identify the top 3 URLs that best satisfies the criteria and most effectively answers the query.
    4. Rank these 3 URLs in order of relevance, with the most relevant first.
    5. Output only the selected URLs in ranked order, without any additional explanation.

    Output Format:
    1. [Most relevant URL]
    2. [Second relevant URL]
    3. [Third relevant URL]
    """

    llm = ChatOpenAI(
        base_url=READMEAI_BASE_URL,
        model=READMEAI_MODEL,
        api_key=READMEAI_API_KEY,
        temperature=1
    )

    prompt = PromptTemplate.from_template(template=template)
    chain = (prompt | llm | StrOutputParser())
    answer = chain.invoke({"question":question, "results":results})
    return answer

def get_url_content(url):
    """
    Get content from given url.
    @param url: the given url
    """
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
        "http": proxy,
        "https": proxy
    }

    try:
        response = requests.get(url,headers=headers,proxies=proxies)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        texts = soup.get_text(separator="\n",strip=True)
        if len(texts)<=320000:
            return texts
        else:
            return texts[:320000]        
    except Exception as e:
        logging.error(e)
        return f"Request url error: {url}"

def search_agent(question):
    """
    Google Search is used to search for recent information and questions that you are completely unaware of.
    @param question: The search question.
    """
    llm = ChatOpenAI(
        base_url=READMEAI_BASE_URL,
        model=READMEAI_MODEL,
        api_key=READMEAI_API_KEY,
        temperature=1
    )

    template = """You are a Content Retrieval and Summarization Expert. Your task is to search for relevant information, retrieve content from the top 3 URLs, and provide a comprehensive summary.

    Available tools:
    {tools}

    Use the following format:

    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [ {tool_names} ]
    Action Input: the input to the action, do not explain the input further
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)

    Thought: I now know the final answer
    Final Answer: the final answer to the original input question

    Begin!

    Question: {input}
    Thought:{agent_scratchpad}"""

    tools = [
        Tool(
            name="GOOGLE_SEARCH",
            func=google_search,
            description=google_search.__doc__
        ),
        Tool(
            name="GET_CONTENT_FROM_URL",
            func=get_url_content,
            description=get_url_content.__doc__
        )
    ]


    prompt = PromptTemplate.from_template(template)
    agent = create_react_agent(llm=llm,tools=tools,prompt=prompt)
    agent_executor = AgentExecutor(agent=agent,tools=tools,verbose=True,return_intermediate_steps=True,max_iterations=30,handle_parsing_errors=True)
    return agent_executor.invoke({"input":question})