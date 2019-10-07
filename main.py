# -*- coding: utf-8 -*-
import argparse
import os
import re
import sqlite3
from collections import namedtuple
from datetime import datetime
from http import HTTPStatus

import requests
from bs4 import BeautifulSoup


def cli() -> None:
    parser.add_argument("-t", dest="dingtalk_token", help="Dingtalk robot token")


BLOG_URL = "http://www.yinwang.org"
DB_FILE = "./title.db"
SCHEMA_FILE = "./schema.sql"
DATE_PATTERN = r"\/(\d{4}\/\d{2}\/\d{2})\/"
DATE_FORMAT = "%Y/%m/%d"
Title = namedtuple("Title", ["href", "title", "published_at"])
parser = argparse.ArgumentParser(description="yinwang.org watcher")

cli()
args = parser.parse_args()


def fetch_html() -> str:
    print("Fetching html doc...", end="")
    resp = requests.get(BLOG_URL, timeout=10)
    try:
        assert resp.status_code == HTTPStatus.OK
    except AssertionError:
        print("ERROR")
        raise
    print("OK")
    return resp.text


def parse_title(html_doc: str) -> map:
    soup = BeautifulSoup(html_doc, features="lxml")
    title_elements = soup.find_all("li", class_="list-group-item title")

    def _func(title_el):
        a = title_el.find("a")
        href = a["href"]
        title = a.get_text()
        return href, title, re.findall(DATE_PATTERN, href)[0]

    return map(_func, title_elements)


def initial_db(titles: list) -> None:
    with sqlite3.connect(DB_FILE) as conn:
        with open(SCHEMA_FILE) as f:
            conn.executescript(f.read())
        for href, title, date in titles:
            script = (
                f"insert into title (href, title, published_at) "
                f"values ('{href}', '{title}', '{date}')"
            )
            conn.executescript(script)


def get_new_titles(titles: list) -> list:
    new_titles = []
    with sqlite3.connect(DB_FILE) as conn:
        csr = conn.cursor()
        csr.execute(
            "select href, title, published_at from title order by id desc limit 1"
        )
        db_latest_title = Title(*csr.fetchone())
        db_latest_date = datetime.strptime(db_latest_title.published_at, DATE_FORMAT)

        for title_tuple in titles:
            title = Title(*title_tuple)
            date = datetime.strptime(title.published_at, DATE_FORMAT)
            if date > db_latest_date:
                print(f"Got a new article: {title.title} at {title.published_at}")
                new_titles.append(title_tuple)
                script = (
                    f"insert into title (href, title, published_at) "
                    f"values ('{title.href}', '{title.title}', '{title.published_at}')"
                )
                conn.executescript(script)
                notify_to_dingtalk(
                    args.dingtalk_token, title.title, BLOG_URL + title.href
                )
    return new_titles


def notify_to_dingtalk(token: str, title: str, url: str) -> None:
    if not token:
        return print("Dingtalk robot token cannot be null")
    post_url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
    payload = {
        "msgtype": "link",
        "link": {"text": title, "title": title, "picUrl": "", "messageUrl": url},
    }
    resp = requests.post(post_url, json=payload, verify=True, timeout=1)
    assert resp.status_code == HTTPStatus.OK
    result = resp.json()
    if result.get("errcode") is not 0:
        print("Dingtalk error response:", result.get("errmsg"))


def main() -> None:
    titles = sorted(parse_title(fetch_html()), reverse=False)
    is_new_db = not os.path.exists(DB_FILE)
    if is_new_db:
        initial_db(titles)
    new_titles = get_new_titles(titles)
    if not new_titles:
        print("No any new articles")


if __name__ == "__main__":
    main()
