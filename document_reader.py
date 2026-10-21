"""Bounded DOCX semantic reader; no external resource resolution or scripts."""
import zipfile
import xml.etree.ElementTree as ET
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W='{'+NS['w']+'}'
def read_docx(file):
    with zipfile.ZipFile(file) as archive:
        info=archive.getinfo('word/document.xml')
        if info.file_size>4000000:raise ValueError('Word document exceeds the reader size limit.')
        root=ET.fromstring(archive.read(info));body=root.find('w:body',NS)
        if body is None:return []
        def paragraph(node):
            style=node.find('w:pPr/w:pStyle',NS);name=style.get(W+'val','') if style is not None else ''
            runs=[]
            for r in node.iter(W+'r'):
                text=''.join((t.text or '') if t.tag==W+'t' else '\n' if t.tag==W+'br' else '\t' if t.tag==W+'tab' else '' for t in r)
                if text:runs.append({'text':text,'bold':r.find('w:rPr/w:b',NS) is not None,'italic':r.find('w:rPr/w:i',NS) is not None})
            return {'type':'heading' if name.lower().startswith(('heading','title')) else 'paragraph','runs':runs}
        blocks=[]
        for node in list(body)[:2000]:
            if node.tag==W+'p':blocks.append(paragraph(node))
            elif node.tag==W+'tbl':blocks.append({'type':'table','rows':[[[paragraph(p) for p in c.findall('w:p',NS)] for c in r.findall('w:tc',NS)[:30]] for r in node.findall('w:tr',NS)[:200]]})
        return blocks
