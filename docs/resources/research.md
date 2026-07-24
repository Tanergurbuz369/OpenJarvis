---
title: Research & Related Work
description: Papers, sibling tools, blog posts, and the related-work bibliography behind OpenJarvis and the Intelligence Per Watt research program
---

# Research & Related Work

OpenJarvis is one of the outputs of **[Intelligence Per Watt](https://www.intelligence-per-watt.ai/)** (IPW), a research
initiative at [Hazy Research](https://hazyresearch.stanford.edu/) and the
[Scaling Intelligence Lab](https://scalingintelligence.stanford.edu/) at Stanford SAIL, studying how efficiently local
models can substitute for cloud AI. This page collects the papers, sibling tools, blog posts, and related-work
bibliography from that program, so the research grounding behind this project's design choices (local-first,
energy/FLOPs/latency/cost as first-class eval axes) is easy to find in one place.

!!! note "Source & accuracy"
    Compiled from [intelligence-per-watt.ai](https://www.intelligence-per-watt.ai/), which is the canonical, actively
    maintained source — check it directly for the current/complete list. Spot-check a link before citing it in formal
    work.

## Papers

| Paper | Authors | Links |
|---|---|---|
| **Intelligence Per Watt: Measuring Intelligence Efficiency of Local AI** | Jon Saad-Falcon*, Avanika Narayan*, et al. | [arXiv:2511.07885](https://arxiv.org/abs/2511.07885) · [blog](https://hazyresearch.stanford.edu/blog/2025-11-11-ipw) |
| **OpenJarvis: Personal AI, On Personal Devices** | Jon Saad-Falcon*, Avanika Narayan*, John Hennessy, Christopher Ré, Azalia Mirhoseini | [arXiv:2605.17172](https://arxiv.org/abs/2605.17172) · [blog](https://scalingintelligence.stanford.edu/blogs/openjarvis/) |
| **Maximizing American Gross Domestic Intelligence with Hybrid Inference** | Jared Dunnmon*, Avanika Narayan*, Jon Saad-Falcon*, Chris Ré | [blog](https://hazyresearch.stanford.edu/blog/2025-11-28-gdi) |
| **Minions: Cost-efficient Collaboration Between On-device and Cloud Language Models** | Avanika Narayan*, Dan Biderman*, Sabri Eyuboglu*, et al. | [arXiv:2502.15964](https://arxiv.org/abs/2502.15964) · [blog](https://hazyresearch.stanford.edu/blog/2025-02-24-minions) |
| **Archon: An Architecture Search Framework for Inference-Time Techniques** | Jon Saad-Falcon, Adrian Gamarra Lafuente, Shlok Natarajan, et al. | [arXiv:2409.15254](https://arxiv.org/abs/2409.15254) |
| **Weaver: Shrinking the Generation-Verification Gap with Weak Verifiers** | Jon Saad-Falcon, E. Kelly Buchanan, Mayee F. Chen, et al. | [arXiv:2506.18203](https://arxiv.org/abs/2506.18203) |
| **China's AI Heist** (Foreign Affairs essay) | Jared Dunnmon, Avanika Narayan, Jon Saad-Falcon | [Foreign Affairs](https://www.foreignaffairs.com/china/chinas-ai-heist) |

## Sibling Tools

Separate repositories from the same research program. Not vendored into this repo — they're independent codebases,
linked here for context:

- **[IPW Profiling Harness](https://github.com/HazyResearch/intelligence-per-watt)** — open-source benchmarking suite that profiles LLM inference across NVIDIA, AMD, and Apple Silicon.
- **[Minions](https://github.com/HazyResearch/minions)** — reference implementation for local-cloud LM collaboration protocols.
- **[Archon](https://github.com/ScalingIntelligence/Archon)** — architecture search framework for inference-time technique configurations.
- **[Weaver](https://github.com/HazyResearch/scaling-verification)** — toolkit for building weighted ensembles of weak verifiers to evaluate LM outputs.

## Blog Posts

- [From Minions to OpenJarvis: A Retrospective on Two Years in Local AI](https://hazyresearch.stanford.edu/blog/2026-05-15-minions-to-openjarvis-retrospective) — May 15, 2026
- [OpenJarvis: Personal AI, On Personal Devices](https://scalingintelligence.stanford.edu/blogs/openjarvis/) — Mar 12, 2026
- [Intelligence Per Watt: A Study of Local Intelligence Efficiency](https://hazyresearch.stanford.edu/blog/2025-11-11-ipw) — Nov 11, 2025

## Related Work

The broader bibliography IPW draws on, organized by topic.

### Algorithmic Progress & Efficiency Measurement

- [Algorithmic Progress in Language Models](https://arxiv.org/abs/2311.06602)
- [How Fast is Algorithmic Progress in AI Inference?](https://www.lesswrong.com/posts/ssNSCaug5p3xnNDSd/how-fast-is-algorithmic-progress-in-ai-inference)
- [LLM Inference Price Trends (Epoch AI)](https://epoch.ai/data-insights/llm-inference-price-trends)
- [Compute Equivalent Gain (CEG) Accounting](https://www.emergentmind.com/topics/compute-equivalent-gain-ceg-accounting)

### Energy Measurement & Benchmarking

- [Zeus: ML Energy Measurement](https://ml.energy/zeus/)
- [AI Energy Score (Hugging Face)](https://huggingface.github.io/AIEnergyScore/)
- [MLCommons Inference Benchmark](https://github.com/mlcommons/inference)
- [MLCommons Inference Policies](https://github.com/mlcommons/inference_policies)

### Economic Impact of AI

- [The Simple Macroeconomics of AI (Acemoglu)](https://economics.mit.edu/sites/default/files/2024-04/The%20Simple%20Macroeconomics%20of%20AI.pdf)
- [How AI is Transforming Work at Anthropic](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic)
- [Remote Labor AI](https://www.remotelabor.ai/)

### Benchmarks & Evaluation

- [GDPVal Dataset](https://huggingface.co/datasets/openai/gdpval/viewer/default/train)
- [Snorkel AI Leaderboard](https://leaderboard.snorkel.ai/)
- [APEX Benchmark](https://arxiv.org/abs/2505.06371)

### Inference Systems & Edge Computing

- [MIT Iceberg](https://iceberg.mit.edu/)
- [LLM Router](https://github.com/ulab-uiuc/LLMRouter)
- [Efficient Inference Routing](https://arxiv.org/abs/2402.16844)

---

For the full, current bibliography (this page lists a representative subset), see the
[**Related**](https://www.intelligence-per-watt.ai/) section on intelligence-per-watt.ai directly.
