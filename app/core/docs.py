"""
@file docs.py
@brief Documentation handler for the application root
@details
Serves the HTML documentation for the API.
Sanitized to remove specific version numbers and internal architecture details
to prevent information disclosure.

@author Vectra Project
@date 2025-12-15
@version 1.0
@license AGPL-3.0
"""

from fastapi.responses import HTMLResponse

def get_root_documentation() -> str:
    """
    @brief Generate the HTML content for the root documentation page
    
    @details
    Returns a comprehensive HTML documentation page describing:
    - System overview and capabilities
    - Legal notices and licensing information
    - API usage references
    
    security: Removed specific version numbers and stack details.
    
    @return HTML string
    """
    html_content = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vectra API - Documentation</title>
        <style>
             * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }
            .header h1 { font-size: 2.5em; margin-bottom: 10px; }
            .content { padding: 40px; }
            h2 { color: #667eea; margin-top: 30px; border-bottom: 2px solid #667eea; padding-bottom: 10px; }
            h3 { color: #764ba2; margin-top: 20px; }
            p { margin-bottom: 15px; color: #555; }
            .status {
                display: inline-block;
                padding: 8px 16px;
                border-radius: 6px;
                background: #d4edda;
                color: #155724;
                font-weight: bold;
                margin: 10px 0;
            }
            .footer {
                background: #f9f9f9;
                padding: 20px;
                text-align: center;
                color: #999;
                font-size: 0.9em;
                border-top: 1px solid #eee;
            }
            .warning {
                background: #fff3cd; color: #856404; border: 1px solid #ffeaa7;
                padding: 15px; border-radius: 6px; margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌍 Vectra API</h1>
                <p>Vehicle Evacuation & Traffic Resilience</p>
            </div>
            
            <div class="content">
                <div class="status">✓ System Operational</div>
                
                <h2>📋 Overview</h2>
                <p>Vectra is a geospatial analysis platform for emergency evacuation and disaster response planning. It provides API services for road network analysis, flow simulation, and scenario management.</p>
                
                <div class="warning">
                    <strong>⚠️ Legal Notice</strong><br>
                    <p style="margin-top: 10px; font-size: 0.95em;">
                    This project uses public geospatial data from the Florida Department of Transportation (FDOT). This project is <strong>not affiliated with FDOT</strong>. Users must comply with applicable data use policies.
                    </p>
                </div>
                
                <h2>🔑 Capabilities</h2>
                <ul>
                    <li><strong>Network Analysis:</strong> Road network topology and capacity planning</li>
                    <li><strong>Simulation:</strong> Evacuation flow and contraflow analysis</li>
                    <li><strong>Scenarios:</strong> Configurable disaster response scenarios</li>
                </ul>
                
                <h2>🔌 API Access</h2>
                <p>API endpoints are available under the <code>/api</code> prefix.</p>
                <ul>
                    <li><code>GET /api/segments</code> - Retrieve road network data</li>
                    <li><code>GET /api/simulate</code> - Run flow simulations</li>
                    <li><code>GET /api/scenarios</code> - List available disaster scenarios</li>
                </ul>

                <h2>⚠️ Status & Maintenance</h2>
                 <p>System health is monitored via standard health check endpoints.</p>
            </div>
            
            <div class="footer">
                <p>Vectra Platform | Emergency Evacuation Analysis</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content
