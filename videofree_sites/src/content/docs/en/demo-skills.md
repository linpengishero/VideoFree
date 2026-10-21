---
title: 'Demo Skills: Install & Use'
lead: The repository ships two demo skills under examples/skills/ — dialogue-video-skill and OpenMontage — that hand the whole video pipeline to an agent. They are production instructions and tooling for an agent, not double-click software. Finish the installation guide first, then connect them to the agent you already use.
order: 6
---

## <span class="no">1</span>Prepare two complete skill folders

In the VideoFree Studio repository, `examples/skills/` contains the two folders below. Copy both whole folders into your agent's skills directory — never copy only `SKILL.md`.

```text
Your agent's skills directory/
├─ dialogue-video-skill/  ← planning, storyboarding, generation, review
└─ openmontage/           ← editing, mixing, final composition
```

Media generation is called directly through VideoFree Studio's MCP by the lead producer role — configure it as in step 3 below; no other media-calling skill is needed.

Skill locations differ per agent — just ask it "where is your skills directory?". Keep OpenMontage's full source, AGPL-3.0 license, and copyright notices intact.

## <span class="no">2</span>Have the agent check its environment

Generation happens on the VideoFree Studio side; editing and composition happen in the agent's runtime. So the agent side also needs Python 3.10+, FFmpeg, ffprobe, and OpenMontage's Python dependencies. Send it this:

> Install the videofree demo video skills for me. I have prepared the dialogue-video-skill and openmontage folders. First confirm this agent's skills directory, then copy the complete folders preserving all assets, scripts, and licenses. Check Python 3.10+, FFmpeg, and ffprobe, and install openmontage's requirements.txt in the Python environment you actually use. Configure my videofree MCP for the lead producer: [gateway URL, e.g. http://192.168.50.8:8765/mcp]. Refresh skill discovery, validate fixed assets and media capabilities. Check only — do not generate anything or spend quota yet.

Node dependencies for Remotion or HyperFrames are only needed if you choose those renderers. Plain FFmpeg composition does not require installing every renderer up front.

## <span class="no">3</span>Connect VideoFree Studio's MCP

Add an HTTP MCP server to the agent's configuration, name it `videofree`, and set the URL to `http://<gateway-machine-IP>:8765/mcp`. It starts with VideoFree Studio — no extra service.

On the same machine `http://127.0.0.1:8765/mcp` works. From another machine you must use the real LAN IP, e.g. `http://192.168.50.8:8765/mcp` — do not copy the example blindly.

Have the agent check health, list capabilities, and list preset voices first. Results coming back means the connection works. Configuration formats differ per platform — follow your agent's HTTP MCP documentation and `dialogue-video-skill/references/install.md`; one platform's JSON is not a universal format.

::note
This demo video skill pack uses MCP. Choose an agent that supports HTTP MCP, and configure the media service only for the lead producer.
::

## <span class="no">4</span>Refresh skills and run the readiness check

Refresh or restart the agent so it picks up the new skills. Have it check fixed character assets, the toolchain, and download permissions, then run OpenMontage's preflight check. Without image, video, or audio review capability it must state the limitation — never pretend a review passed.

With subagents, only the lead producer connects to media generation tools; give script, storyboard, and QA roles permissions per task so no subagent submits generations freely. Permission isolation belongs in host settings — skill text alone cannot enforce it.

## <span class="no">5</span>Make one short first, then go fully automatic

For the first run, send this example and confirm characters, voices, generation, and composition all work:

> Using dialogue-video-skill, make a dialogue-explainer video between a robot and a young man on "why the sky is blue", 30 seconds, 9:16, keep the dialogue, no subtitles. Tell me the production plan, expected generation count, and whether a second take is needed — wait for my confirmation before generating.

Only grant full automation after that succeeds. State the topic, duration, aspect ratio, generation or cost ceiling, second-take policy, and which steps need your confirmation. If something ambiguous appears — like an unclear reference identity — the agent must still stop and ask.

Example: "Plan approved, at most 12 generation submissions, second takes allowed; continue automatically where unambiguous, ask me first about identity or budget issues."

## <span class="no">6</span>Find the results and keep production records

Generated media lives in the VideoFree Studio project. Have the agent create a dedicated project first and submit with its project ID, so automated output never mixes with your manual generations.

The final edited cut is saved in the agent's agreed delivery directory, not necessarily the VideoFree Studio project folder. Ask where it will output before starting. Use a fresh working directory per production and keep plans, asset lists, and review records — never pile finished cuts into the skill folders.

To take this skill apart — final-package-first, stage gates, guarded submission — and build your own fully automated pipeline for a different format, see [Long-Video Skill Development](/en/guide/skill-dev/).
