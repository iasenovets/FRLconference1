"""
Adaptive Privacy-Aware Federated Reinforcement Learning for Intelligent Network Defense
Research workflow blueprint script.

This script provides an end-to-end, research-oriented implementation scaffold for:
1) CIC-IDS2017 preprocessing
2) non-IID federated client partitioning
3) window-based RL environment construction
4) DQN local agents
5) trust-aware DAPI privacy control
6) federated aggregation and experiment logging


from __future__ import annotations

import os
import glob
import math
import json
import time
import copy
import random
import zipfile
import warnings
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional, Any

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

# =========================================================
# Reproducibility helpers
# =========================================================

def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# =========================================================
# Configuration
# =========================================================
@dataclass
class Config:
    seed: int = 42
    zip_path: str = "/content/MachineLearningCSV.zip"
    extract_dir: str = "/content/cicids2017_csv"
    output_dir: str = "/content/frl_outputs"

    # preprocessing
    test_size: float = 0.2
    val_size: float = 0.1
    use_binary_target: bool = True
    max_rows: Optional[int] = None  # None = full dataset

    # federation
    num_clients: int = 5
    clients_per_round: int = 5
    rounds: int = 10
    local_epochs: int = 2
    batch_size: int = 128
    lr: float = 1e-3

    # RL/windowing
    window_size: int = 16
    stride: int = 8
    episode_length: int = 50

    # DQN
    gamma: float = 0.99
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay: float = 0.995
    replay_capacity: int = 5000
    target_update_freq: int = 50
    hidden_dim: int = 128

    # DAPI / trust
    base_epsilon_privacy: float = 0.5
    beta_privacy: float = 2.0
    gamma_privacy: float = 0.1
    gradient_clip: float = 5.0
    anomaly_z_threshold: float = 2.5
    min_trust: float = 0.05
    max_trust: float = 1.0
    trust_momentum: float = 0.7

    # device
    device: str = "cuda" if torch.cuda.is_available() else "cpu"



# =========================================================
# Window construction and environment
# =========================================================
class WindowBuilder:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def build_windows(self, X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        windows, labels = [], []
        ws, stride = self.cfg.window_size, self.cfg.stride
        for start in range(0, len(X) - ws + 1, stride):
            end = start + ws
            chunk_x = X[start:end]
            chunk_y = y[start:end]
            # state representation: mean + std + max + benign ratio
            state = np.concatenate([
                chunk_x.mean(axis=0),
                chunk_x.std(axis=0),
                chunk_x.max(axis=0),
                np.array([(chunk_y == 0).mean()], dtype=np.float32),
            ]).astype(np.float32)
            # label of window: majority class
            label = np.bincount(chunk_y).argmax()
            windows.append(state)
            labels.append(label)
        return np.array(windows, dtype=np.float32), np.array(labels, dtype=np.int64)


class NetworkDefenseEnv:
    """
    Simplified RL environment for network defense.
    Actions:
      0 = allow
      1 = monitor
      2 = throttle
      3 = block
    Reward encourages correct defense with low operational cost.
    """
    def __init__(self, states: np.ndarray, labels: np.ndarray, episode_length: int = 50):
        self.states = states
        self.labels = labels
        self.episode_length = min(episode_length, len(states))
        self.num_actions = 4
        self.ptr = 0
        self.steps = 0
        self.order = np.arange(len(states))

    def reset(self) -> np.ndarray:
        np.random.shuffle(self.order)
        self.ptr = 0
        self.steps = 0
        idx = self.order[self.ptr]
        return self.states[idx]

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        idx = self.order[self.ptr]
        state = self.states[idx]
        label = self.labels[idx]
        benign = int(label == 0)

        # defense logic: stronger action needed for attack windows
        if benign:
            reward_table = {0: 1.0, 1: 0.4, 2: -0.3, 3: -1.0}
        else:
            reward_table = {0: -1.2, 1: 0.2, 2: 0.8, 3: 1.2}
        reward = reward_table.get(action, -0.5)

        self.ptr += 1
        self.steps += 1
        done = self.ptr >= len(self.order) or self.steps >= self.episode_length
        if done:
            next_state = np.zeros_like(state)
        else:
            next_state = self.states[self.order[self.ptr]]

        info = {"label": int(label), "benign": benign}
        return next_state, float(reward), done, info


# =========================================================
# DQN Agent
# =========================================================
class ReplayBuffer:
    def __init__(self, capacity: int):
        self.buffer = deque(maxlen=capacity)

    def push(self, s, a, r, ns, d):
        self.buffer.append((s, a, r, ns, d))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        s, a, r, ns, d = map(np.array, zip(*batch))
        return s, a, r, ns, d

    def __len__(self):
        return len(self.buffer)


class QNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DQNAgent:
    def __init__(self, cfg: Config, state_dim: int, action_dim: int):
        self.cfg = cfg
        self.device = cfg.device
        self.action_dim = action_dim
        self.epsilon = cfg.epsilon_start

        self.policy_net = QNetwork(state_dim, action_dim, cfg.hidden_dim).to(self.device)
        self.target_net = QNetwork(state_dim, action_dim, cfg.hidden_dim).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=cfg.lr)
        self.buffer = ReplayBuffer(cfg.replay_capacity)
        self.train_steps = 0

    def act(self, state: np.ndarray, greedy: bool = False) -> int:
        if (not greedy) and random.random() < self.epsilon:
            return random.randrange(self.action_dim)
        with torch.no_grad():
            x = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            q = self.policy_net(x)
            return int(q.argmax(dim=1).item())

    def update(self, batch_size: int) -> Optional[float]:
        if len(self.buffer) < batch_size:
            return None
        s, a, r, ns, d = self.buffer.sample(batch_size)

        s = torch.tensor(s, dtype=torch.float32, device=self.device)
        a = torch.tensor(a, dtype=torch.long, device=self.device).unsqueeze(1)
        r = torch.tensor(r, dtype=torch.float32, device=self.device).unsqueeze(1)
        ns = torch.tensor(ns, dtype=torch.float32, device=self.device)
        d = torch.tensor(d, dtype=torch.float32, device=self.device).unsqueeze(1)

        q_values = self.policy_net(s).gather(1, a)
        with torch.no_grad():
            next_q = self.target_net(ns).max(dim=1, keepdim=True)[0]
            target = r + self.cfg.gamma * next_q * (1.0 - d)

        loss = nn.MSELoss()(q_values, target)
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy_net.parameters(), self.cfg.gradient_clip)
        self.optimizer.step()

        self.train_steps += 1
        if self.train_steps % self.cfg.target_update_freq == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())

        self.epsilon = max(self.cfg.epsilon_end, self.epsilon * self.cfg.epsilon_decay)
        return float(loss.item())

    def local_train_on_env(self, env: NetworkDefenseEnv, episodes: int = 5, batch_size: int = 64) -> Dict[str, float]:
        total_rewards, losses = [], []
        for _ in range(episodes):
            state = env.reset()
            done = False
            ep_reward = 0.0
            while not done:
                action = self.act(state)
                next_state, reward, done, _ = env.step(action)
                self.buffer.push(state, action, reward, next_state, done)
                loss = self.update(batch_size)
                if loss is not None:
                    losses.append(loss)
                state = next_state
                ep_reward += reward
            total_rewards.append(ep_reward)
        return {
            "avg_reward": float(np.mean(total_rewards)) if total_rewards else 0.0,
            "avg_loss": float(np.mean(losses)) if losses else 0.0,
        }

    def get_weights(self) -> Dict[str, torch.Tensor]:
        return {k: v.detach().cpu().clone() for k, v in self.policy_net.state_dict().items()}

    def set_weights(self, state_dict: Dict[str, torch.Tensor]) -> None:
        self.policy_net.load_state_dict(state_dict)
        self.target_net.load_state_dict(state_dict)


# =========================================================
# Trust and DAPI
# =========================================================
@dataclass
class ClientStats:
    trust: float = 0.5
    epsilon_privacy: float = 1.0
    last_reward: float = 0.0
    last_loss: float = 0.0
    stability_score: float = 0.5
    anomaly_score: float = 0.0


class DAPIController:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def compute_privacy_budget(self, trust_score: float) -> float:
        # epsilon_i = beta * T_i + gamma   (as in the paper's DAPI description)
        eps = self.cfg.beta_privacy * trust_score + self.cfg.gamma_privacy
        return float(max(self.cfg.base_epsilon_privacy, eps))

    def update_trust(self, prev_trust: float, reward: float, loss: float, update_norm: float, anomaly_score: float) -> float:
        # normalize to [0,1]-ish components
        reward_component = 1 / (1 + math.exp(-reward / 5.0))
        loss_component = 1 / (1 + loss) if loss > 0 else 1.0
        stability_component = 1 / (1 + update_norm)
        anomaly_component = max(0.0, 1.0 - anomaly_score)

        raw = 0.35 * reward_component + 0.25 * loss_component + 0.20 * stability_component + 0.20 * anomaly_component
        trust = self.cfg.trust_momentum * prev_trust + (1 - self.cfg.trust_momentum) * raw
        trust = float(np.clip(trust, self.cfg.min_trust, self.cfg.max_trust))
        return trust

    @staticmethod
    def add_dp_noise_to_weights(weights: Dict[str, torch.Tensor], epsilon: float, sensitivity: float = 1.0) -> Dict[str, torch.Tensor]:
        noisy = {}
        sigma = sensitivity / max(epsilon, 1e-6)
        for k, v in weights.items():
            noise = torch.normal(mean=0.0, std=sigma, size=v.shape)
            noisy[k] = v + noise
        return noisy


# =========================================================
# Federated aggregation
# =========================================================
class FederatedAggregator:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def score_anomaly(self, client_weight_list: List[Dict[str, torch.Tensor]]) -> List[float]:
        flat_updates = []
        for w in client_weight_list:
            flat = torch.cat([p.flatten() for p in w.values()]).numpy()
            flat_updates.append(flat)
        stacked = np.stack(flat_updates, axis=0)
        mean = stacked.mean(axis=0)
        dists = np.linalg.norm(stacked - mean, axis=1)
        if len(dists) <= 1 or dists.std() < 1e-8:
            return [0.0 for _ in dists]
        zscores = np.abs((dists - dists.mean()) / (dists.std() + 1e-8))
        return zscores.tolist()

    def fedavg(self, client_weights: List[Dict[str, torch.Tensor]], client_sizes: List[int], trust_scores: Optional[List[float]] = None) -> Dict[str, torch.Tensor]:
        total = 0.0
        coeffs = []
        for i, sz in enumerate(client_sizes):
            trust = trust_scores[i] if trust_scores is not None else 1.0
            coeff = float(sz) * float(trust)
            coeffs.append(coeff)
            total += coeff
        total = max(total, 1e-8)

        agg = {k: torch.zeros_like(v) for k, v in client_weights[0].items()}
        for coeff, w in zip(coeffs, client_weights):
            alpha = coeff / total
            for k in agg.keys():
                agg[k] += w[k] * alpha
        return agg


# =========================================================
# Evaluation helpers
# =========================================================
def evaluate_agent(env: NetworkDefenseEnv, agent: DQNAgent, episodes: int = 5) -> Dict[str, float]:
    rewards = []
    actions, truths = [], []
    for _ in range(episodes):
        s = env.reset()
        done = False
        ep_reward = 0.0
        while not done:
            a = agent.act(s, greedy=True)
            ns, r, done, info = env.step(a)
            rewards.append(r)
            actions.append(a)
            truths.append(info["label"])
            ep_reward += r
            s = ns
        rewards.append(ep_reward)

    # a coarse operational metric: treat action 0 as benign decision, others as defense trigger
    pred_binary = np.array([0 if a == 0 else 1 for a in actions])
    true_binary = np.array([0 if y == 0 else 1 for y in truths])

    return {
        "mean_reward": float(np.mean(rewards)) if rewards else 0.0,
        "accuracy": float(accuracy_score(true_binary, pred_binary)),
        "precision": float(precision_score(true_binary, pred_binary, zero_division=0)),
        "recall": float(recall_score(true_binary, pred_binary, zero_division=0)),
        "f1": float(f1_score(true_binary, pred_binary, zero_division=0)),
    }


def state_dict_distance(a: Dict[str, torch.Tensor], b: Dict[str, torch.Tensor]) -> float:
    acc = 0.0
    for k in a.keys():
        acc += torch.norm(a[k] - b[k]).item()
    return float(acc)


# =========================================================
# Main FRL workflow
# =========================================================
class FRLWorkflow:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.preprocessor = CICIDSPreprocessor(cfg)
        self.partitioner = FederatedPartitioner(cfg)
        self.window_builder = WindowBuilder(cfg)
        self.dapi = DAPIController(cfg)
        self.aggregator = FederatedAggregator(cfg)
        self.client_stats: Dict[int, ClientStats] = {cid: ClientStats() for cid in range(cfg.num_clients)}
        self.global_agent: Optional[DQNAgent] = None
        self.logs: List[Dict[str, Any]] = []

    def prepare_data(self):
        csv_files = self.preprocessor.unzip_if_needed()
        print(f"Found {len(csv_files)} CSV files")
        raw_df = self.preprocessor.load_merge(csv_files)
        clean_df = self.preprocessor.clean(raw_df)
        prepared = self.preprocessor.prepare_features(clean_df)
        self.preprocessor.save_artifacts(prepared)

        y = prepared["y_binary_enc"] if self.cfg.use_binary_target else prepared["y_multi_enc"]
        splits = self.preprocessor.split(prepared["X_scaled"], y)
        return prepared, splits

    def build_client_environments(self, X_train: np.ndarray, y_train: np.ndarray):
        client_data = self.partitioner.dirichlet_partition(X_train, y_train, alpha=0.3)
        client_envs = {}
        for cid, payload in client_data.items():
            states, labels = self.window_builder.build_windows(payload["X"], payload["y"])
            if len(states) == 0:
                continue
            client_envs[cid] = {
                "env": NetworkDefenseEnv(states, labels, episode_length=self.cfg.episode_length),
                "size": len(states),
                "state_dim": states.shape[1],
                "labels": labels,
            }
        return client_envs

    def initialize_global_agent(self, state_dim: int):
        self.global_agent = DQNAgent(self.cfg, state_dim=state_dim, action_dim=4)

    def run(self):
        set_seed(self.cfg.seed)
        os.makedirs(self.cfg.output_dir, exist_ok=True)

        prepared, splits = self.prepare_data()
        client_envs = self.build_client_environments(splits["X_train"], splits["y_train"])
        if not client_envs:
            raise RuntimeError("No client environments created.")

        first_state_dim = next(iter(client_envs.values()))["state_dim"]
        self.initialize_global_agent(first_state_dim)
        assert self.global_agent is not None

        # Validation/Test envs built from centralized splits for global evaluation
        val_states, val_labels = self.window_builder.build_windows(splits["X_val"], splits["y_val"])
        test_states, test_labels = self.window_builder.build_windows(splits["X_test"], splits["y_test"])
        val_env = NetworkDefenseEnv(val_states, val_labels, episode_length=self.cfg.episode_length)
        test_env = NetworkDefenseEnv(test_states, test_labels, episode_length=self.cfg.episode_length)

        global_weights = self.global_agent.get_weights()

        for rnd in range(1, self.cfg.rounds + 1):
            print(f"\n========== Federated Round {rnd}/{self.cfg.rounds} ==========")
            sampled_clients = sorted(random.sample(list(client_envs.keys()), min(self.cfg.clients_per_round, len(client_envs))))

            local_weights, client_sizes, trust_scores, local_meta = [], [], [], []
            clean_local_weights = []

            for cid in sampled_clients:
                local_agent = DQNAgent(self.cfg, state_dim=first_state_dim, action_dim=4)
                local_agent.set_weights(global_weights)
                train_stats = local_agent.local_train_on_env(
                    client_envs[cid]["env"],
                    episodes=self.cfg.local_epochs,
                    batch_size=min(self.cfg.batch_size, 64),
                )

                clean_weights = local_agent.get_weights()
                clean_local_weights.append(clean_weights)
                client_sizes.append(client_envs[cid]["size"])
                trust_scores.append(self.client_stats[cid].trust)
                local_meta.append((cid, train_stats, clean_weights))

            anomaly_scores = self.aggregator.score_anomaly(clean_local_weights)

            for idx, (cid, train_stats, clean_weights) in enumerate(local_meta):
                update_norm = state_dict_distance(clean_weights, global_weights)
                anomaly_score = anomaly_scores[idx]
                prev_trust = self.client_stats[cid].trust
                new_trust = self.dapi.update_trust(
                    prev_trust=prev_trust,
                    reward=train_stats["avg_reward"],
                    loss=max(train_stats["avg_loss"], 1e-6),
                    update_norm=update_norm,
                    anomaly_score=anomaly_score,
                )
                eps_priv = self.dapi.compute_privacy_budget(new_trust)
                noisy_weights = self.dapi.add_dp_noise_to_weights(clean_weights, epsilon=eps_priv)

                self.client_stats[cid].trust = new_trust
                self.client_stats[cid].epsilon_privacy = eps_priv
                self.client_stats[cid].last_reward = train_stats["avg_reward"]
                self.client_stats[cid].last_loss = train_stats["avg_loss"]
                self.client_stats[cid].anomaly_score = anomaly_score

                local_weights.append(noisy_weights)
                trust_scores[idx] = new_trust

                print(
                    f"Client {cid}: reward={train_stats['avg_reward']:.3f} | "
                    f"loss={train_stats['avg_loss']:.4f} | trust={new_trust:.3f} | "
                    f"eps={eps_priv:.3f} | anomaly={anomaly_score:.3f}"
                )

            global_weights = self.aggregator.fedavg(local_weights, client_sizes, trust_scores)
            self.global_agent.set_weights(global_weights)

            val_metrics = evaluate_agent(val_env, self.global_agent, episodes=5)
            round_log = {
                "round": rnd,
                **{f"val_{k}": v for k, v in val_metrics.items()},
                "mean_trust": float(np.mean([self.client_stats[c].trust for c in sampled_clients])),
                "mean_privacy_epsilon": float(np.mean([self.client_stats[c].epsilon_privacy for c in sampled_clients])),
            }
            self.logs.append(round_log)
            print(f"Round {rnd} validation: {round_log}")

        test_metrics = evaluate_agent(test_env, self.global_agent, episodes=10)
        print("\n========== Final Test Metrics ==========")
        print(test_metrics)

        self.save_outputs(test_metrics)
        return test_metrics

    def save_outputs(self, test_metrics: Dict[str, float]) -> None:
        os.makedirs(self.cfg.output_dir, exist_ok=True)
        pd.DataFrame(self.logs).to_csv(os.path.join(self.cfg.output_dir, "federated_round_logs.csv"), index=False)
        pd.DataFrame({cid: asdict(stats) for cid, stats in self.client_stats.items()}).T.to_csv(
            os.path.join(self.cfg.output_dir, "client_stats.csv"), index=True
        )
        with open(os.path.join(self.cfg.output_dir, "final_test_metrics.json"), "w") as f:
            json.dump(test_metrics, f, indent=2)
        if self.global_agent is not None:
            torch.save(self.global_agent.policy_net.state_dict(), os.path.join(self.cfg.output_dir, "global_dqn_model.pt"))
        with open(os.path.join(self.cfg.output_dir, "run_config.json"), "w") as f:
            json.dump(asdict(self.cfg), f, indent=2)


# =========================================================
# Colab-friendly main
# =========================================================
def main():
    cfg = Config(
        zip_path="/content/MachineLearningCSV.zip",   # change if needed
        extract_dir="/content/cicids2017_csv",
        output_dir="/content/frl_outputs",
        max_rows=300000,   # reduce/raise depending on Colab RAM
        num_clients=5,
        clients_per_round=5,
        rounds=8,
        local_epochs=2,
        use_binary_target=True,
    )

    workflow = FRLWorkflow(cfg)
    results = workflow.run()
    print("\nRun finished.")
    print(results)


if __name__ == "__main__":
    main()
