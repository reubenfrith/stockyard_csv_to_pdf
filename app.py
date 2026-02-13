import csv
import io
import re
import zipfile
from dataclasses import dataclass, field

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SaleRecord:
    date: str
    item: str
    qty: int
    net_sales: float


@dataclass
class ArtistReport:
    name: str
    commission_rate: float  # 0.20 means 20%
    sales: list[SaleRecord] = field(default_factory=list)

    @property
    def total_net_sales(self) -> float:
        return round(sum(s.net_sales for s in self.sales), 2)

    @property
    def gallery_commission(self) -> float:
        return round(self.total_net_sales * self.commission_rate, 2)

    @property
    def artist_payout(self) -> float:
        return round(self.total_net_sales - self.gallery_commission, 2)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_COMMISSION_RE = re.compile(r"\((\d+)\)\s*$")


def parse_category(category: str) -> tuple[str, float]:
    """Extract (artist_name, commission_rate) from a Category string.

    Returns ("", 0.0) for None / empty categories (sentinel value).
    """
    if not category or category.strip().lower() == "none":
        return ("", 0.0)

    match = _COMMISSION_RE.search(category)
    if match:
        rate = int(match.group(1)) / 100.0
        name_part = category[: match.start()].strip()
    else:
        rate = 0.30  # default 30%
        name_part = category.strip()

    # Strip leading '#' prefix used by some gallery categories
    name_part = name_part.lstrip("#").strip()

    return (name_part, rate)


def parse_dollar(value: str) -> float:
    """Parse a dollar string like '$25.00' or '-$2.00' into a float."""
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# CSV processing
# ---------------------------------------------------------------------------


def process_csv(
    rows: list[dict],
) -> tuple[dict[str, ArtistReport], list[dict]]:
    """Group CSV rows by artist and build commission reports.

    Returns (artists_dict, skipped_rows) where skipped_rows are rows with
    None/empty Category.
    """
    artists: dict[str, ArtistReport] = {}
    skipped: list[dict] = []

    for row in rows:
        category = row.get("Category", "").strip()
        artist_name, commission_rate = parse_category(category)

        if not artist_name:
            skipped.append(row)
            continue

        net_sales = parse_dollar(row.get("Net Sales", ""))

        try:
            qty = int(float(row.get("Qty", "0") or "0"))
        except ValueError:
            qty = 0

        sale = SaleRecord(
            date=row.get("Date", ""),
            item=row.get("Item", ""),
            qty=qty,
            net_sales=net_sales,
        )

        if artist_name not in artists:
            artists[artist_name] = ArtistReport(
                name=artist_name,
                commission_rate=commission_rate,
            )
        artists[artist_name].sales.append(sale)

    # Sort each artist's sales by date
    for report in artists.values():
        report.sales.sort(key=lambda s: s.date)

    return (artists, skipped)


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------


def _sanitise_filename(name: str) -> str:
    """Turn an artist name into a safe filename component."""
    safe = re.sub(r"[^\w\s-]", "", name)  # strip non-alphanumeric (keep spaces/hyphens)
    safe = re.sub(r"\s+", "_", safe.strip())  # spaces → underscores
    return safe or "unknown"


def generate_artist_pdf(report: ArtistReport) -> bytes:
    """Generate a single-artist PDF with their sales and commission summary."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()

    artist_heading = ParagraphStyle(
        "ArtistHeading",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
    )
    summary_style = ParagraphStyle(
        "SummaryText",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=4,
    )

    elements: list = []

    # Artist header
    elements.append(Paragraph(report.name, artist_heading))
    elements.append(
        Paragraph(
            f"Commission Rate: {report.commission_rate:.0%}",
            summary_style,
        )
    )
    elements.append(Spacer(1, 12))

    # Sales table
    col_widths = [80, 250, 40, 90]
    header_row = ["Date", "Item", "Qty", "Net Sales"]
    table_data: list[list[str]] = [header_row]

    for sale in report.sales:
        table_data.append(
            [
                sale.date,
                sale.item,
                str(sale.qty),
                f"${sale.net_sales:,.2f}",
            ]
        )

    # Totals row
    table_data.append(["", "TOTAL", "", f"${report.total_net_sales:,.2f}"])

    table = Table(table_data, colWidths=col_widths)
    style_commands = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        # Data rows
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        # Totals row
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        # Grid and padding
        ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Alternating row shading for data rows
    for row_idx in range(2, len(table_data) - 1, 2):
        style_commands.append(
            (
                "BACKGROUND",
                (0, row_idx),
                (-1, row_idx),
                colors.HexColor("#f0f3f5"),
            )
        )
    table.setStyle(TableStyle(style_commands))
    elements.append(table)
    elements.append(Spacer(1, 20))

    # Commission summary
    elements.append(
        Paragraph(
            f"Total Net Sales: <b>${report.total_net_sales:,.2f}</b>",
            summary_style,
        )
    )
    elements.append(
        Paragraph(
            f"Gallery Commission ({report.commission_rate:.0%}): "
            f"<b>${report.gallery_commission:,.2f}</b>",
            summary_style,
        )
    )
    elements.append(
        Paragraph(
            f"Artist Payout: <b>${report.artist_payout:,.2f}</b>",
            summary_style,
        )
    )

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


def generate_all_pdfs_zip(artists: dict[str, ArtistReport]) -> bytes:
    """Generate a ZIP containing one PDF per artist inside a 'commission_reports/' folder."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for report in sorted(artists.values(), key=lambda a: a.name):
            pdf_bytes = generate_artist_pdf(report)
            filename = f"commission_reports/{_sanitise_filename(report.name)}.pdf"
            zf.writestr(filename, pdf_bytes)
    zip_buffer.seek(0)
    return zip_buffer.read()


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="CSV to PDF Commission Report", page_icon=":art:")
st.title("Art Gallery Commission Report Generator")

uploaded_file = st.file_uploader("Upload a Square POS CSV export", type=["csv"])

if uploaded_file is not None:
    # Decode with fallback
    raw = uploaded_file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)

    # Validate required columns
    required_columns = {"Category", "Net Sales", "Item", "Qty", "Date"}
    if rows:
        actual_columns = set(rows[0].keys())
        missing = required_columns - actual_columns
        if missing:
            st.error(
                f"CSV is missing required columns: {', '.join(sorted(missing))}. "
                "Please upload a Square POS export with the expected format."
            )
            st.stop()

    # Process data
    artists, skipped_rows = process_csv(rows)

    # Warning for None/empty categories
    if skipped_rows:
        with st.expander(
            f":warning: {len(skipped_rows)} row(s) with no artist category",
            expanded=True,
        ):
            st.caption(
                "These rows have 'None' or empty Category and are excluded "
                "from artist reports."
            )
            st.dataframe(
                [
                    {
                        "Date": r.get("Date", ""),
                        "Item": r.get("Item", ""),
                        "Net Sales": r.get("Net Sales", ""),
                    }
                    for r in skipped_rows
                ]
            )

    # Summary table
    if artists:
        st.subheader("Commission Summary")
        summary_data = []
        for report in sorted(artists.values(), key=lambda a: a.name):
            summary_data.append(
                {
                    "Artist": report.name,
                    "Commission Rate": f"{report.commission_rate:.0%}",
                    "Total Net Sales": f"${report.total_net_sales:,.2f}",
                    "Gallery Commission": f"${report.gallery_commission:,.2f}",
                    "Artist Payout": f"${report.artist_payout:,.2f}",
                }
            )
        st.dataframe(summary_data, use_container_width=True)

        # ZIP download (one PDF per artist in a folder)
        zip_bytes = generate_all_pdfs_zip(artists)
        st.download_button(
            label="Download All Reports (ZIP)",
            data=zip_bytes,
            file_name="commission_reports.zip",
            mime="application/zip",
        )
    elif not skipped_rows:
        st.warning("No data found in the uploaded CSV.")
