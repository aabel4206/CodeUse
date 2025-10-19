# Environment Variables Setup

This document outlines the environment variables that have been moved from hardcoded values to environment variables for better security and configuration management.

## Changes Made

### 1. API Keys Moved to Environment Variables

**Before (Hardcoded):**
- Gemini API Key: `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`
- OpenRouter API Key: `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`
- OpenAI API Key (fallback): `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`

**After (Environment Variables):**
- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`

### 2. Configuration Values Moved to Environment Variables

**Before (Hardcoded):**
- Default target URL: `http://localhost:5173`
- HTTP Referer: `http://localhost`
- OpenRouter Model: `anthropic/claude-3.5-sonnet`

**After (Environment Variables):**
- `DEFAULT_TARGET_URL`
- `HTTP_REFERER`
- `OPENROUTER_MODEL`

### 3. Files Modified

1. **`tool/main.py`**
   - Added dotenv loading
   - Updated Gemini API key to use `GEMINI_API_KEY`
   - Updated OpenRouter API key to use `OPENROUTER_API_KEY`
   - Updated default target URL to use `DEFAULT_TARGET_URL`

2. **`tool/orchestrator/loop.py`**
   - Updated OpenRouter API key to use `OPENROUTER_API_KEY` with `OPENAI_API_KEY` fallback
   - Updated default target URL to use `DEFAULT_TARGET_URL`

3. **`tool/orchestrator/adapter.py`**
   - Added dotenv loading
   - Updated HTTP Referer to use `HTTP_REFERER`

4. **`tool/test_main.py`**
   - Updated test to handle environment variable for default target URL
   - Added `os` import

5. **`env.example`**
   - Created template file with all environment variables

6. **`README.md`**
   - Added environment setup section

## Environment Variables Reference

| Variable | Description | Default Value | Required |
|----------|-------------|---------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | - | Yes |
| `OPENROUTER_API_KEY` | OpenRouter API key | - | Yes |
| `OPENAI_API_KEY` | OpenAI API key (fallback) | - | No |
| `OPENROUTER_MODEL` | OpenRouter model to use | `anthropic/claude-3.5-sonnet` | No |
| `DEFAULT_TARGET_URL` | Default target URL for testing | `http://localhost:5173` | No |
| `EXECUTOR_BASE_URL` | Executor service base URL | `http://localhost:8001` | No |
| `HTTP_REFERER` | HTTP Referer for OpenRouter requests | `http://localhost` | No |

## Setup Instructions

1. Copy the environment template:
   ```bash
   cp env.example .env
   ```

2. Edit `.env` file and add your actual API keys:
   ```bash
   GEMINI_API_KEY=your_actual_gemini_key
   OPENROUTER_API_KEY=your_actual_openrouter_key
   OPENAI_API_KEY=your_actual_openai_key
   ```

3. The application will automatically load these environment variables on startup.

## Security Notes

- The `.env` file is already in `.gitignore` to prevent accidental commits
- Never commit actual API keys to version control
- Use the `env.example` file as a template for other developers
- Consider using a secrets management system for production deployments
