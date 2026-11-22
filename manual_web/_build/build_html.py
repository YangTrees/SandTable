# -*- coding: utf-8 -*-
import base64
import html
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(r'D:\PROJECTS\_AI\SandTable\manual_web')
BUILD = ROOT / '_build'
DOCX = Path(r'D:\PROJECTS\_AI\SandTable\心理沙盘系统_账户与全系统操作手册_V1.2_20261122.docx')
OUTPUT = ROOT / '心理沙盘系统_账户与全系统操作手册.html'

FIG_FILES = [
    '00_login.png', '01_dashboard.png', '04_change_password.png',
    '08_review.png', '02_users.png', '03_add_user.png',
    '09_workbench_login.png', '06_report_viewer.png',
    '07_share.png',
]

CHAPTER_LEADS = {
    'sec-1': '先确认手册的适用范围、入口边界和术语，再开始操作。',
    'sec-2': '四个入口、四类角色，以及一条从建立学生账号到家长查看的完整链路；后台只面向教职员工，工作台只面向学生。',
    'sec-3': '后台登录、学生测评入口、会话、改密、退出，以及常见登录错误的处理方式；两边账号不能互相登录。',
    'sec-4': '工作概览、报告审核、正文修订、分享二维码和数据看板。',
    'sec-5': '仅超级管理员可操作：新增、编辑、重置密码、启停和删除账号，并负责建立学生账号。',
    'sec-6': '学生使用学校账号登录，确认只读身份信息，摆放沙具、完成作品并提交给心理老师。',
    'sec-7': '教职员工查看完整报告与家长/学生版的差异，以及打印、导出和分享。',
    'sec-8': '家长/学生免登录查看的脱敏范围、链接生命周期和使用边界。',
    'sec-9': '按登录、后台、学生测评、报告和分享分类的排查表。',
    'sec-10': '账号、密码、心理数据和日常检查的底线要求。',
    'sec-a': '线下登记账号开通、调岗、停用和删除，不记录明文密码。',
    'sec-b': '把高频任务压缩成一张可打印的速查表。',
    'sec-c': '记录手册版本与后续修订。',
    'sec-d': '可单独打印给学生：登录、完成、提交、退出四步。',
}


def escape(text):
    return html.escape(str(text), quote=False)


def paragraph_text(p):
    return ''.join(run.text for run in p.runs).replace('\u00a0', ' ').strip()


def run_markup(p):
    chunks = []
    for run in p.runs:
        text = run.text
        if not text:
            continue
        text = escape(text).replace('\n', '<br>')
        if run.bold:
            text = '<strong>' + text + '</strong>'
        if run.italic:
            text = '<em>' + text + '</em>'
        chunks.append(text)
    return ''.join(chunks)


def heading_parts(text, level):
    text = text.replace('\u3000', ' ').strip()
    if level == 1:
        m = re.match(r'^(?:附录)?([0-9]+|[A-D])\s+(.+)$', text)
        if m:
            return m.group(1).upper(), m.group(2).strip()
        return '', text
    m = re.match(r'^([0-9]+(?:\.[0-9]+)*|[A-D]\.\d+)\s+(.+)$', text)
    if m:
        return m.group(1), m.group(2).strip()
    return '', text


def chapter_id(number):
    return 'sec-' + number.lower() if number else 'sec-x'


def table_widths(table):
    widths = []
    for cell in table.rows[0].cells:
        width = cell.width.cm if cell.width is not None else 0
        widths.append(width)
    if not any(widths):
        widths = [1] * len(table.columns)
    total = sum(widths)
    percents = [round(w / total * 100, 2) for w in widths]
    diff = round(100 - sum(percents), 2)
    if percents:
        percents[-1] = round(percents[-1] + diff, 2)
    return percents


def cell_html(cell):
    pieces = []
    for p in cell.paragraphs:
        text = run_markup(p).strip()
        if text:
            pieces.append(text)
    return '<br>'.join(pieces)


def table_html(table, caption):
    if len(table.rows) == 1 and len(table.columns) == 1:
        paras = [paragraph_text(p) for p in table.rows[0].cells[0].paragraphs if paragraph_text(p)]
        if not paras:
            return ''
        title = escape(paras[0])
        rest = ''.join('<p>' + escape(x) + '</p>' for x in paras[1:])
        return '<aside class="callout"><b>' + title + '</b>' + rest + '</aside>'

    colgroup = ''.join('<col style="width:%.2f%%">' % w for w in table_widths(table))
    header = table.rows[0]
    body_rows = table.rows[1:]
    head_cells = ''.join(
        '<th scope="col">' + (cell_html(cell) or '&#160;') + '</th>'
        for cell in header.cells
    )
    rows = []
    for row in body_rows:
        cells = ''.join(
            '<td>' + (cell_html(cell) or '&#160;') + '</td>'
            for cell in row.cells
        )
        rows.append('<tr>' + cells + '</tr>')
    caption_html = '<p class="table-caption">' + escape(caption) + '</p>' if caption else ''
    return (
        '<div class="table-block">' + caption_html +
        '<div class="table-wrap"><table><colgroup>' + colgroup + '</colgroup>' +
        '<thead><tr>' + head_cells + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></div>'
    )


def image_html(filename, caption, number):
    caption = caption or '系统界面截图'
    alt = caption.replace('\u3000', ' ')
    return (
        '<figure class="shot" id="fig-%d">'
        '<button type="button" aria-label="放大查看：%s">'
        '<img src="assets/%s" alt="%s" loading="lazy">'
        '<span class="zoom-hint">点击放大</span>'
        '</button>'
        '<figcaption>%s</figcaption>'
        '</figure>'
    ) % (number, html.escape(alt, quote=True), filename, html.escape(alt, quote=True), escape(caption))


def load_blocks(doc):
    blocks = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn('w:p'):
            blocks.append(Paragraph(child, doc))
        elif child.tag == qn('w:tbl'):
            blocks.append(Table(child, doc))
    return blocks


def collect_headings(blocks):
    started = False
    chapters = []
    current = None
    for block in blocks:
        if not isinstance(block, Paragraph):
            continue
        style = block.style.name if block.style is not None else ''
        if not started:
            if style == 'Heading 1' and re.match(r'^1\s+', block.text.replace('\u3000', ' ').strip()):
                started = True
            else:
                continue
        if style == 'Heading 1':
            number, title = heading_parts(block.text, 1)
            current = {'id': chapter_id(number), 'number': number, 'title': title, 'h2': []}
            chapters.append(current)
        elif style == 'Heading 2' and current is not None:
            number, title = heading_parts(block.text, 2)
            current['h2'].append({'number': number, 'title': title, 'id': current['id'] + '-' + str(len(current['h2']) + 1)})
    return chapters


def build_nav(chapters):
    out = []
    for chapter in chapters:
        sub = ''.join(
            '<a href="#%s">%s</a>' % (item['id'], escape((item['number'] + ' ' if item['number'] else '') + item['title']))
            for item in chapter['h2']
        )
        out.append(
            '<div class="nav-group" data-target="%s">'
            '<a class="nav-chapter" href="#%s"><span class="nav-no">%s</span><span class="nav-title">%s</span></a>'
            '<div class="nav-sub">%s</div>'
            '</div>' % (chapter['id'], chapter['id'], escape(chapter['number'] or '·'), escape(chapter['title']), sub)
        )
    return ''.join(out)


def build_content(blocks, chapters):
    chapter_by_id = {c['id']: c for c in chapters}
    chapter_order = [c['id'] for c in chapters]
    current_id = None
    section_parts = []
    chapter_buffer = []
    figure_no = 0
    image_index = 0
    pending_caption = ''

    def flush():
        nonlocal chapter_buffer, current_id
        if current_id is None:
            chapter_buffer = []
            return
        section_parts.append(''.join(chapter_buffer))
        chapter_buffer = []

    started = False
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if isinstance(block, Paragraph):
            style = block.style.name if block.style is not None else ''
            heading_text = block.text.replace('\u3000', ' ').strip()

            if not started:
                if style == 'Heading 1' and re.match(r'^1\s+', heading_text):
                    started = True
                else:
                    i += 1
                    continue

            if style == 'Heading 1':
                number, title = heading_parts(block.text, 1)
                cid = chapter_id(number)
                flush()
                current_id = cid
                chapter = chapter_by_id.get(cid, {'h2': []})
                kicker = 'CHAPTER ' + str(int(number)).zfill(2) if number.isdigit() else 'APPENDIX ' + number
                chips = ''
                if chapter['h2']:
                    chips = '<div class="chapter-index">' + ''.join(
                        '<a href="#%s">%s</a>' % (item['id'], escape((item['number'] + ' ' if item['number'] else '') + item['title']))
                        for item in chapter['h2']
                    ) + '</div>'
                lead = CHAPTER_LEADS.get(cid, '')
                chapter_buffer.append(
                    '<section class="chapter" id="%s">'
                    '<header class="chapter-head">'
                    '<div class="chapter-no">%s</div>'
                    '<div><div class="chapter-kicker">%s / INTERNAL MANUAL</div>'
                    '<h1>%s</h1>%s</div>'
                    '</header>%s'
                    % (
                        cid,
                        escape(str(int(number)).zfill(2) if number.isdigit() else number),
                        kicker,
                        escape(title),
                        ('<p class="chapter-summary">' + escape(lead) + '</p>') if lead else '',
                        chips,
                    )
                )
                i += 1
                continue

            if style == 'Heading 2' and current_id:
                number, title = heading_parts(block.text, 2)
                chapter = chapter_by_id.get(current_id)
                h2 = None
                if chapter:
                    for item in chapter['h2']:
                        if item['number'] == number and item['title'] == title:
                            h2 = item
                            break
                hid = h2['id'] if h2 else current_id + '-h2-' + str(len(chapter_buffer))
                chapter_buffer.append(
                    '<h2 id="%s"><span class="h2-no">%s</span><span class="h2-title">%s</span></h2>'
                    % (hid, escape(number or '·'), escape(title))
                )
                i += 1
                continue

            if style == 'Heading 3' and current_id:
                chapter_buffer.append('<h3>' + escape(paragraph_text(block)) + '</h3>')
                i += 1
                continue

            if style == 'Caption':
                text = paragraph_text(block)
                if text.startswith('表') and i + 1 < len(blocks) and isinstance(blocks[i + 1], Table):
                    pending_caption = text
                i += 1
                continue

            if block._p.findall('.//' + qn('a:blip')):
                caption = ''
                if i + 1 < len(blocks) and isinstance(blocks[i + 1], Paragraph):
                    nxt = blocks[i + 1]
                    nxt_style = nxt.style.name if nxt.style is not None else ''
                    if nxt_style == 'Caption' and paragraph_text(nxt).startswith('图'):
                        caption = paragraph_text(nxt)
                        i += 1
                if image_index < len(FIG_FILES):
                    figure_no += 1
                    chapter_buffer.append(image_html(FIG_FILES[image_index], caption, figure_no))
                    image_index += 1
                i += 1
                continue

            markup = run_markup(block)
            if markup.strip():
                chapter_buffer.append('<p>' + markup + '</p>')
            i += 1
            continue

        if isinstance(block, Table):
            if current_id:
                chapter_buffer.append(table_html(block, pending_caption))
                pending_caption = ''
            i += 1
            continue

        i += 1

    flush()
    return ''.join(section_parts), figure_no, image_index


def main():
    doc = Document(str(DOCX))
    blocks = load_blocks(doc)
    chapters = collect_headings(blocks)
    content, figure_no, image_index = build_content(blocks, chapters)

    head = (BUILD / 'head.html').read_text(encoding='utf-8')
    tail = (BUILD / 'tail.html').read_text(encoding='utf-8')
    nav = build_nav(chapters)
    final = head.replace('{{NAV}}', nav).replace('{{CONTENT}}', content) + tail
    OUTPUT.write_text(final, encoding='utf-8', newline='\n')
    print('output:', OUTPUT)
    print('chapters:', len(chapters), 'figures:', figure_no, 'images:', image_index, 'bytes:', OUTPUT.stat().st_size)


if __name__ == '__main__':
    main()
