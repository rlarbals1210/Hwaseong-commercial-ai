"""공개 보고서 JSON을 텍스트·표 기반 A4 문서로 조판한다. 외부 요청 없음."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

INK = colors.HexColor("#172d46")
BLUE = colors.HexColor("#0764b0")
MUTED = colors.HexColor("#607185")
LINE = colors.HexColor("#d6e0e8")
PALE = colors.HexColor("#eef5fb")
WIDTH = A4[0] - 36 * mm


@lru_cache(maxsize=1)
def _register_fonts():
    root = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    pdfmetrics.registerFont(TTFont("ReportKR", str(root / "NanumGothic-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("ReportKR-Bold", str(root / "NanumGothic-Bold.ttf")))
    pdfmetrics.registerFontFamily("ReportKR", normal="ReportKR", bold="ReportKR-Bold")


class _NumberedCanvas(Canvas):
    """전체 페이지 수가 정해진 뒤 각 페이지에 같은 꼬리말을 출력한다."""

    def __init__(self, *args, report_ref, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []
        self._report_ref = report_ref

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setStrokeColor(LINE)
            self.line(18 * mm, 17 * mm, A4[0] - 18 * mm, 17 * mm)
            self.setFont("ReportKR", 8)
            self.setFillColor(MUTED)
            self.drawString(18 * mm, 12 * mm, f"화성시 상권 지원 · 참고자료 / {self._report_ref}")
            self.drawRightString(A4[0] - 18 * mm, 12 * mm, f"{self._pageNumber} / {total}")
            super().showPage()
        super().save()


def build_report_pdf(report: dict, *, generated_at: datetime | None = None) -> bytes:
    _register_fonts()
    created = (generated_at or datetime.now(ZoneInfo("Asia/Seoul"))).astimezone(ZoneInfo("Asia/Seoul"))
    reference = sha256(report["cache_key"].encode()).hexdigest()[:10].upper()
    styles = {
        "body": ParagraphStyle("body", fontName="ReportKR", fontSize=10, leading=16, textColor=INK, wordWrap="CJK"),
        "small": ParagraphStyle("small", fontName="ReportKR", fontSize=8.5, leading=13, textColor=MUTED, wordWrap="CJK"),
        "title": ParagraphStyle("title", fontName="ReportKR-Bold", fontSize=25, leading=34, textColor=INK, wordWrap="CJK", spaceAfter=7),
        "heading": ParagraphStyle("heading", fontName="ReportKR-Bold", fontSize=12, leading=18, textColor=BLUE, spaceAfter=9, keepWithNext=True),
        "value": ParagraphStyle("value", fontName="ReportKR-Bold", fontSize=11, leading=17, textColor=INK, alignment=TA_RIGHT, wordWrap="CJK"),
    }

    def p(text, style="body"):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])

    sections = {section["key"]: section for section in report["sections"]}

    def bullets(key):
        return [p(f"• {text}") for text in sections.get(key, {}).get("body", [])]

    def block(title, content):
        return KeepTogether([p(title, "heading"), *content, Spacer(1, 14)])

    def table(rows, widths, *, shaded=False):
        result = Table(rows, colWidths=widths, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
            ("BACKGROUND", (0, 0), (-1, -1), PALE if shaded else colors.white),
        ]))
        return result

    year, quarter = divmod(report["quarter_code"], 10)
    start_index = year * 4 + quarter - 1 - 3
    period = f"{start_index // 4}Q{start_index % 4 + 1} ~ {report['quarter_label']}"
    meta = table([
        [p("데이터 기준", "small"), p("판단 기준", "small"), p("문서 생성 (한국시간)", "small")],
        [p(report["quarter_label"]), p(report["preset"]), p(created.strftime("%Y.%m.%d %H:%M"))],
    ], [WIDTH * .27, WIDTH * .27, WIDTH * .46], shaded=True)
    meta.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0, PALE),
    ]))

    observed = table([
        [p(metric["label"]), p(metric["value"], "value")]
        for metric in report["metrics"]
    ], [WIDTH * .69, WIDTH * .31])
    observed.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f7f9fb"))]))
    assessment = table([[
        [p("상대 강점", "heading"), *bullets("strengths")],
        [p("유의할 점", "heading"), *bullets("cautions")],
    ]], [WIDTH / 2, WIDTH / 2])
    assessment.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0f7f5")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fbf6ee")),
        ("LINEAFTER", (0, 0), (0, 0), 7, colors.white),
    ]))

    story = [
        p("화성시 상권 지원  /  데이터 기반 참고자료", "small"), Spacer(1, 14),
        p("상권 요약 보고서", "title"),
        p(f"{report['area_name']} · {report['industry_name']}"), Spacer(1, 16),
        meta, Spacer(1, 21),
        block("01  한눈에 보기", bullets("overview")),
        block("02  확인된 관측 지표", [
            p(f"누적 관측 기간 {period} · 현재 점포는 {report['quarter_label']} 기준", "small"),
            Spacer(1, 8), observed, Spacer(1, 7),
            p("누적 폐업률의 분모는 4개 분기 직전 점포 수의 합입니다. 폐업 점포 수를 현재 점포 수로 나눈 값과 다릅니다.", "small"),
        ]),
        block("03  같은 업종 안의 상대 여건", [assessment]),
        p("상대 적합도는 성공 확률이나 안전 보장이 아닙니다. 관측된 폐업 현황과 현장 여건을 함께 확인하세요.", "small"),
        PageBreak(),
        p(f"{report['area_name']} · {report['industry_name']} / {report['quarter_label']}", "small"),
        Spacer(1, 14), p("현장 확인과 해석 기준", "title"), Spacer(1, 10),
        p("04  현장 확인 체크리스트", "heading"),
        p("자료에 없는 조건은 직접 확인한 뒤 검토 메모에 남겨주세요.", "small"), Spacer(1, 8),
    ]
    checklist = table([
        [p("□"), p(text)] for text in sections.get("field-check", {}).get("body", [])
    ], [26, WIDTH - 26])
    story.extend([checklist, Spacer(1, 17), p("검토 메모", "heading")])
    for _ in range(3):
        story.extend([Spacer(1, 20), HRFlowable(width="100%", thickness=.5, color=LINE)])
    story.extend([Spacer(1, 23), p("05  자료 출처와 이용 안내", "heading")])
    for source in report["sources"]:
        story.extend([p(source, "small"), Spacer(1, 5)])
    for label, text in [
        ("자료 시점", report.get("provisional_notice")),
        ("상대값 해석", report["relative_notice"]),
        ("AI 사용 공개", report["ai_disclosure"]),
        ("이용 범위", report["disclaimer"]),
    ]:
        if text:
            story.extend([p(label, "small"), p(text, "small"), Spacer(1, 8)])
    story.append(p(f"산출 규칙 {report['generated_by']} · 이 문서는 선택 조건의 자동 요약이며 현장 조사 결과나 공식 증명서가 아닙니다.", "small"))

    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=24 * mm,
        title=report["title"], author="화성시 상권 지원", subject="관측 지표와 상대 적합도 참고자료",
    )
    doc.build(story, canvasmaker=lambda *args, **kwargs: _NumberedCanvas(*args, report_ref=reference, **kwargs))
    return output.getvalue()
