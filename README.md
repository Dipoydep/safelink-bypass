# Safelink Bypass API

Bypass safelink sfl.gl / safelinku / khaddavi via serverless function.

## Deploy
1. Push repo ke GitHub
2. Import ke vercel.com
3. Deploy

## Endpoint
GET /api/bypass?url=https://sfl.gl/xxxxx

## Response
{
  "success": true,
  "url": "https://target-asli.com",
  "method": "hidden-in-html",
  "candidates": ["..."],
  "logs": ["..."]
}

## Local Test
pip install cloudscraper
python api/bypass.py "https://sfl.gl/xxxxx"
