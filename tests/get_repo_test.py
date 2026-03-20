import argparse
from src.tools import get_target_github_repos
from src.default_values import DEFAULT_VALUES
args={'random':10,'test':False}
args=argparse.Namespace(**args)
print(get_target_github_repos(args, DEFAULT_VALUES))
