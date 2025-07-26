import os
from pathlib import Path

# 指定你的 CSS 文件路径（相对路径或绝对路径都可）
css_link_tag = '<link rel="stylesheet" href="style.css">'

# 处理 .htm 和 .html 文件
extensions = ['.html', '.htm']

def insert_css_link(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 判断是否已经插入过 CSS，避免重复插入
    if css_link_tag in content:
        return

    # 插入 CSS 引用在 <head> 标签之后
    updated_content = content.replace(
        '<head>',
        f'<head>\n    {css_link_tag}',
        1  # 只替换第一个
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    print(f'✅ 插入成功: {filepath}')

def batch_process_html_files():
    for file in os.listdir('.'):
        if any(file.endswith(ext) for ext in extensions):
            insert_css_link(file)

if __name__ == "__main__":
    batch_process_html_files()
