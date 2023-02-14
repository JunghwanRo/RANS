import torch
import torch.nn as nn

# Import the skrl components to build the RL system
from skrl.models.torch import Model, DeterministicMixin
from skrl.memories.torch import RandomMemory
from skrl.agents.torch.dqn import DQN, DQN_DEFAULT_CONFIG
from skrl.resources.schedulers.torch import KLAdaptiveRL
from skrl.resources.preprocessors.torch import RunningStandardScaler
from skrl.trainers.torch import SequentialTrainer
from skrl.envs.torch import wrap_env
from skrl.envs.torch import load_omniverse_isaacgym_env

from skrl.utils import set_seed

# set the seed for reproducibility

set_seed(42)



# Define the shared model (stochastic and deterministic models) for the agent using mixins.
class Shared(DeterministicMixin, Model):
    def __init__(self, observation_space, action_space, device, clip_actions=False,
                 clip_log_std=True, min_log_std=-20, max_log_std=2, reduction="sum"):
        Model.__init__(self, observation_space, action_space, device)
        DeterministicMixin.__init__(self, clip_actions)

        self.net = nn.Sequential(nn.Linear(self.num_observations, 256),
                                 nn.Tanh(),
                                 nn.Linear(256, 256),
                                 nn.Tanh(),
                                 nn.Linear(256, 128),
                                 nn.ReLU(),
                                  nn.Linear(128, self.num_actions))


    def act(self, inputs, role):

        return DeterministicMixin.act(self, inputs, role)

    def compute(self, inputs, role):
        return nn.Linear(self.net(inputs["states"])), {}


# Load and wrap the Omniverse Isaac Gym environment
env = load_omniverse_isaacgym_env(task_name="FloatingPlatform")
env = wrap_env(env)

device = env.device


# Instantiate a RandomMemory as rollout buffer (any memory can be used for this)
memory = RandomMemory(memory_size=16, num_envs=env.num_envs, device=device)


# Instantiate the agent's models (function approximators).
# PPO requires 2 models, visit its documentation for more details
# https://skrl.readthedocs.io/en/latest/modules/skrl.agents.ppo.html#spaces-and-models
models_dqn = {}
models_dqn["q_network"] = Shared(env.observation_space, env.action_space, device)
models_dqn["target_q_network"] = models_dqn["q_network"]  # same instance: shared model


# Configure and instantiate the agent.
# Only modify some of the default configuration, visit its documentation to see all the options
# https://skrl.readthedocs.io/en/latest/modules/skrl.agents.ppo.html#configuration-and-hyperparameters
cfg_dqn = DQN_DEFAULT_CONFIG.copy()
#cfg_dqn["rewards_shaper"] = lambda rewards, timestep, timesteps: rewards * 0.01
# logging to TensorBoard and write checkpoints each 80 and 800 timesteps respectively
cfg_dqn["experiment"]["write_interval"] = 80
cfg_dqn["experiment"]["checkpoint_interval"] = 800
#cfg_dqn["experiment"]["wandb"] = True

agent = DQN(models=models_dqn,
            memory=memory,
            cfg=cfg_dqn,
            observation_space=env.observation_space,
            action_space=env.action_space,
            device=device)


# Configure and instantiate the RL trainer
cfg_trainer = {"timesteps": 16000, "headless": True}
trainer = SequentialTrainer(cfg=cfg_trainer, env=env, agents=agent)

# start training
trainer.train()