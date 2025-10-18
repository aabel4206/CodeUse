# CodeUse Tool

A comprehensive code analysis and execution tool with modular architecture.

## Project Structure & Team Ownership

```
tool/
├── main.py                    # 🎯 MAIN ENTRY POINT (Shared)
├── __init__.py               # 📦 PACKAGE INIT (Shared)
├── orchestrator/             # 👤 PERSON A - ORCHESTRATION
│   ├── loop.py               # Main workflow coordination
│   ├── state.py              # Application state management
│   └── prompts/
│       ├── __init__.py
│       └── system_prompts.py # LLM prompt templates
├── executor/                 # 👤 PERSON B - CODE EXECUTION
│   ├── __init__.py
│   └── executor.py           # Safe code execution engine
├── llm_parse/                # 👤 PERSON C - CODE ANALYSIS
│   ├── __init__.py
│   └── parser.py             # LLM-based code parsing
├── reporter/                 # 👤 PERSON D - REPORTING
│   ├── __init__.py
│   └── reporter.py           # Report generation
└── runs/                     # 📁 SHARED STORAGE
    └── .gitkeep             # Execution results & reports
```

## Team Responsibilities

### 👤 Person A - Orchestrator
- **Primary Focus**: Workflow coordination and state management
- **Key Files**: `orchestrator/loop.py`, `orchestrator/state.py`
- **Responsibilities**:
  - Main application loop and workflow coordination
  - State management and data persistence
  - Integration between all modules
  - LLM prompt management

### 👤 Person B - Executor  
- **Primary Focus**: Safe code execution and sandboxing
- **Key Files**: `executor/executor.py`
- **Responsibilities**:
  - Safe execution of user code
  - Multi-language support (Python, JavaScript, Bash, PowerShell)
  - Security and sandboxing
  - Resource monitoring and timeout handling

### 👤 Person C - LLM Parser
- **Primary Focus**: Code analysis and understanding
- **Key Files**: `llm_parse/parser.py`
- **Responsibilities**:
  - Code structure analysis
  - Function and class extraction
  - Issue detection and suggestions
  - Language-specific parsing logic

### 👤 Person D - Reporter
- **Primary Focus**: Report generation and output formatting
- **Key Files**: `reporter/reporter.py`
- **Responsibilities**:
  - Comprehensive report generation
  - Multiple output formats (JSON, Markdown)
  - Result visualization and formatting
  - Report management and retrieval

## Getting Started

1. Each team member should focus on their assigned module
2. Use the existing interfaces and data structures
3. The `main.py` file coordinates all modules
4. Results are stored in the `runs/` directory

## Development Notes

- All modules are Python packages with proper `__init__.py` files
- Type hints and documentation are included for better collaboration
- Error handling and logging should be consistent across modules
- The orchestrator manages the flow between all components
