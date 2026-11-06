# -*- coding: utf-8 -*-
"""用 Word COM 把投稿版 docx 导出为 PDF 并回报页数/字数。

注意：Word 的存盘/导出在沙箱内会被拦截（进程直接退出），必须在沙箱外运行。
用法：python 代码/export_pdf.py v1.5
"""
import os, sys
import win32com.client as win32

ver = sys.argv[1] if len(sys.argv) > 1 else "v1.5"
base = os.path.abspath("论文实验")
docx = os.path.join(base, f"投稿版_IEEE_Access_{ver}.docx")
pdf = os.path.join(base, f"投稿版_IEEE_Access_{ver}.pdf")

app = win32.DispatchEx("Word.Application")
app.Visible = False
app.DisplayAlerts = 0
doc = app.Documents.Open(docx, False, True)
pages = doc.ComputeStatistics(2)
words = doc.ComputeStatistics(0)
doc.SaveAs(pdf, 17)
doc.Close(False)
app.Quit()
print(f"PAGES={pages} WORDS={words} PDF={os.path.getsize(pdf)}")
