from app.core.utils import html_to_text, slugify, text_to_html


def test_slugify_basic():
    assert slugify("Hello World!") == "hello-world"


def test_html_to_text_breaks_and_entities():
    assert html_to_text("<b>Hi</b><br>there") == "Hi\nthere"
    assert html_to_text("<div>a</div><div>b</div>").splitlines() == ["a", "b"]
    assert html_to_text("Tom &amp; Jerry &lt;x&gt;") == "Tom & Jerry <x>"
    assert html_to_text("") == ""


def test_text_to_html_escapes_and_preserves_newlines():
    assert text_to_html("a & b\n<script>") == "a &amp; b<br>&lt;script&gt;"
