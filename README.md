# FRLconference1

This repository accompanies the Springer publication:

> **"Conceptual Framework for Federated Reinforcement Learning in Network Defense"**
> Srimali & Yi — _ICA3PP 2025, LNCS 16387_ — DOI: [10.1007/978-981-95-8417-8_17](https://doi.org/10.1007/978-981-95-8417-8_17)

The paper proposes a _conceptual_ FRL framework. The code in this repository reflects **two separate, partial implementations** at different stages of development. The section below maps each paper claim to its implementation status. Readers should note that several privacy-preservation claims made in the paper are **not implemented** in the primary code and exist only at the conceptual level.

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

## Paper Claims vs. Code Implementation Status

### 1. Federated Learning Core (FL training loop)

| Paper claim                                                               | Implementation status                                                                                        |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Decentralised agents train locally and share model updates, not raw data  | ✅ **Implemented** — `FL_train.py` (`FRL_train`, `FedAVG`, `Mkrum`, `Tr_Mean`)                               |
| FedAvg aggregation                                                        | ✅ **Implemented** — `FedAVG()` in `FL_train.py`                                                             |
| Byzantine-robust aggregation (TrimmedMean, MultiKrum)                     | ✅ **Implemented** — `AGRs.py`, invoked in `FL_train.py`                                                     |
| Attack simulation (gradient manipulation against TrimmedMean / MultiKrum) | ✅ **Implemented** — `Attacks.py` (`our_attack_trmean`, `our_attack_mkrum`)                                  |
| Non-IID data distribution (Dirichlet)                                     | ✅ **Implemented** — referenced via `args.non_iid_degree` and `data` module (not included in uploaded files) |

> **Note:** The primary codebase (`main.py` / `FL_train.py`) runs on **CIFAR-10** image classification, not the network-intrusion datasets (CIC-IDS2017 / UNSW-NB15) described in the paper's experimental section. The FRL "ranking vote" mechanism (`FRL_Vote` in `utils.py`) is specific to sparse-mask convolutional models (`MaskConv`) and is not a general federated-averaging scheme.

---

### 2. Reinforcement Learning Component

| Paper claim                                           | Implementation status                                                                                                                                                                                                                         |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agents learn defensive policies through RL            | ⚠️ **Partially implemented** — `frl_workflow_blueprint1.py` provides a DQN agent (`DQNAgent`) with a 4-action network-defence environment (`NetworkDefenseEnv`). The primary codebase (`FL_train.py`) uses supervised classification, not RL. |
| Network intrusion detection environment (CIC-IDS2017) | ⚠️ **Blueprint only** — `frl_workflow_blueprint1.py` provides preprocessing for CIC-IDS2017, but this file is a scaffold; it is **not** integrated with `main.py`.                                                                            |

---

### 3. Privacy-Preservation Claims — **CRITICAL GAP**

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

#### Summary table — privacy mechanisms

| Mechanism                         | Paper Section | `FL_train.py` (primary) | `frl_workflow_blueprint1.py` (scaffold)            |
| --------------------------------- | ------------- | ----------------------- | -------------------------------------------------- |
| Differential Privacy              | §3, §5.2      | ❌ absent               | ⚠️ Gaussian noise proxy (linear DAPI)              |
| Homomorphic Encryption (Paillier) | §3.1, §4.3    | ❌ absent               | ❌ absent                                          |
| Secure Aggregation                | §3.3 Table 1  | ❌ absent               | ❌ absent                                          |
| SMPC                              | §3.3 Table 1  | ❌ absent               | ❌ absent                                          |
| Trust-conditioned privacy (DAPI)  | §5.2          | ❌ absent               | ⚠️ partial (linear form, no HE/SecAgg integration) |

---

### 4. Trust Management

| Paper claim                                                                                           | Implementation status                                                                                                                                                                                                                 |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dynamic trust scores updated per round based on model accuracy, update stability, and peer evaluation | ⚠️ **Partial** — `frl_workflow_blueprint1.py` implements `DAPIController.update_trust()` using reward, loss, update norm, and anomaly score. This approximates the conceptual description. The primary codebase has no trust scoring. |
| Low-trust nodes excluded from future rounds                                                           | ⚠️ **Partial** — low-trust clients receive higher noise but are not explicitly excluded from rounds in either codebase.                                                                                                               |
| Anomaly-based filtering of updates (Eq. 4)                                                            | ✅ **Partially implemented** — `FederatedAggregator.score_anomaly()` computes z-score distances; Byzantine attack filtering in `FL_train.py` is done via TrimmedMean / MultiKrum in `AGRs.py`.                                        |

---

### 5. Communication Protocols

| Paper claim                                                       | Implementation status                                                                             |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| TLS / mTLS encrypted channels                                     | ❌ **Not implemented.** All communication is in-process Python function calls (no network layer). |
| Retry mechanism, version control, anomaly filtering (Eq. 2, 3, 4) | ❌ **Not implemented** in either codebase beyond the anomaly z-score in the blueprint.            |
| Gradient quantisation / sparsification for compression            | ❌ **Not implemented.**                                                                           |

---

### 6. Experimental Results (Table 1 — Privacy–Accuracy Trade-offs)

The paper presents Table 1 comparing DP, DP+Paillier, SecAgg, HE, and SMPC configurations on CIC-IDS2017. **None of these configurations are reproducible from the provided code** because:

- HE, SecAgg, and SMPC are not implemented.
- The primary codebase uses CIFAR-10, not CIC-IDS2017/UNSW-NB15.
- The blueprint scaffold targets CIC-IDS2017 but covers only the DP+DAPI path.

---

## DAPI Formulation Inconsistency

Two different mathematical forms of the DAPI relationship appear across the artefacts:

| Source                        | Formula         | Form                       |
| ----------------------------- | --------------- | -------------------------- |
| Paper §5.2, Eq. 5 / Table 2   | ε_i = β·T_i + γ | **Linear**                 |
| `DAPI_graph.py` (Fig. 4 plot) | ε_i = β·T_i^γ   | **Power-law**              |
| `frl_workflow_blueprint1.py`  | ε_i = β·T_i + γ | **Linear** (matches Eq. 5) |

The plot (`DAPI_graph.py`) and the paper's Fig. 4 use the power-law form, which is **not** the formula stated in Eq. 5 of the same paper, and not what the blueprint implements. This inconsistency should be resolved in both the paper and the code.

---

## Recommended Improvements

The following steps would close the gap between the paper's claims and the codebase:

1. **Differential Privacy:** Integrate a DP library (e.g., `opacus`) into `FL_train.py` to add gradient clipping and Gaussian/Laplace noise injection with proper ε/δ accounting.

2. **Homomorphic Encryption:** Integrate a library such as `TenSEAL` or `python-paillier` to encrypt local model updates before transmission to the aggregator.

3. **Secure Aggregation:** Implement a SecAgg protocol (e.g., via `PySyft` or a hand-rolled masking scheme) so that the server never sees individual plaintext updates.

4. **SMPC:** Integrate `CrypTen` or equivalent to enable collaborative computation without revealing private inputs.

5. **DAPI formula alignment:** Decide on one canonical formula (linear Eq. 5 or power-law), apply it consistently in the paper, `DAPI_graph.py`, and `frl_workflow_blueprint1.py`.

6. **Dataset alignment:** Replace CIFAR-10 in the primary codebase with CIC-IDS2017 or UNSW-NB15, or clearly document that the primary codebase is a proof-of-concept using a proxy dataset.

7. **Code consolidation:** `frl_workflow_blueprint1.py` and `main.py`/`FL_train.py` represent two disconnected codebases. Consider merging them or clearly labelling each with its purpose and limitations.

8. **Table 1 reproducibility:** Add scripts (or clearly state they do not yet exist) that reproduce the privacy–accuracy trade-off results from Table 1 under each configuration.

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
