from types import SimpleNamespace

from open_webui.utils.pdf_generator import PDFGenerator


def _generator():
    return PDFGenerator(SimpleNamespace(title="test", messages=[]))


def test_pdf_model_label_prefers_visible_model_name():
    generator = _generator()

    assert (
        generator._format_model_label(
            {"model": "d7f188cd.gpt-5.4", "modelName": "gpt-5.4 | 佬友测试"}
        )
        == "gpt-5.4 | 佬友测试"
    )


def test_pdf_model_label_strips_internal_prefix_for_legacy_messages():
    generator = _generator()

    assert generator._format_model_label({"model": "d7f188cd.gpt-5.4"}) == "gpt-5.4"
    assert generator._format_model_label({"model": "gpt-5.4"}) == "gpt-5.4"


class _FakePdf:
    def __init__(self):
        self.fonts = []

    def add_font(self, family, style, path):
        self.fonts.append((family, style, path))


def test_pdf_font_family_registers_italic_styles_even_without_italic_file(tmp_path):
    generator = _generator()
    regular = tmp_path / "HarmonyOS_SansSC_Regular.ttf"
    bold = tmp_path / "HarmonyOS_SansSC_Bold.ttf"
    regular.write_bytes(b"regular")
    bold.write_bytes(b"bold")

    generator._materialize_font_for_fpdf = lambda font_path: font_path
    pdf = _FakePdf()

    generator._register_pdf_font_family(pdf, "HaloSansSC", regular=regular, bold=bold)

    assert pdf.fonts == [
        ("HaloSansSC", "", str(regular)),
        ("HaloSansSC", "b", str(bold)),
        ("HaloSansSC", "i", str(regular)),
        ("HaloSansSC", "bi", str(bold)),
    ]
