from PIL import Image

from linkedin_relay.render import render_html


def test_render_html_to_png(tmp_path):
    html = "<html><body style='margin:0;width:300px;height:200px;background:#0B2545;color:#fff'>Größe & Übersicht</body></html>"
    out = render_html(html, 300, 200, tmp_path / "x.png")
    with Image.open(out) as img:
        assert img.size == (600, 400)
