import os
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Comment

# ===== 可调开关 =====
STRIP_INLINE_STYLES = True     # 删除所有内联 style
MAKE_BACKUP = True             # 写入前生成 .bak 备份
PROCESS_RECURSIVELY = False    # 递归子目录（如需递归，改为 True）

MOBILE_SNIPPET = """<script>
            if (/mobile/i.test(navigator.userAgent) || /android/i.test(navigator.userAgent))
            {
               document.body.classList.add('mobile');
            }
        </script>"""

def iter_html_files(root: Path):
    exts = {".html", ".htm"}
    if PROCESS_RECURSIVELY:
        for p in root.rglob("*"):
            if p.suffix.lower() in exts and p.is_file():
                yield p
    else:
        for p in root.iterdir():
            if p.suffix.lower() in exts and p.is_file():
                yield p

def has_mobile_script(soup: BeautifulSoup) -> bool:
    for s in soup.find_all("script"):
        code = (s.string or "") + "".join(c for c in s.stripped_strings)
        if "classList.add('mobile')" in code or 'classList.add("mobile")' in code:
            return True
    return False

def insert_mobile_script_if_missing(soup: BeautifulSoup):
    if has_mobile_script(soup):
        return
    body = soup.body
    if not body:
        return
    # 尝试放在“原文”链接的 <p> 后；否则放到 <body> 开头
    target_p = None
    for p in body.find_all("p", recursive=False):
        a = p.find("a", href=True)
        if a and ("原文" in (a.get_text() or "")):
            target_p = p
            break
    frag = BeautifulSoup(MOBILE_SNIPPET, "html.parser")
    if target_p:
        target_p.insert_after(frag)
    else:
        # 放到 body 开头
        if body.contents:
            body.insert(0, frag)
        else:
            body.append(frag)

def remove_ads_in(tag):
    """删除内容区域内的广告：ins.adsbygoogle 及其相邻脚本；顺带清空只剩空白的容器 div。"""
    # 1) 删除 <ins class="adsbygoogle"> 及其前后紧邻的 script
    for ins in list(tag.select("ins.adsbygoogle")):
        # 删除紧邻的上一个 / 下一个 script（若存在）
        prev = ins.find_previous_sibling()
        if prev and prev.name == "script":
            prev.decompose()
        nxt = ins.find_next_sibling()
        if nxt and nxt.name == "script":
            nxt.decompose()
        ins.decompose()

    # 2) 删除只剩空白或全是注释/script 的空 div
    def is_empty_block(t):
        if not t.name:
            return False
        if t.name not in ("div", "section"):
            return False
        for c in t.contents:
            if isinstance(c, Comment):
                continue
            if isinstance(c, NavigableString) and c.strip() == "":
                continue
            if getattr(c, "name", None) == "script":
                # 只含 script 也算空容器（广告残留）
                continue
            return False
        return True

    changed = True
    while changed:
        changed = False
        for d in list(tag.find_all(["div", "section"])):
            if is_empty_block(d):
                d.decompose()
                changed = True
                break

def strip_all_inline_styles(soup: BeautifulSoup):
    for t in soup.find_all(style=True):
        del t["style"]

def pick_main_content_td(table):
    """优先取第一行第一个 <td> 作为主内容区；找不到时退回第一个 <td>。"""
    tr = table.find("tr")
    if tr:
        td = tr.find("td")
        if td:
            return td
    td = table.find("td")
    return td

def pick_article_root_in_td(td):
    """
    在主 td 里找包含 <h2> 的块作为文章根；若找不到，返回 td 自身。
    优先匹配直属的 div/section，其次任意深度 div/section。
    """
    for cand in td.find_all(["div", "section"], recursive=False):
        if cand.find("h2"):
            return cand
    deep = td.find(lambda x: x and x.name in ("div", "section") and x.find("h2"))
    return deep or td

def replace_outer_table_with_inner(soup: BeautifulSoup) -> bool:
    """
    查找最外层布局 table，将其用 <div class="inner">…</div> 替换。
    返回是否发生了替换。
    """
    body = soup.body
    if not body:
        return False

    # 找第一张 table（通常就是布局用的那张）
    table = body.find("table")
    if not table:
        return False

    main_td = pick_main_content_td(table)
    if not main_td:
        return False

    # 在主 td 中清理广告、选择文章根
    remove_ads_in(main_td)
    article_root = pick_article_root_in_td(main_td)

    # 组装 <div class="inner">：搬运 article_root 的子节点
    inner_div = soup.new_tag("div", **{"class": "inner"})
    # 将内容节点移入 inner_div（extract 以移动，而非复制）
    for child in list(article_root.contents):
        inner_div.append(child.extract())

    # 选择替换节点：若 table 父是仅用于外边距的 div（含 style/仅包此 table），优先替换父
    replace_target = table
    parent = table.parent
    if parent and parent.name == "div":
        # 若该 div 内只有这一个 table（排除空白）
        only_tables = [c for c in parent.find_all(recursive=False) if getattr(c, "name", None)]
        if len(only_tables) == 1 and only_tables[0] is table:
            replace_target = parent

    # 用 inner_div 替换
    replace_target.replace_with(inner_div)
    return True

def process_file(path: Path):
    orig = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(orig, "html.parser")

    changed = False
    # 1) 布局替换：table -> <div class="inner">
    if replace_outer_table_with_inner(soup):
        changed = True

    # 2) 插入 mobile 脚本（如缺失）
    before = has_mobile_script(soup)
    insert_mobile_script_if_missing(soup)
    if not before and has_mobile_script(soup):
        changed = True

    # 3) 删除所有内联 style（可关）
    if STRIP_INLINE_STYLES:
        strip_all_inline_styles(soup)
        changed = True

    if not changed:
        print(f"SKIP (no change): {path}")
        return

    if MAKE_BACKUP:
        path.with_suffix(path.suffix + ".bak").write_text(orig, encoding="utf-8")

    html = str(soup)
    path.write_text(html, encoding="utf-8")
    print(f"OK: {path}")

def main():
    root = Path(".").resolve()
    for f in iter_html_files(root):
        try:
            process_file(f)
        except Exception as e:
            print(f"ERROR: {f} -> {e}")

if __name__ == "__main__":
    main()
