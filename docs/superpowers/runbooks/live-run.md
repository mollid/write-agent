# Live-LLM end-to-end run

Set API keys in env, then:

    NOVEL_LIVE=1 novel init demo --genre fantasy
    cd demo
    NOVEL_LIVE=1 novel premise "a thief who steals time"
    NOVEL_LIVE=1 novel write-chapter 3
    novel export

This exercises real models (configured in project.config.yaml). Not run in CI.