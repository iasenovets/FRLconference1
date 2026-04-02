# FRLconference1

This repository accompanies the Springer publication:

> **"Conceptual Framework for Federated Reinforcement Learning in Network Defense"**  
> Srimali & Yi — *ICA3PP 2025, LNCS 16387* — DOI: [10.1007/978-981-95-8417-8_17](https://doi.org/10.1007/978-981-95-8417-8_17)

The paper proposes a *conceptual* FRL framework. The code reflects **two separate, partial implementations** at different stages of development. Several privacy-preservation claims made in the paper are **not implemented** in the primary code and exist only at the conceptual level. The section below maps each of the paper's five framework components to its implementation status, followed by the full gap analysis and a library-referenced improvement roadmap.

---

## Repository Structure

```
article/
  687176_1_En_17_Chapter_Author.pdf   ← authoritative Springer proof
code/
  main.py                             ← entry point (primary codebase)
  FL_train.py                         ← FRL / FedAVG / TrimmedMean / MultiKrum training loops
  AGRs.py                             ← aggregation rules: TrimmedMean, MultiKrum
  Attacks.py                          ← Byzantine attack generators
  utils.py                            ← FRL_Vote, train/test helpers
  args.py                             ← argument parser (CIFAR-10 defaults)
  eval.py                             ← top-k accuracy
  misc.py                             ← AverageMeter, init helpers
  DAPI_graph.py                       ← standalone plot of DAPI curve (Fig. 4)
  frl_workflow_blueprint1.py          ← separate end-to-end scaffold (CIC-IDS2017 + DQN + DAPI)
```

---

## Framework Overview: Five Components

The paper's conceptual architecture (Fig. 3) flows through five components. Each is described below alongside its current implementation status.

---

### Component 1 — Data Sharing Mechanism

Agents (firewalls, routers, IoT nodes) train locally on their own traffic data and transmit only model updates — weights or gradients — to a federated aggregator. Raw logs never leave the node. The global model is built via aggregation rules (FedAvg or Byzantine-robust variants) and redistributed to all agents.

| Paper claim | Implementation status |
|---|---|
| Decentralised agents train locally and share model updates, not raw data | ✅ **Implemented** — `FL_train.py` (`FRL_train`, `FedAVG`, `Mkrum`, `Tr_Mean`) |
| FedAvg aggregation | ✅ **Implemented** — `FedAVG()` in `FL_train.py` |
| Byzantine-robust aggregation (TrimmedMean, MultiKrum) | ✅ **Implemented** — `AGRs.py`, invoked in `FL_train.py` |
| Attack simulation (gradient manipulation against TrimmedMean / MultiKrum) | ✅ **Implemented** — `Attacks.py` (`our_attack_trmean`, `our_attack_mkrum`) |
| Non-IID data distribution (Dirichlet) | ✅ **Implemented** — `args.non_iid_degree` and `data` module |

> **Note:** The primary codebase runs on **CIFAR-10**, not the CIC-IDS2017 / UNSW-NB15 datasets described in the paper's experiments. The `FRL_Vote` mechanism in `utils.py` is specific to sparse-mask convolutional models (`MaskConv`) and is not a general federated-averaging scheme.

---

### Component 2 — Privacy Preserving Layer (+ DAPI) — CRITICAL GAP

This layer sits between the agents and the aggregator. The paper proposes four privacy mechanisms alongside the DAPI trust-conditioned noise schedule. This is the area of **greatest divergence** between the paper and the code.

#### What DAPI is

DAPI (Dynamic Adaptive Privacy Intensity) couples each agent's trust score directly to its differential privacy budget, rather than applying a fixed ε to all agents:

> εᵢ = β · Tᵢ^γ *(power-law form, as plotted in Fig. 4 and `DAPI_graph.py`)*

A higher trust score → higher ε → less Gaussian noise injected → update contributes more cleanly to the global model. A lower trust score → lower ε → more noise → heavier masking, reducing the influence of potentially compromised nodes.

**Original DAPI workflow chain (conceptual paper):**
> higher trust → higher ε → less noise added to gradient → **plaintext gradient** → aggregator reads everything

The aggregator sees every gradient; privacy comes only from noise magnitude. There is no encryption protecting the gradient in transit or during aggregation.

**Enhanced CipherFRL workflow chain (proposed extension):**
> higher trust → higher ε → less noise added to gradient → **noisy gradient encrypted under CKKS** → ciphertext transmitted → **aggregator computes trust-weighted average homomorphically, never decrypts** → encrypted aggregate broadcast → **each agent decrypts locally** → policy updated

CKKS encryption inserts between the noise injection step and transmission, and persists through aggregation. The trust weight is applied as a plaintext scalar multiplication on the ciphertext — the aggregator applies each agent's weight without seeing what it scales. What the aggregator learns is limited to: how many agents participated, and what the public trust weights are.

#### DAPI formulation inconsistency

Two different mathematical forms appear across the artefacts and must be resolved before implementation:

| Source | Formula | Form |
|---|---|---|
| Paper §5.2, Eq. 5 / Table 2 | ε_i = β·T_i + γ | **Linear** |
| `DAPI_graph.py` (Fig. 4 plot) | ε_i = β·T_i^γ | **Power-law** |
| `frl_workflow_blueprint1.py` | ε_i = β·T_i + γ | **Linear** (matches Eq. 5, not the plot) |

The power-law form is recommended: it provides finer discrimination at low trust scores, which is important for the security property that low-trust agents face meaningfully stronger noise.

This is the area of greatest divergence between the paper and the code.

#### 3a. Differential Privacy (DP)

| Paper claim                                                                                                        | Implementation status                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DP noise injected into local gradients before transmission; privacy budget ε calibrated via ε = Δf / (α·λ) (Eq. 1) | ❌ **Not implemented** in the primary codebase (`FL_train.py`). No Gaussian or Laplace mechanism, no gradient clipping for DP, no privacy budget tracking.                                                                                                                                                                                                                                                  |
| DP noise via DAPI (ε_i = β·T_i^γ) (Fig. 4 formula and DAPI_graph.py)                                               | ⚠️ **Partially implemented** — `frl_workflow_blueprint1.py` applies Gaussian noise scaled to 1/ε after trust-score-derived ε (`DAPIController.add_dp_noise_to_weights`). The formula used is the linear form ε_i = β·T_i + γ (Eq. 5 in the paper), **not** the power-law ε = β·T^γ used in `DAPI_graph.py`. These two formulations are inconsistent with each other. The primary codebase has no DP at all. |

#### 3b. Homomorphic Encryption (HE / Paillier)

| Paper claim                                                                                               | Implementation status                                                                                                         |
| --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Paillier cryptosystem used for lightweight encryption of gradients; secure aggregation without decryption | ❌ **Not implemented anywhere** in the codebase. No HE library is imported or invoked. This is a conceptual description only. |

#### 3c. Secure Aggregation (SecAgg)

| Paper claim                                                                      | Implementation status                                                                                                                                                |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Secure aggregation protocol to protect updates during transmission to the server | ❌ **Not implemented anywhere** in the codebase. Aggregation in both codebases is performed in plaintext (mean / trimmed-mean / multi-krum over clear-text tensors). |

#### 3d. Secure Multi-Party Computation (SMPC)

| Paper claim                                                                               | Implementation status                                                                             |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| SMPC allows agents to collectively compute global models without revealing private inputs | ❌ **Not implemented anywhere** in the codebase. No SMPC library (e.g., CrypTen, PySyft) is used. |


#### Privacy mechanism implementation status

| Mechanism | Paper section | `FL_train.py` (primary) | `frl_workflow_blueprint1.py` (scaffold) |
|---|---|---|---|
| Differential Privacy | §3, §5.2 | ❌ absent | ⚠️ Gaussian noise proxy (linear DAPI, no formal DP accounting) |
| Homomorphic Encryption (Paillier / CKKS) | §3.1, §4.3 | ❌ absent | ❌ absent |
| Secure Aggregation | §3.3 Table 1 | ❌ absent | ❌ absent |
| SMPC | §3.3 Table 1 | ❌ absent | ❌ absent |
| Trust-conditioned privacy (DAPI) | §5.2 | ❌ absent | ⚠️ partial (linear form, no HE/SecAgg integration) |

---

### Component 3 — Communication Protocols

In-process Python function calls simulate all communication in both codebases. No real network layer exists.

| Paper claim | Implementation status |
|---|---|
| TLS / mTLS encrypted channels | ❌ **Not implemented** — all communication is in-process |
| Retry mechanism, version control, anomaly filtering (Eq. 2, 3, 4) | ❌ **Not implemented** beyond the anomaly z-score in the blueprint |
| Gradient quantisation / sparsification | ❌ **Not implemented** |

---

### Component 4 — Reinforcement Learning Core

Each agent runs a local RL policy observing local network state, receives rewards for correct defense decisions, and trains locally before sharing updates.

| Paper claim | Implementation status |
|---|---|
| Agents learn defensive policies through RL | ⚠️ **Partial** — `frl_workflow_blueprint1.py` provides `DQNAgent` with a 4-action defense environment (allow / monitor / throttle / block). The primary codebase (`FL_train.py`) uses supervised classification, not RL. |
| Network intrusion detection environment (CIC-IDS2017) | ⚠️ **Blueprint only** — `frl_workflow_blueprint1.py` preprocesses CIC-IDS2017 but is not integrated with `main.py` |

---

### Component 5 — Trust Management

Agents accumulate trust scores based on historical contribution quality. Low-trust agents receive stronger privacy controls or are excluded from aggregation rounds. Trust feeds directly into DAPI.

| Paper claim | Implementation status |
|---|---|
| Dynamic trust scores updated per round based on model accuracy, update stability, and peer evaluation | ⚠️ **Partial** — `DAPIController.update_trust()` in the blueprint uses reward, loss, update norm, and anomaly score. Primary codebase has no trust scoring. |
| Low-trust nodes excluded from future rounds | ⚠️ **Partial** — low-trust clients receive higher noise but are not explicitly excluded from rounds in either codebase |
| Anomaly-based filtering of updates (Eq. 4) | ✅ **Partially implemented** — `FederatedAggregator.score_anomaly()` computes z-score distances; `AGRs.py` handles Byzantine filtering via TrimmedMean / MultiKrum |

---

## Experimental Results Gap

The paper presents Table 1 comparing DP, DP+Paillier, SecAgg, HE, and SMPC configurations on CIC-IDS2017. **None of these configurations are reproducible from the provided code** because HE, SecAgg, and SMPC are not implemented, the primary codebase uses CIFAR-10, and the blueprint covers only the DP+DAPI path.

---

## Recommended Improvements

### Improvement 1 — Differential Privacy with Formal Accounting (Component 2)

Integrate a proper DP library into `FL_train.py` to add gradient clipping and Gaussian/Laplace noise injection with correct ε/δ accounting. The blueprint's `DAPIController.add_dp_noise_to_weights` is a manual Gaussian proxy without sensitivity analysis or formal privacy guarantees.

**Recommended library:** [`opacus`](https://github.com/pytorch/opacus) — PyTorch-native DP training with per-sample gradient clipping and a moment accountant for tracking the privacy budget across rounds. Also resolve the DAPI formula inconsistency (Improvement 5) as a prerequisite.

---

### Improvement 2 — CKKS-Encrypted Gradient Aggregation (Component 2)

Replace the plaintext gradient channel with CKKS homomorphic encryption so the aggregator never sees individual agent updates. This directly enables the enhanced DAPI chain described in Component 2 above.

**Recommended library:** [**TenSEAL**](https://github.com/OpenMined/TenSEAL) — a Python library for homomorphic encryption operations on tensors, built on top of Microsoft SEAL. It supports CKKS (real-valued vectors, suited to floating-point gradients) and BFV (integer vectors). Install via `pip install tenseal`.

Why TenSEAL fits this use case:
- `ts.ckks_vector` encrypts a flat list of floats into a CKKS ciphertext directly, matching the gradient tensor representation in `frl_workflow_blueprint1.py`
- Ciphertext addition and plaintext scalar multiplication are natively supported — the only two operations needed for trust-weighted FedAvg (multiplicative depth 1)
- The `TenSEALContext` object manages key generation, scale parameters, and modulus chains without manual polynomial arithmetic
- Serialisation via Protocol Buffers is built in, enabling ciphertext transmission once a real network layer (Component 3) is added

Example context setup for the FRL setting (25 agents, DQN gradient ~50k parameters):
```python
import tenseal as ts

context = ts.context(
    ts.SCHEME_TYPE.CKKS,
    poly_modulus_degree=8192,        # 4096 slots per ciphertext
    coeff_mod_bit_sizes=[60, 30, 60] # depth-1 circuit, 128-bit security
)
context.global_scale = 2**30
secret_key = context.secret_key()
context.make_context_public()  # strip secret key before sharing with aggregator
```

> **Note on Paillier:** The paper mentions Paillier as a lightweight encryption option. Paillier only supports integer arithmetic and requires quantising floating-point gradients. CKKS handles real-valued gradients natively and is the better fit. A Paillier implementation is available via [`python-paillier`](https://github.com/data61/python-paillier) if integer-quantised gradients are acceptable in a future variant.

---

### Improvement 3 — Secure Aggregation (Component 2)

Implement a masking-based SecAgg protocol so that even without HE, individual plaintext updates are never visible to the aggregator. In SecAgg, agents add pairwise random masks to their updates; the masks cancel in the sum, revealing only the aggregate.

**Recommended library:** [**NssMPClib**](https://github.com/XidianNSS/NssMPClib) — a Python/PyTorch MPC library from Xidian University NSS Lab based on arithmetic secret sharing and function secret sharing, with semi-honest security.

Why NssMPClib fits the FRL aggregation setting:
- `SecretTensor` wraps PyTorch tensors and supports additive secret sharing across two parties (`Party2PC`), which maps directly to the agent ↔ aggregator topology in FRL
- Supports both 32-bit and 64-bit ring arithmetic; floating-point gradients are handled via fixed-point scaling (`SCALE_BIT` in `configs.json`)
- The semi-honest security model matches the honest-but-curious aggregator assumption stated in the paper

Install: `pip install -e . --no-build-isolation` from the cloned repository. Pre-computed parameters for MPC operations must be generated separately before use (see the repository README for the parameter generation step).

---

### Improvement 4 — SMPC for Secure Gradient Verification (Component 2)

The paper proposes SMPC for scenarios where agents or the aggregator need to jointly compute statistics on gradients — such as norm-checking for Byzantine filtering — without any party seeing individual inputs in plaintext.

**Recommended library:** [**EzPC / CrypTFlow**](https://github.com/mpc-msri/EzPC) — a Microsoft Research suite of tools for secure machine learning using semi-honest 2PC protocols. It includes the EzPC language, the SCI library (OT-based 2PC for fixed-point arithmetic), and Beacon for secure training of feed-forward and convolutional networks.

Why EzPC fits the SMPC component:
- The SCI library implements 2PC protocols for gradient norms and comparison operations — exactly what is needed for Byzantine filtering without plaintext exposure, replacing the current `score_anomaly()` z-score filter in `FederatedAggregator`
- The Beacon component supports secure 2PC training of feed-forward networks with floating-point protocols, which could be adapted to the DQN local training step
- EzPC has been applied to ResNet-50 and DenseNet-121 secure inference, making it directly relevant to the neural network gradient computation in FRL
- Docker images are available (`docker pull ezpc/ezpc:latest`) for easier setup

**Practical note:** EzPC requires C++ compilation and is the most complex of the three libraries listed here. It is best introduced after Improvements 2 and 3 are in place.

---

### Improvement 5 — DAPI Formula Alignment (Component 2)

Choose one canonical DAPI formula and apply it consistently:

| Artefact | Current formula | Required change |
|---|---|---|
| Paper §5.2 Eq. 5 / Table 2 | ε_i = β·T_i + γ (linear) | Update to power-law |
| `DAPI_graph.py` | ε_i = β·T_i^γ (power-law) | Already correct |
| `frl_workflow_blueprint1.py` `DAPIController.compute_privacy_budget` | ε_i = β·T_i + γ (linear) | Update to power-law |

The power-law form is recommended as it matches the published Fig. 4 and provides stronger differentiation at low trust scores.

---

### Improvement 6 — Dataset Alignment (Components 1 and 4)

Replace CIFAR-10 in the primary codebase with CIC-IDS2017 or UNSW-NB15, or document explicitly that the primary codebase is a proof-of-concept on a proxy dataset. The blueprint already preprocesses CIC-IDS2017; consolidating the two codebases addresses this gap.

---

### Improvement 7 — Code Consolidation (All Components)

`frl_workflow_blueprint1.py` and `main.py`/`FL_train.py` are two disconnected implementations with different datasets, model types, and privacy mechanisms. Merge them into a single configurable pipeline, or label each clearly with its scope and limitations.

---

### Improvement 8 — Table 1 Reproducibility (Component 2)

Add experiment scripts that reproduce the Table 1 privacy–accuracy trade-off results for each configuration: DP only, DP+Paillier, SecAgg only, DP+SecAgg, HE only (Paillier), and SMPC. These scripts become feasible once Improvements 2–4 are implemented.

---

## Priority Order

| Step | Improvement | Library | Effort |
|---|---|---|---|
| 1 | Fix DAPI formula (Improvement 5) | — | Trivial |
| 2 | CKKS gradient encryption (Improvement 2) | [TenSEAL](https://github.com/OpenMined/TenSEAL) | Low — pip install, Python only |
| 3 | DP with formal accounting (Improvement 1) | `opacus` | Low — pip install, PyTorch native |
| 4 | Secure Aggregation (Improvement 3) | [NssMPClib](https://github.com/XidianNSS/NssMPClib) | Medium — requires parameter generation |
| 5 | SMPC anomaly filtering (Improvement 4) | [EzPC](https://github.com/mpc-msri/EzPC) | High — C++ build, Docker recommended |
| 6 | Dataset / code consolidation (Improvements 6–7) | — | Medium |
| 7 | Table 1 reproducibility scripts (Improvement 8) | — | Depends on steps 2–5 |

---

## Quick-Start (Primary Codebase)

```bash
python main.py \
  --set CIFAR10 \
  --FL_type FRL \
  --nClients 1000 \
  --at_fractions 0.1 \
  --round_nclients 25 \
  --FL_global_epochs 1000 \
  --data_loc /path/to/CIFAR10
```

Available `--FL_type` options: `FRL`, `FedAVG`, `trimmedMean`, `Mkrum`.

> **No privacy mechanisms (DP, HE, SecAgg, SMPC) are active in this command.** The code trains with plaintext gradient/score updates only.

---

## Quick-Start (Blueprint / CIC-IDS2017 Scaffold)

```bash
# Place MachineLearningCSV.zip in /content/ (Colab) or update cfg.zip_path
python frl_workflow_blueprint1.py
```

This runs a DQN-based FRL loop over CIC-IDS2017 with trust scoring and Gaussian DP noise (linear DAPI). HE, SecAgg, and SMPC are **not active**.

---

## Citation

```bibtex
@inproceedings{srimali2026frl,
  author    = {Srimali, Rajapaksha R. Mudiyanselage Piyumi Madhubhashini and Yi, YinXue},
  title     = {Conceptual Framework for Federated Reinforcement Learning in Network Defense},
  booktitle = {Algorithms and Architectures for Parallel Processing (ICA3PP 2025)},
  series    = {LNCS},
  volume    = {16387},
  year      = {2026},
  doi       = {10.1007/978-981-95-8417-8_17}
}
```

---

## License

See `LICENSE`.