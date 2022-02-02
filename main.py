# Script to batch create github issues from set of markdown files exported by notion

from pathlib import Path
import os
from typing import List
from tqdm import tqdm
import argparse

from ghapi.all import GhApi
from notion.client import NotionClient
from notion.block import Block, TextBlock, BulletedListBlock, HeaderBlock, \
    SubheaderBlock, SubsubheaderBlock, NumberedListBlock
from notion.collection import CollectionRowBlock, PageBlock
from numpy import block


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

def get_markdown_file_by_id(data_path: Path, block_title: str, block_id: str):
    block_file_id = block_id.replace("-", "")
    for block_md_file in data_path.glob(f"*{block_file_id}*"):
        md_content = ""
        with block_md_file.open("rt") as f:
            for l in f:
                if l.find(block_title) == -1:
                    md_content += l

    return md_content

def process_view_blocks(data_path: Path, backlog_view_url: str):
    notion_token = os.environ.get("NOTION_TOKEN", None)
    if notion_token is None or len(notion_token.strip()) == 0:
        raise NotionException("No Notion token given in environment variable NOTION_TOKEN.")

    notion_client = NotionClient(token_v2=notion_token)
    cv = notion_client.get_collection_view(backlog_view_url)

    for cv_block in cv.collection.get_rows(limit=-1):
        backlog_item = {}
        if cv_block.status == "Backlog" and cv_block.name != "Post-alpha":
            backlog_item["title"] = cv_block.title
            backlog_item["area"] = cv_block.functionality
            backlog_item["body"] = get_markdown_file_by_id(data_path, cv_block.title, cv_block.id)

            yield backlog_item, cv_block


def main():
    parser = argparse.ArgumentParser("notion2github")
    parser.add_argument("backlog_view_url", help="URL to notion collection view containing backlog")
    parser.add_argument("github_owner", help="Github owner of repo to use")
    parser.add_argument("github_repo", help="Name of github repo in which to create issues")
    args = parser.parse_args()

    try:    
        markdown_file_path = Path("./data/markdown")
        gh_api = GhApi(owner=args.github_owner, repo=args.github_repo)

        for backlog_item, block in tqdm(process_view_blocks(markdown_file_path, args.backlog_view_url)):
            issue = gh_api.issues.create(
                title=backlog_item["title"],
                body=backlog_item["body"]
            )
            block.github_issue_url = issue.url
            

    except NotionException as e:
        print(e.message)


if __name__ == "__main__":
    main()