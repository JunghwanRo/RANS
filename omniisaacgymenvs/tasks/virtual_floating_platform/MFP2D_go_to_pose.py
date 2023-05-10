from omniisaacgymenvs.tasks.virtual_floating_platform.MFP2D_core import Core, parse_data_dict
from omniisaacgymenvs.tasks.virtual_floating_platform.MFP2D_task_rewards import GoToPoseReward
from omniisaacgymenvs.tasks.virtual_floating_platform.MFP2D_task_parameters import GoToPoseParameters

import math
import torch

EPS = 1e-6   # small constant to avoid divisions by 0 and log(0)

class GoToPoseTask(Core):
    def __init__(self, task_param, reward_param, num_envs, device):
        super(GoToPoseTask, self).__init__(num_envs, device)
        self._task_parameters = parse_data_dict(GoToPoseParameters(), task_param)
        self._reward_parameters = parse_data_dict(GoToPoseReward(), reward_param)

        self._goal_reached = torch.zeros((self._num_envs), device=self._device, dtype=torch.int32)
        self._target_positions = torch.zeros((self._num_envs, 2), device=self._device, dtype=torch.float32)
        self._target_headings = torch.zeros((self._num_envs), device=self._device, dtype=torch.float32)
        self._task_label = self._task_label * 1 

    def create_stats(self, stats):
        torch_zeros = lambda: torch.zeros(self._num_envs, dtype=torch.float, device=self._device, requires_grad=False)
        if not "position_reward" in stats.keys():
            stats["position_reward"] = torch_zeros()
        if not "position_error" in stats.keys():
            stats["position_error"] = torch_zeros()
        if not "heading_reward" in stats.keys():
            stats["heading_reward"] = torch_zeros()
        if not "heading_error" in stats.keys():
            stats["heading_error"] = torch_zeros()
        return stats

    def get_state_observations(self, current_state):
        # position distance
        self._position_error = self._target_positions - current_state["position"]
        # heading distance
        heading = torch.arctan2(current_state["orientation"][:,1], current_state["orientation"][:, 0])
        self._heading_error = torch.arctan2(torch.sin(self._target_headings - heading), torch.cos(self._target_headings - heading))
        # Encode task data
        self._task_data[:,:2] = self._position_error
        self._task_data[:, 2] = torch.cos(self._heading_error)
        self._task_data[:, 3] = torch.sin(self._heading_error)
        return self.update_observation_tensor(current_state)

    def compute_reward(self, current_state, actions):
        # position error
        self.position_dist = torch.sqrt(torch.square(self._position_error).sum(-1))
        self.heading_dist = torch.abs(self._heading_error)

        # Checks if the goal is reached
        position_goal_is_reached = (self.position_dist < self._task_parameters.x_y_tolerance).int()
        heading_goal_is_reached = (self.heading_dist < self._task_parameters.heading_tolerance).int()
        goal_is_reached = position_goal_is_reached * heading_goal_is_reached
        self._goal_reached *= goal_is_reached # if not set the value to 0
        self._goal_reached += goal_is_reached # if it is add 1
    
        # rewards
        self.position_reward, self.heading_reward = self._reward_parameters.compute_reward(current_state, actions, self.position_dist, self.heading_dist)

        return self.position_reward + self.heading_reward
    
    def update_kills(self):
        die = torch.zeros_like(self._goal_reached, dtype=torch.long)
        ones = torch.ones_like(self._goal_reached, dtype=torch.long)
        die = torch.where(self.position_dist > self._task_parameters.kill_dist, ones, die)
        die = torch.where(self._goal_reached > self._task_parameters.kill_after_n_steps_in_tolerance, ones, die)
        return die
    
    def update_statistics(self, stats):
        stats["position_reward"] += self.position_reward
        stats["heading_reward"] += self.heading_reward
        stats["position_error"] += self.position_dist
        stats["heading_error"] += self.heading_dist
        return stats

    def reset(self, env_ids):
        self._goal_reached[env_ids] = 0

    def get_goals(self, env_ids, target_positions, target_orientations):
        num_goals = len(env_ids)
        # Randomize position
        self._target_positions[env_ids] = torch.rand((num_goals, 2), device=self._device)*self._task_parameters.goal_random_position*2 - self._task_parameters.goal_random_position
        target_positions[env_ids,:2] += self._target_positions[env_ids]
        # Randomize heading
        self._target_headings[env_ids] = torch.rand(num_goals, device=self._device) * math.pi * 2
        target_orientations[env_ids, 0] = torch.cos(self._target_headings[env_ids]*0.5)
        target_orientations[env_ids, 3] = torch.sin(self._target_headings[env_ids]*0.5)
        return target_positions, target_orientations
    
    def get_spawns(self, env_ids, initial_position, initial_orientation, step=0):
        num_resets = len(env_ids)
        # Resets the counter of steps for which the goal was reached
        self._goal_reached[env_ids] = 0
        # Run curriculum if selected
        if self._task_parameters.spawn_curriculum:
            if step < self._task_parameters.spawn_curriculum_warmup:
                rmax = self._task_parameters.spawn_curriculum_max_dist
                rmin = self._task_parameters.spawn_curriculum_min_dist
            elif step > self._task_parameters.spawn_curriculum_end:
                rmax = self._task_parameters.max_spawn_dist
                rmin = self._task_parameters.min_spawn_dist
            else:
                r = (step - self._task_parameters.spawn_curriculum_warmup) / (self._task_parameters.spawn_curriculum_end - self._task_parameters.spawn_curriculum_warmup)
                rmax = r * (self._task_parameters.max_spawn_dist - self._task_parameters.spawn_curriculum_max_dist) + self._task_parameters.spawn_curriculum_max_dist
                rmin = r * (self._task_parameters.min_spawn_dist - self._task_parameters.spawn_curriculum_min_dist) + self._task_parameters.spawn_curriculum_min_dist
        else:
            rmax = self._task_parameters.max_spawn_dist
            rmin = self._task_parameters.min_spawn_dist

        # Randomizes the starting position of the platform
        r = torch.rand((num_resets,), device=self._device) * (rmax - rmin) + rmin
        theta = torch.rand((num_resets,), device=self._device) * 2 * math.pi
        initial_position[env_ids, 0] += (r)*torch.cos(theta) + self._target_positions[env_ids, 0]
        initial_position[env_ids, 1] += (r)*torch.sin(theta) + self._target_positions[env_ids, 1]
        initial_position[env_ids, 2] += 0

        # Randomizes the heading of the platform
        random_orient = torch.rand(num_resets, device=self._device) * math.pi
        initial_orientation[env_ids, 0] = torch.cos(random_orient*0.5)
        initial_orientation[env_ids, 3] = torch.sin(random_orient*0.5)
        return initial_position, initial_orientation