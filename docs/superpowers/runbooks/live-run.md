# Live-LLM end-to-end run

Set API keys in env, then:

    NOVEL_LIVE=1 uv run novel init demo --genre fantasy
    cd demo
    NOVEL_LIVE=1 uv run novel premise "a thief who steals time"
    NOVEL_LIVE=1 uv run novel write-chapter 3
    uv run novel export

`write-chapter` takes the chapter count as a positional argument (`write-chapter 3`).
Re-running `write-chapter N` continues from the last written chapter instead of overwriting.

This exercises real models (configured in project.config.yaml). Not run in CI.
When `NOVEL_LIVE=1`, chapter/outline gates prompt for approval interactively.
For a no-LLM smoke run, omit `NOVEL_LIVE=1` (demo mode uses canned responses).