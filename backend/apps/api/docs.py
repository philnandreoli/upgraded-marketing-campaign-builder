"""Custom-themed API documentation pages.

Overrides the default FastAPI /docs (Swagger UI) and /redoc endpoints
with CSS that matches the frontend's design system — dark surfaces,
teal primary accent, and the same typography scale.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from backend.config import get_settings

# ---------------------------------------------------------------------------
# Design tokens — mirrored from frontend/src/index.css :root (dark theme)
# ---------------------------------------------------------------------------
_BG = "#0C0F1A"
_SURFACE = "#151929"
_SURFACE_2 = "#1E2338"
_BORDER = "#2A3050"
_PRIMARY = "#0D9488"
_PRIMARY_HOVER = "#14B8A6"
_TEXT = "#E8ECF4"
_TEXT_MUTED = "#8B95AD"
_FONT_BODY = "'Switzer', 'Inter', system-ui, sans-serif"

# ---------------------------------------------------------------------------
# Custom CSS injected into Swagger UI
# ---------------------------------------------------------------------------
_SWAGGER_CSS = f"""
/* ---- base chrome ---- */
html, body {{ background: {_BG} !important; color: {_TEXT}; }}
body {{ font-family: {_FONT_BODY}; }}

.swagger-ui {{
  font-family: {_FONT_BODY};
  color: {_TEXT};
}}

/* top-bar */
.swagger-ui .topbar {{
  background: {_SURFACE} !important;
  border-bottom: 1px solid {_BORDER};
  padding: 8px 16px;
}}
.swagger-ui .topbar .download-url-wrapper input[type=text] {{
  background: {_SURFACE_2};
  color: {_TEXT};
  border: 1px solid {_BORDER};
  border-radius: 6px;
}}

/* info section */
.swagger-ui .info {{ margin: 30px 0 20px; }}
.swagger-ui .info .title {{ color: {_TEXT} !important; font-weight: 700; }}
.swagger-ui .info .description,
.swagger-ui .info .description p {{
  color: {_TEXT_MUTED};
}}
.swagger-ui .info a {{ color: {_PRIMARY} !important; }}
.swagger-ui .info a:hover {{ color: {_PRIMARY_HOVER} !important; }}

/* main wrapper */
.swagger-ui .wrapper {{ background: {_BG} !important; }}
.swagger-ui .scheme-container {{
  background: {_SURFACE} !important;
  border-radius: 8px;
  border: 1px solid {_BORDER};
  box-shadow: none;
  padding: 12px 16px;
}}

/* operation blocks */
.swagger-ui .opblock {{
  background: {_SURFACE} !important;
  border: 1px solid {_BORDER} !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  margin-bottom: 8px;
}}
.swagger-ui .opblock .opblock-summary {{
  border: none !important;
  padding: 10px 16px;
}}
.swagger-ui .opblock .opblock-summary-description {{
  color: {_TEXT_MUTED};
  font-size: 13px;
}}
.swagger-ui .opblock .opblock-summary-path,
.swagger-ui .opblock .opblock-summary-path a {{
  color: {_TEXT} !important;
}}

/* GET */
.swagger-ui .opblock.opblock-get {{
  border-color: {_PRIMARY} !important;
}}
.swagger-ui .opblock.opblock-get .opblock-summary-method {{
  background: {_PRIMARY} !important;
  border-radius: 6px;
  font-weight: 600;
}}

/* POST */
.swagger-ui .opblock.opblock-post .opblock-summary-method {{
  border-radius: 6px;
  font-weight: 600;
}}

/* DELETE */
.swagger-ui .opblock.opblock-delete .opblock-summary-method {{
  border-radius: 6px;
  font-weight: 600;
}}

/* PATCH / PUT */
.swagger-ui .opblock.opblock-patch .opblock-summary-method,
.swagger-ui .opblock.opblock-put .opblock-summary-method {{
  border-radius: 6px;
  font-weight: 600;
}}

/* expanded */
.swagger-ui .opblock-body {{
  background: {_SURFACE_2} !important;
}}
.swagger-ui .opblock-body pre {{
  background: {_BG} !important;
  color: {_TEXT};
  border: 1px solid {_BORDER};
  border-radius: 6px;
}}

/* parameter tables */
.swagger-ui table thead tr td,
.swagger-ui table thead tr th {{
  color: {_TEXT_MUTED};
  border-bottom: 1px solid {_BORDER};
}}
.swagger-ui .parameters-col_description input[type=text],
.swagger-ui .parameters-col_description select {{
  background: {_SURFACE} !important;
  color: {_TEXT};
  border: 1px solid {_BORDER};
  border-radius: 6px;
}}
.swagger-ui .parameter__name {{ color: {_TEXT}; }}
.swagger-ui .parameter__type {{ color: {_TEXT_MUTED}; }}

/* models */
.swagger-ui section.models {{
  border: 1px solid {_BORDER};
  border-radius: 8px;
  background: {_SURFACE};
}}
.swagger-ui section.models h4 {{ color: {_TEXT}; }}
.swagger-ui .model-box {{ background: {_SURFACE_2} !important; }}
.swagger-ui .model {{ color: {_TEXT}; }}

/* buttons */
.swagger-ui .btn {{
  border-radius: 6px;
  font-weight: 600;
}}
.swagger-ui .btn.authorize {{
  color: {_PRIMARY};
  border-color: {_PRIMARY};
}}
.swagger-ui .btn.authorize svg {{ fill: {_PRIMARY}; }}
.swagger-ui .btn.execute {{
  background: {_PRIMARY} !important;
  border-color: {_PRIMARY} !important;
  color: #fff !important;
}}
.swagger-ui .btn.execute:hover {{
  background: {_PRIMARY_HOVER} !important;
}}

/* responses */
.swagger-ui .responses-inner {{ background: transparent !important; }}
.swagger-ui .response-col_status {{ color: {_TEXT}; }}
.swagger-ui .response-col_description {{ color: {_TEXT_MUTED}; }}

/* tag headers */
.swagger-ui .opblock-tag {{
  color: {_TEXT} !important;
  border-bottom: 1px solid {_BORDER} !important;
}}
.swagger-ui .opblock-tag small {{ color: {_TEXT_MUTED}; }}

/* scrollbar */
.swagger-ui ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
.swagger-ui ::-webkit-scrollbar-track {{ background: {_SURFACE}; }}
.swagger-ui ::-webkit-scrollbar-thumb {{
  background: {_BORDER};
  border-radius: 3px;
}}
.swagger-ui ::-webkit-scrollbar-thumb:hover {{ background: {_TEXT_MUTED}; }}

/* misc */
.swagger-ui select {{ background: {_SURFACE_2}; color: {_TEXT}; border: 1px solid {_BORDER}; }}
.swagger-ui .loading-container .loading::after {{ color: {_PRIMARY}; }}
.swagger-ui .dialog-ux .modal-ux {{
  background: {_SURFACE};
  border: 1px solid {_BORDER};
  color: {_TEXT};
}}
.swagger-ui .dialog-ux .modal-ux-header h3 {{ color: {_TEXT}; }}
"""

# ---------------------------------------------------------------------------
# Custom CSS for ReDoc
# ---------------------------------------------------------------------------
_REDOC_CSS = f"""
body {{ background: {_BG} !important; font-family: {_FONT_BODY}; }}

/* menu panel */
.menu-content {{ background: {_SURFACE} !important; }}
[role="menuitem"] label {{ color: {_TEXT_MUTED} !important; }}
[role="menuitem"].active label {{ color: {_TEXT} !important; }}

/* main content */
.api-content {{ background: {_BG} !important; color: {_TEXT}; }}
h1, h2, h3, h4, h5, h6 {{ color: {_TEXT} !important; }}
a {{ color: {_PRIMARY} !important; }}

/* code samples panel */
.react-tabs__tab-panel {{ background: {_SURFACE_2} !important; }}
code {{ background: {_BG} !important; color: {_TEXT}; }}
"""


def register_custom_docs(app: FastAPI) -> None:
    """Register themed /docs and /redoc routes on *app*."""

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui():
        openapi_url = app.openapi_url or "/openapi.json"
        persist_authorization = (
            get_settings().app.env.strip().lower()
            in {"development", "dev", "local", "localdev"}
        )
        persist_authorization_json = json.dumps(persist_authorization)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{app.title} — API Docs</title>
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
<style>{_SWAGGER_CSS}</style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({{
  url: "{openapi_url}",
  dom_id: "#swagger-ui",
  deepLinking: true,
  persistAuthorization: {persist_authorization_json},
  displayRequestDuration: true,
  syntaxHighlight: {{ theme: "monokai" }},
  presets: [
    SwaggerUIBundle.presets.apis,
    SwaggerUIBundle.SwaggerUIStandalonePreset,
  ],
  layout: "BaseLayout",
}});
</script>
</body>
</html>"""
        return HTMLResponse(html)

    @app.get("/redoc", include_in_schema=False)
    async def custom_redoc():
        openapi_url = app.openapi_url or "/openapi.json"
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{app.title} — API Reference</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"
      rel="stylesheet" />
<style>{_REDOC_CSS}</style>
</head>
<body>
<redoc spec-url="{openapi_url}"
       hide-hostname
       theme='{{"colors":{{"primary":{{"main":"{_PRIMARY}"}}}},
               "typography":{{"fontFamily":"{_FONT_BODY}","headings":{{"fontFamily":"{_FONT_BODY}"}}}},
               "sidebar":{{"backgroundColor":"{_SURFACE}","textColor":"{_TEXT_MUTED}","activeTextColor":"{_TEXT}"}},
               "rightPanel":{{"backgroundColor":"{_SURFACE_2}"}}}}'
></redoc>
<script src="https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js"></script>
</body>
</html>"""
        return HTMLResponse(html)
