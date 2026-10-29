# Delta

Delta measures how a coding agent's choices affect the cost of future change (ETC, "Easier To Change"). An agent builds a project across many stages, each extending its own prior code. Delta records tokens, cost, and time per stage. See [DESIGN.md](DESIGN.md) for the full design.

## Quick Start

```
docker build -t delta-sandbox:dev images
python -m delta check ecommerce
python -m delta run --harness codex --model gpt-6-luna
python -m delta spend
```

API keys go in `.env` at the repo root (`OpenAI_API_Key=...`).

### SlopCodeBench problems

```
python -m delta fetch-scb                  # checks out scb-problems at a pinned commit into vendor/
python -m delta image scb:file_backup      # builds the problem image
python -m delta check scb:file_backup      # reference solutions must pass
python -m delta run --harness codex --model gpt-6-luna --problem scb:file_backup
```

## Acknowledgments

Delta builds on **SlopCodeBench** (SCBench) by Orlanski et al. Delta's design follows SCBench's iterative setup. The agent extends its own code across checkpoints, specs describe only black-box behavior, and tests stay hidden. Delta also reimplements SCBench's test-category rules (core, error, functionality, regression) and spec conventions so it can run SCBench problems unchanged.

Delta can run problems from the SCBench problem set, [gabeorlanski/scb-problems](https://github.com/gabeorlanski/scb-problems). Delta does not include or redistribute those files. `python -m delta fetch-scb` downloads them from the original repository at a pinned commit, and they remain under their authors' license (Apache License 2.0 per the repository's `LICENSE` file).

Problem files carry canary strings marking them as benchmark data that should never appear in training corpora. Delta leaves the files unmodified. It strips the canary from the spec text shown to agents, as SCBench's own runner does.

The `eve_*` problems bundle EVE Online static data from CCP Games, which CCP's own terms govern.

If you use Delta with SCBench problems, please cite SCBench:

```bibtex
@misc{Orlanski2026SlopCodeBench,
  author = {Orlanski, Gabriel and Roy, Devjeet and Yun, Alexander and Shin, Changho and Gu, Alex and Ge, Albert and Adila, Dyah and Roberts, Nicholas and Sala, Frederic and Albarghouthi, Aws},
  title = {{SlopCodeBench: Benchmarking How Coding Agents Degrade Over Long-Horizon Iterative Tasks}},
  year = {2026},
  eprint = {2603.24755},
  archivePrefix = {arXiv},
  primaryClass = {cs.SE},
  url = {https://arxiv.org/abs/2603.24755}
}
```

SCBench is not affiliated with Delta and does not endorse it.
