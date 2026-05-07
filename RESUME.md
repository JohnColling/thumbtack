# RESUME — Current Session State

**Date:** 2026-05-07  ~11:15 PM AEST  
**Session started:** Wednesday, May 06, 2026 10:59 PM

---

## Active Project: OpenMonoAgent.ai Investigation

**Primary focus:** Deep inspection of OpenMono.ai (StartupHakk's C#/.NET local AI coding agent) + troubleshooting GPU issue on John's PC.

### What We Did This Session
1. **Installed OpenMono.ai** on the server (CPU mode — no GPU on R2-D2). Repo at `~/openmono.ai`.
   - Downloaded Qwen3.6-35B-A3B-UD-Q4_K_XL model (~21 GB)
   - llama-server running in Docker on port 7474, healthy
   - Agent Docker image built
   - `openmono` CLI symlinked to `~/.local/bin/openmono`
   - Verified: `curl -s http://127.0.0.1:7474/v1/chat/completions` works, returns valid chat responses

2. **Deep code inspection** completed. Full report saved to:
   - `AI Memory/Projects/OpenMonoAgent.ai/Deep Inspection Report.md`
   - Key findings: HttpClient leak, LSP flaws, naïve token counting, no graceful shutdown
   - Architecture: .NET 10, 161 C# files, ~808 KB, Docker sandboxing, Roslyn + LSP tools

3. **John's PC (GPU) issue:** Agent hangs on "thinking". Screenshot mentioned but **not uploaded** yet.
   - **Likely cause:** `nvidia-container-toolkit` not installed on PC → llama-server container can't see GPU → hangs
   - **Next step:** John to run three diagnostic commands on his PC (see below) and upload the screenshot

### Immediate Next Action
**Awaiting diagnostics from John's PC.** The screenshot and these commands will reveal the root cause:
```bash
# 1. Server health
curl -s http://localhost:7474/health

# 2. Container logs
docker logs docker-llama-server-1 2>&1 | tail -50

# 3. Can Docker see GPU?
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

---

## ThumbTack Status
- **No code changes** this session (git clean)
- Service running on 10.0.0.53:3456
- **Top open task:** Design external API so outside services/programs can trigger agents, tasks, or events inside the application (from Things to Do.md)

---

## Quick Commands Reference
- OpenMono server status: `docker ps | grep llama`
- OpenMono logs: `docker logs docker-llama-server-1 2>&1 | tail -30`
- OpenMono test API: `curl -s http://127.0.0.1:7474/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"default","messages":[{"role":"user","content":"Say hello in exactly 3 words"}]}'`

---

*Context hibernation protocol active. On wake, read this file + Things to Do.md, then proceed.*
