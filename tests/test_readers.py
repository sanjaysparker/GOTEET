import base64
import zipfile
from unittest.mock import patch
import pytest
import document_reader
import mail_reader
import drive_reader
import media_library
import settings

def encoded(s):return base64.urlsafe_b64encode(s.encode()).decode()

def test_mail_text_blocks_tracking_and_scripts():
    body={'mimeType':'text/html','body':{'data':encoded('<p>Hello</p><script>secret()</script><img src="https://tracker.test">World')}}
    text,files,truncated=mail_reader.body_text(body)
    assert 'Hello' in text and 'World' in text
    assert 'secret' not in text and 'tracker' not in text and not files and not truncated

def test_multipart_prefers_plain_and_bounds_total():
    part=lambda value:{'mimeType':'text/plain','body':{'data':encoded(value)}}
    body={'parts':[part('plain'),{'mimeType':'text/html','body':{'data':encoded('<p>duplicate</p>')}},{'filename':'file.pdf','body':{'size':10}}]}
    assert mail_reader.body_text(body)[0]=='plain'
    assert mail_reader.body_text(body)[1][0]['name']=='file.pdf'
    with pytest.raises(ValueError):mail_reader.body_text({'parts':[part('x'*600000),part('x'*600000)]})

def test_word_semantic_reader(tmp_path):
    file=tmp_path/'sample.docx'
    with zipfile.ZipFile(file,'w') as z:z.writestr('word/document.xml','''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t>GOTEET sample</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>''')
    blocks=document_reader.read_docx(file)
    assert blocks[0]['type']=='heading' and blocks[0]['runs'][0]['bold']
    assert blocks[1]['rows'][0][0][0]['runs'][0]['text']=='Cell'

def test_drive_metadata_permission_cannot_download():
    with patch('settings.require'),patch('google_auth.read_secret',return_value={'scope':'https://www.googleapis.com/auth/drive.metadata.readonly'}),patch('httpx.Client') as client:
        with pytest.raises(ValueError,match='read access'):drive_reader.preview('valid_id')
        client.assert_not_called()

def test_cloud_preview_account_boundary(tmp_path):
    file=tmp_path/'private.png';file.write_bytes(b'x');media_library.CLOUD_PREVIEWS[str(file)]='first'
    with patch('settings.require'),patch('google_auth.read_secret',return_value={'profile':{'sub':'other'}}):
        with pytest.raises(PermissionError):media_library.indexed(str(file))
    media_library.CLOUD_PREVIEWS.pop(str(file))

def test_theme_validation(tmp_path):
    with patch.object(settings,'DATA',tmp_path):
        assert settings.save({'theme':'light','accent':'#123456'})['theme']=='light'
        with pytest.raises(ValueError):settings.save({'theme':'invalid'})
