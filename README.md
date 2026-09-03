# Quotation MCP server

An MCP server that creates quotations from client details and grouped
line items. It calculates section totals, tax, additional charges,
rounded totals, and payment schedules, then returns the quotation data
and a Markdown representation. A separate MCP tool generates a PDF from
the quotation data.

## Project layout

```
Quotation_MCP/
├── app/
│   ├── config.py                    # Application constants
│   ├── models.py                    # Pydantic request and response models
│   ├── main.py                      # MCP server and exposed tools
│   ├── quotation/
│   │   ├── calculations.py          # Quotation calculations
│   │   ├── formatter.py              # Markdown formatting
│   │   └── quotation.py              # Quotation orchestration
│   └── file_generator/
│       └── pdf_generator.py          # PDF generation
└── requirements.txt
```

The code is organized into models, calculations, formatting, file
generation, and MCP tool registration so each part has a focused role.

## What the MCP server does

The server exposes two tools:

- `create_quotation` accepts client information, sections, line items,
  tax, additional charges, and payment stages. It returns calculated
  quotation data and Markdown text.
- `generate_pdf` accepts quotation data and returns the path to the
  generated PDF file.

Line-item amounts are calculated according to the selected unit:

| Unit  | Area / Qty       | Amount              |
|-------|------------------|----------------------|
| `sft` | `width * height` | `width * height * qty * rate` |
| `Nos` | `qty`            | `qty * rate`         |
| `LS`  | `qty` (usually 1)| `rate` (flat lump sum)|

The server then calculates section totals, the overall total, tax,
additional charges, the final total, a rounded total, and payment-stage
amounts.

## Setup

Create and activate a virtual environment:

```bash
python -m venv env
```

On Windows PowerShell:

```powershell
.\env\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
source env/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

## Running the server

```bash
python -m app.main
```

This starts the FastMCP server using streamable HTTP. Connect an
MCP-compatible client to the server URL provided by FastMCP.

## Tool input

`create_quotation` accepts client details, sections containing line
items, a tax percentage, an additional charge, and an optional payment
split. A line item can use `sft`, `Nos`, or `LS` as its unit.

Example payload:

```json
{
  "client_name": "Example Client",
  "location": "Example Location",
  "sections": [
    {
      "name": "Section A",
      "items": [
        {"description": "Item A", "width": 10, "height": 5, "unit": "sft", "rate": 100}
      ]
    }
  ],
  "gst_percent": 0,
  "transport_charge": 0,
  "payment_split": [
    {"label": "Initial Payment", "percent": 50},
    {"label": "Final Payment", "percent": 50}
  ]
}
```

The server is stateless: each request produces a fresh quotation.
