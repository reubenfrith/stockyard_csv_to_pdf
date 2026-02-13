# Art Gallery Commission Report Generator

Streamlit app that turns Square POS CSV exports into per-artist PDF commission reports.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens in your browser at `http://localhost:8501`. Upload a CSV and download the reports.

## How It Works

1. Upload a Square POS items export (CSV)
2. The app parses the **Category** column to extract each artist's name and commission rate
3. Sales are grouped by artist, and commission is calculated on **Net Sales**
4. Download a ZIP containing one PDF per artist in a `commission_reports/` folder

Each PDF includes a table of that artist's sales (date, item, qty, net sales) and a commission summary showing total net sales, gallery commission, and artist payout.

## CSV Format

The app expects a standard Square POS items export. The key column is **Category**, which encodes the artist name and gallery commission percentage:

| Category value | Parsed as |
|---|---|
| `KB Kate Billingsley (20)` | Artist: KB Kate Billingsley, Commission: 20% |
| `#Storytelling Through Pictures (20)` | Artist: Storytelling Through Pictures, Commission: 20% |
| `#Paddy Wenborn Archives` | Artist: Paddy Wenborn Archives, Commission: 30% (default) |
| `None` or empty | Skipped (warning shown in the app) |

**Rules:**
- Number in brackets at the end `(XX)` sets the gallery commission percentage
- No brackets defaults to **30%**
- Leading `#` is stripped from the name
- `None` or empty categories are excluded and shown as a warning

## Output

The download is a `commission_reports.zip` containing:

```
commission_reports/
  AE_Ann_Emerton.pdf
  KB_Kate_Billingsley.pdf
  SG_Sue_Gilford.pdf
  ...
```

## Project Structure

```
app.py                          # All logic: UI, parsing, PDF generation
requirements.txt                # streamlit, reportlab
sample_data/example_sales.csv   # Example CSV in Square POS format
```
