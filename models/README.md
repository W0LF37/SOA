# Local Model Files

This project expects the local Ollama model files to be placed in this folder when running the full LLM demo.

The GGUF model files are intentionally not committed to GitHub because they are several gigabytes each and exceed normal repository limits.

Expected local files:

```text
models/Qwen3.5-9B-Q5_K_M.gguf
models/Qwen_Qwen3-8B-Q5_K_M.gguf
models/Modelfile
```

The repository includes `models/Modelfile`. Add the `.gguf` files locally before running:

```powershell
ollama create ai-project-manager-planner -f models/Modelfile
```
