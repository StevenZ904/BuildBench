import os
from tqdm import tqdm
import argparse
from tools import clone_repository
import json
from concurrent.futures import ThreadPoolExecutor, as_completed


def clone_repositories(save_path, input_path=None, column_name=None, github_repo=None, logger=None, github_token=None):
    """
    Clones one or multiple GitHub repositories to a specified local directory.

    Parameters:
    save_path (str): The local directory where the repositories will be cloned.
    input_path (str, optional): Path to a json/jsonl file containing repository URLs. Defaults to None.
    column_name (str, optional): The key in the JSON/JSONL file that contains the repository URL or repo path. Defaults to None.
    github_repo (str, optional): A single GitHub repository URL to clone. Defaults to None.

    Raises:
    ValueError: If neither input_path and column_name nor github_repo are provided.

    Returns:
    str or None: The directory of the cloned repository if a single repository is cloned, otherwise None.
    """

    # Ensure save_path exists
    os.makedirs(save_path, exist_ok=True)

    # Determine the repositories to clone
    if github_repo is not None:
        github_repos = [github_repo]
    elif input_path is not None and column_name is not None:
        if input_path.endswith('.jsonl'):
            github_repos = []
            with open(input_path, 'r') as f:
                for line in f:
                    obj = json.loads(line)
                    if column_name in obj:
                        url = obj[column_name]
                        if not url.startswith('http'):
                            url = f'https://github.com/{url}.git'
                        if github_token:
                            url = url.replace('https://', f'https://{github_token}@')
                        github_repos.append(url)
        elif input_path.endswith('.json'):
            with open(input_path, 'r') as f:
                data = json.load(f)
            github_repos = []
            for obj in data:
                if column_name in obj:
                    url = obj[column_name]
                    if not url.startswith('http'):
                        url = f'https://github.com/{url}.git'
                    if github_token:
                        url = url.replace('https://', f'https://{github_token}@')
                    github_repos.append(url)
        else:
            raise ValueError("Unsupported file format. Please provide a JSON or JSONL file.")
    else:
        raise ValueError("Either input_path and column_name or github_repo should be provided.")

    # Clone repositories in parallel
    max_workers = min(8, (os.cpu_count() or 1) * 5)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(clone_repository, url, save_path, logger): url for url in github_repos}
        for future in tqdm(as_completed(future_to_url), total=len(github_repos), desc="Cloning repositories"):
            url = future_to_url[future]
            try:
                future.result()
            except Exception as e:
                if logger:
                    logger.error(f"Error cloning {url}: {e}")
                else:
                    print(f"Error cloning {url}: {e}")
        
    if len(github_repos) == 1:
        return os.path.join(save_path, github_repos[0].split('/')[-1].replace('.git', ''))
    return None

    
    
def parse_args():
    parser = argparse.ArgumentParser(description='Clone repositories from a list of URLs')
    parser.add_argument('--input_path', type=str, help='Path to the file containing the URLs')
    parser.add_argument('--column_name', type=str, help='Name of the column containing the URLs')
    parser.add_argument('--save_path', type=str, help='Path to save the cloned repositories', required=True)
    parser.add_argument('--github_token', type=str, help='GitHub token for authentication', required=True)
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    clone_repositories(save_path=args.save_path,
                       input_path=args.input_path,
                       column_name=args.column_name,
                       github_token=args.github_token)
    