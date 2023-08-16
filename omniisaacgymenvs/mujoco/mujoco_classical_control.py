import mujoco
import numpy as np

# Graphics and plotting.
import matplotlib.pyplot as plt
import numpy as np

class MuJoCoFloatingPlatform:
    """
    A class for the MuJoCo Floating Platform environment."""

    def __init__(self, step_time=0.02, duration=60, inv_play_rate=10):
        """
        Initializes the MuJoCo Floating Platform environment.
        step_time: The time between steps in the simulation.
        duration: The duration of the simulation.
        inv_play_rate: The inverse of rate at which the controller will run.
        
        With a step_time of 0.02, and inv_play_rate of 10, the agent will play every 0.2 seconds. (or 5Hz)
        """

        self.inv_play_rate = inv_play_rate

        self.createModel()
        self.initializeModel()
        self.setupPhysics(step_time, duration)
        self.initForceAnchors()
        self.initializeLoggers()

        self.goal = np.zeros((2), dtype=np.float32)
        self.state = np.zeros((10), dtype=np.float32)

    def initializeModel(self):
        """
        Initializes the mujoco model for the simulation."""

        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)
        self.body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY,"top")

    def setupPhysics(self, step_time, duration):
        """
        Sets up the physics parameters for the simulation.
        Setups the gravity, timestep, and duration of the simulation."""

        self.model.opt.timestep = step_time
        self.model.opt.gravity = [0,0,0]
        self.duration = duration

    def initializeLoggers(self):
        """
        Initializes the loggers for the simulation.
        Allowing for the simulation to be replayed/plotted."""

        self.timevals = []
        self.angular_velocity = []
        self.linear_velocity = []
        self.position = []
        self.heading = []

    def createModel(self):
        """
        A YAML style string that defines the MuJoCo model for the simulation.
        The mass is set to 5.32 kg, the radius is set to 0.31 m.
        The initial position is set to (3, 3, 0.4) m."""

        sphere = """
        <mujoco model="tippe top">
          <option integrator="RK4"/>
        
          <asset>
            <texture name="grid" type="2d" builtin="checker" rgb1=".1 .2 .3"
             rgb2=".2 .3 .4" width="300" height="300"/>
            <material name="grid" texture="grid" texrepeat="8 8" reflectance=".2"/>
          </asset>
        
          <worldbody>
            <geom size="10.0 10.0 .01" type="plane" material="grid"/>
            <light pos="0 0 10.0"/>
            <camera name="closeup" pos="0 -3 2" xyaxes="1 0 0 0 1 2"/>
            <body name="top" pos="0 0 .4">
              <freejoint/>
              <geom name="ball" type="sphere" size=".31" mass="5.32"/>
            </body>
          </worldbody>
        
          <keyframe>
            <key name="idle" qpos="3 3 0.4 1 0 0 0" qvel="0 0 0 0 0 0" />
          </keyframe>
        </mujoco>
        """
        self.model = mujoco.MjModel.from_xml_string(sphere)

    def initForceAnchors(self):
        """"
        Defines where the forces are applied relatively to the center of mass of the body.
        self.forces: 8x3 array of forces, indicating the direction of the force.
        self.positions: 8x3 array of positions, indicating the position of the force."""

        self.forces = np.array([[ 1, -1, 0],
                           [-1,  1, 0],
                           [ 1,  1, 0],
                           [-1, -1, 0],
                           [-1,  1, 0],
                           [ 1, -1, 0],
                           [-1, -1, 0],
                           [ 1,  1, 0]])
        
        self.positions = np.array([[ 1,  1, 0],
                              [ 1,  1, 0],
                              [-1,  1, 0],
                              [-1,  1, 0],
                              [-1, -1, 0],
                              [-1, -1, 0],
                              [ 1, -1, 0],
                              [ 1, -1, 0]]) * 0.2192


    def resetPosition(self):
        """
        Resets the position of the body to the initial position, (3, 3, 0.4) m"""
        mujoco.mj_resetDataKeyframe(self.model, self.data, 0)

    def applyForces(self, action):
        """
        Applies the forces to the body."""

        self.data.qfrc_applied[...] = 0 # Clear applied forces.
        rmat = self.data.xmat[self.body_id].reshape(3,3) # Rotation matrix.
        p = self.data.xpos[self.body_id] # Position of the body.

        # Compute the number of thrusters fired, split the pressure between the nozzles.
        factor = max(np.sum(action), 1) 
        # For each thruster, apply a force if needed.
        for i in range(8):
          # The force applied is the action value (1 or 0), divided by the number of thrusters fired (factor),
          # times the orientation of the force (self.forces), times sqrt(0.5) to normalize the force orientation vector.
          force = action[i] * (1./factor) * self.forces[i] * np.sqrt(0.5)
          # If the force is not zero, apply the force.
          if np.sum(np.abs(force)) > 0:
              force = np.matmul(rmat, force) # Rotate the force to the body frame.
              p2 = np.matmul(rmat, self.positions[i]) + p # Compute the position of the force.
              mujoco.mj_applyFT(self.model, self.data, force, [0,0,0], p2, self.body_id, self.data.qfrc_applied) # Apply the force.

    def updateLoggers(self):
        """
        Updates the loggers with the current state of the simulation."""

        self.timevals.append(self.data.time)
        self.angular_velocity.append(self.data.qvel[3:6].copy())
        self.linear_velocity.append(self.data.qvel[0:3].copy())
        self.position.append(self.data.qpos[0:3].copy())

    def updateState(self):
        """
        Updates the state of the simulation."""

        qpos = self.data.qpos.copy() # Copy the pose of the object.
        # Cast the quaternion to the yaw (roll and pitch are invariant).
        siny_cosp = 2 * (qpos[3] * qpos[6] + qpos[4] * qpos[5])
        cosy_cosp = 1 - 2 * (qpos[5] * qpos[5] + qpos[6] * qpos[6])
        orient_z = np.arctan2(siny_cosp, cosy_cosp)
        # Compute the distance to the goal. (in the global frame)
        dist_to_goal = self.goal - qpos[:2]
        # Gets the angular and linear velocity.
        linear_velocity = self.data.qvel[0:2].copy() # X and Y velocities.
        angular_velocity = self.data.qvel[5].copy() # Yaw velocity.
        # Returns the state.
        return orient_z, dist_to_goal, angular_velocity, linear_velocity

    def runLoop(self, controller, xy):
        """
        Runs the simulation loop."""

        self.resetPosition() # Resets the position of the body.
        self.data.qpos[:2] = xy # Sets the position of the body.

        while self.duration > self.data.time:
            state = self.updateState() # Updates the state of the simulation.
            # Get the actions from the controller
            action = controller.getAction(self.state)
            # Plays only once every self.inv_play_rate steps.
            for _ in range(self.inv_play_rate):
                self.applyForces(action)
                mujoco.mj_step(self.model, self.data)
                self.updateLoggers()
    
    def plotSimulation(self, dpi=120, width=600, height=800, save=False):
        """
        Plots the simulation."""

        figsize = (width / dpi, height / dpi)

        fig, ax = plt.subplots(2, 1, figsize=figsize, dpi=dpi)

        ax[0].plot(env.timevals, env.angular_velocity)
        ax[0].set_title('angular velocity')
        ax[0].set_ylabel('radians / second')

        ax[1].plot(env.timevals, env.linear_velocity)
        ax[1].set_xlabel('time (seconds)')
        ax[1].set_ylabel('meters / second')
        _ = ax[1].set_title('linear_velocity')
        if save:
            fig.savefig("test_velocities.png")

        fig, ax = plt.subplots(2, 1, figsize=figsize, dpi=dpi)
        ax[0].plot(env.timevals, np.abs(env.position))
        ax[0].set_xlabel('time (seconds)')
        ax[0].set_ylabel('meters')
        _ = ax[0].set_title('position')
        ax[0].set_yscale('log')


        ax[1].plot(np.array(env.position)[:,0], np.array(env.position)[:,1])
        ax[1].set_xlabel('meters')
        ax[1].set_ylabel('meters')
        _ = ax[1].set_title('x y coordinates')
        plt.tight_layout()
        if save:
            fig.savefig("test_positions.png")

if __name__ == "__main__":

    model = SOMETHING
    env = MuJoCoFloatingPlatform()
    env.runLoop(model, [3,0])
    env.plotSimulation(save=False)