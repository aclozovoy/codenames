# Codenames

A web-based implementation of the Codenames board game where you can play against an
LLM, or watch LLMs play against each other. Model calls run on AWS Bedrock, with a
preference for cheap models during development and testing.

## Status

🚧 Early development — building out the core game mechanics first.

## Roadmap

- [ ] Core game engine (board generation, turns, clues, guessing, win/loss)
- [ ] Game engine tests
- [ ] LLM players (spymaster + operative) via AWS Bedrock
- [ ] Web UI (human vs. LLM, LLM vs. LLM spectating)
