# Script to batch create github issues from set of markdown files exported by notion

from lib2to3.pytree import Base
from pathlib import Path
import os
from typing import List
from tqdm import tqdm
import argparse
import json
import time

from ghapi.all import GhApi
from notion.client import NotionClient
from notion.block import Block, TextBlock, BulletedListBlock, HeaderBlock, \
    SubheaderBlock, SubsubheaderBlock, NumberedListBlock
from notion.collection import CollectionRowBlock, PageBlock
from notion2md.exporter import block_string_exporter



class NotionException(Exception):
    pass


def _block_to_markdown(block: Block):
    list_idx = 0
    content = None

    if type(block) is TextBlock:
        list_idx = 0
        content = block.title
    if type(block) is HeaderBlock:
        list_idx = 0
        content = f"# {block.title}"
    if type(block) is SubheaderBlock:
        list_idx = 0
        content = f"## {block.title}"
    if type(block) is SubsubheaderBlock:
        list_idx = 0
        content = f"### {block.title}"
    if type(block) is BulletedListBlock:
        list_idx = 0
        content = f"- {block.title}"
    if type(block) is NumberedListBlock:
        list_idx += 1
        content = f"{list_idx}. {block.title}"
    
    return content
        
def process_block_children(block: Block):
    markdown_content = []
    list_idx = 0

    #if len(block.children) > 0:
    block_children_content = []
    for child_block in block.children:
        block_children_content.append(
            process_block_children(child_block)
        )

    if len(block_children_content) > 0:
        return block_children_content
    
    return _block_to_markdown(block)


def process_view_blocks(backlog_view_url: str):
    """Read blocks in a Notion collection view"""

    notion_token = os.environ.get("NOTION_USER_TOKEN", None)

    if notion_token is None or len(notion_token.strip()) == 0:
        raise NotionException("No Notion token given in environment variable NOTION_TOKEN.")
    
    try:
        notion_client = NotionClient(token_v2=notion_token)
        cv = notion_client.get_collection_view(backlog_view_url)

        for cv_block in cv.collection.get_rows(limit=500):
            backlog_item = {}
            if cv_block.status == "Backlog" and cv_block.name != "Post-alpha":
                backlog_item["title"] = cv_block.title
                backlog_item["labels"] = [cv_block.functionality] if cv_block.functionality is not None else []
                backlog_item["body"] = block_string_exporter(id=cv_block.id)

                yield backlog_item, cv_block
    except NotionException:
        print("Error occurred reading from Notion.")


def create_github_issue(
    gh_api: GhApi, 
    title: str, 
    body: str, 
    labels=List[str], 
    n_retries=10, 
    retry_delay=60
):
    """Create notion story on github as issue"""

    issue = None

    # Try to create issue, and retry n_retries number of times if an exception occurs
    for _ in range(n_retries):
        try:
            # Try to create issue
            issue = gh_api.issues.create(title=title, body=body, labels=labels)
        except BaseException as e:
            # Catch exceptions return from github api
            try:
                result_body = json.loads(e.fp.read())
                result_message = result_body["message"]
                result_doc_url = result_body["documentation_url"]
                print(f"Exception occured calling Github API: {result_message}; {result_doc_url}; retrying in {retry_delay} seconds.")
                if e.code == 403:
                    # If we get an http 403 (forbidden) exception, its likely the rate limit has been exceeded
                    # Pause for retry_delay seconds if rate limit exceeded
                    time.sleep(retry_delay)
            except Exception as inner_e:
                # There was a problem gettig the body of the result from the exception
                print("Tried to get result body from Github, but was unsuccessful")
        else:
            # If no exception occurred, we managed to create the issue so don't retry request
            break
    else:
        # If we retired n_retries times, then issue wasn't created successfully
        print(f"Unable to create issue with title {title}. Skipping creation of issue.")

    return issue

def main():
    parser = argparse.ArgumentParser("notion2github")
    parser.add_argument("backlog_view_url", help="URL to notion collection view containing backlog")
    parser.add_argument("github_owner", help="Github owner of repo to use")
    parser.add_argument("github_repo", help="Name of github repo in which to create issues")
    parser.add_argument(
        "--throttle_delay", 
        default=1, 
        required=False,
        help="Specifies the number of seconds to wait between each github request."
    )
    args = parser.parse_args()
  
    gh_api = GhApi(owner=args.github_owner, repo=args.github_repo)

    for backlog_item, block in tqdm(process_view_blocks(args.backlog_view_url)):
        issue = create_github_issue(gh_api=gh_api, **backlog_item)
        if issue is not None:
            block.github_issue_url = issue.url

        # Throttle requests by adding delay - bit of a hack!
        time.sleep(args.throttle_delay)
    

if __name__ == "__main__":
    main()