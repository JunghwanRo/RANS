import argparse
import os

from omniisaacgymenvs.mujoco_envs.RL_games_model_4_mujoco import RLGamesModel
from omniisaacgymenvs.ros.ros_nodes import RLPlayerNode

def parseArgs():
    parser = argparse.ArgumentParser("Generates meshes out of Digital Elevation Models (DEMs) or Heightmaps.")
    # Model arguments
    parser.add_argument("--model_path", type=str, default=None, help="The path to the model to be loaded. It must be a velocity tracking model.")
    parser.add_argument("--config_path", type=str, default=None, help="The path to the network configuration to be loaded.")
    # GoToXY arguments
    parser.add_argument("--goal_x", type=float, nargs="+", default=None, help="List of x coordinates for the goals to be reached by the platform. In world frame, meters.")
    parser.add_argument("--goal_y", type=float, nargs="+", default=None, help="List of y coordinates for the goals to be reached by the platform. In world frame, meters.")
    parser.add_argument("--distance_threshold", type=float, default=0.03, help="The threshold to be under to consider a goal reached. In meters.")
    # GoToPose arguments
    parser.add_argument("--goal_theta", type=float, nargs="+", default=None, help="List of headings for the goals to be reached by the platform. In world frame, radiants.")
    # TrackXYVelocity arguments
    parser.add_argument("--tracking_velocity", type=float, default=0.25, help="The tracking velocity. In meters per second.")
    # Velocity trajectory arguments
    parser.add_argument("--trajectory_type", type=str, default="Circle", help="The type of trajectory to be generated. Options are: Circle, Square, Spiral.")
    parser.add_argument("--radius", type=float, default=1.5, help="The radius of the circle trajectory. In meters.")
    parser.add_argument("--height", type=float, default=3.0, help="The height of the square trajectory. In meters.")
    parser.add_argument("--start_radius", type=float, default=0.5, help="The starting radius for the spiral for the spiral trajectory. In meters.")
    parser.add_argument("--end_radius", type=float, default=2.0, help="The final radius for the spiral trajectory. In meters.")
    parser.add_argument("--num_loop", type=float, default=5.0, help="The number of loops the spiral trajectory should make. Must be greater than 0.")
    parser.add_argument("--closed", type=bool, default=True, help="Whether the trajectory is closed (it forms a loop) or not.")
    parser.add_argument("--lookahead_dist", type=float, default=0.15, help="How far the velocity tracker looks to generate the velocity vector that will track the trajectory. In meters.")
    # General arguments
    parser.add_argument("--task_mode", type=str, default="GoToXY", help="The type of task that the agent must solve. Options are: GoToXY, GoToPose, TrackXYVelocity, TrackXYOVelocity.")
    parser.add_argument("--exp_duration", type=float, default=240, help="The length of the experiment. In seconds.")
    parser.add_argument("--use_live_goals", type=bool, default=False, help="Whether the agent should use command live goals or ROS goals. If set to True, the agent will use the live goals.")
    parser.add_argument("--play_rate", type=float, default=5.0, help="The frequency at which the agent will played. In Hz. Note, that this depends on the sim_rate, the agent my not be able to play at this rate depending on the sim_rate value. To be consise, the agent will play at: sim_rate / int(sim_rate/play_rate)")
    parser.add_argument("--save_dir", type=str, default="ros_exp", help="The path to the folder in which the results will be stored.")
    parser.add_argument("--save_exp", type=bool, default=False, help="Whether or not the experiment will be saved as np array.")
    args, unknown_args = parser.parse_known_args()
    return args, unknown_args

if __name__ == '__main__':
    # Collects args
    args, _ = parseArgs()
    # Checks args
    assert os.path.exists(args.model_path), "The model file does not exist."
    assert os.path.exists(args.config_path), "The configuration file does not exist."
    assert args.task_mode.lower() in ["gotoxy", "gotopose", "trackxyvelocity", "trackxyovelocity"], "The task mode must be one of the following: GoToXY, GoToPose, TrackXYVelocity, TrackXYOVelocity."
    if args.task_mode.lower() == "gotoxy":
        task_id = 0
        if not args.use_live_goals:
            assert not args.goal_x is None, "The x coordinates of the goals must be specified."
            assert not args.goal_y is None, "The y coordinates of the goals must be specified."
            assert len(args.goal_x) == len(args.goal_y), "The number of x coordinates must be equal to the number of y coordinates."
        else:
            args.goal_x = [0]
            args.goal_y = [0]
    elif args.task_mode.lower() == "gotopose":
        task_id = 1
        if not args.use_live_goals:
            assert not args.goal_x is None, "The x coordinates of the goals must be specified."
            assert not args.goal_y is None, "The y coordinates of the goals must be specified."
            assert not args.goal_theta is None, "The theta coordinates of the goals must be specified."
            assert len(args.goal_x) == len(args.goal_y), "The number of x coordinates must be equal to the number of y coordinates."
            assert len(args.goal_x) == len(args.goal_theta), "The number of x coordinates must be equal to the number of theta coordinates."
        else:
            args.goal_x = [0]
            args.goal_y = [0]
            args.goal_theta = [0]
    elif args.task_mode.lower() == "trackxyvelocity":
        task_id = 2
        assert args.num_loop > 0, "The number of loops must be greater than 0."
        assert args.lookahead_dist > 0, "The lookahead distance must be greater than 0."
        assert args.radius > 0, "The radius must be greater than 0."
        assert args.start_radius > 0, "The start radius must be greater than 0."
        assert args.end_radius > 0, "The end radius must be greater than 0."
        assert args.height > 0, "The height must be greater than 0."
        assert args.tracking_velocity > 0, "The tracking velocity must be greater than 0."
    elif args.task_mode.lower() == "trackxyovelocity":
        task_id = 3
        raise NotImplementedError("The TrackXYOVelocity task is not implemented yet.")
    assert args.exp_duration > 0, "The experiment duration must be greater than 0."
    assert args.play_rate > 0, "The play rate must be greater than 0."
    # Try to create the save directory
    if args.save_exp:
        try:
            os.makedirs(args.save_dir, exist_ok=True)
        except:
            raise ValueError("Could not create the save directory.")
    # Initialize the model.
    model = RLGamesModel(args.config_path, task_id, args.model_path)
    # Initialize the node.
    node = RLPlayerNode(model, args)
    # Run the node.
    node.run()