import sys
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lerobot.cameras import CameraConfig
from lerobot.lerobot_types import RobotAction, RobotObservation
from lerobot.robots.robot import Robot, RobotConfig

from .config_seeed_b601_dm_follower import SeeedB601DMFollowerConfig
from .config_seeed_b601_rs_follower import SeeedB601RSFollowerConfig
from .seeed_b601_dm_follower import SeeedB601DMFollower
from .seeed_b601_rs_follower import SeeedB601RSFollower
from .seeed_b601_follower import MotorOverheatError


@dataclass
class SeeedB601ArmConfig:
    motor_family: Literal["dm", "rs"]
    port: str
    # Match HF defaults: DM uses its serial bridge, RS uses native CAN.
    can_adapter: Literal["socketcan", "damiao"] | None = None
    dm_serial_baud: int = 921600
    max_relative_target: float | dict[str, float] | None = None

    def __post_init__(self):
        if self.can_adapter is None:
            self.can_adapter = "damiao" if self.motor_family == "dm" else "socketcan"
        if self.motor_family == "rs" and self.can_adapter == "damiao":
            raise ValueError("An RS follower needs a SocketCAN-compatible adapter")


@RobotConfig.register_subclass("bi_seeed_b601_follower")
@dataclass(kw_only=True)
class BiSeeedB601FollowerConfig(RobotConfig):
    left_arm_config: SeeedB601ArmConfig
    right_arm_config: SeeedB601ArmConfig
    # All cameras are configured here and keep their names in observations.
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    # Disconnect parks both arms in this order after a successful connection.
    # Calibration, connection failure, and detected control faults skip parking.
    park_first: Literal["left", "right"] | None = "left"


class BiSeeedB601Follower(Robot):
    name = "bi_seeed_b601_follower"
    config_class = BiSeeedB601FollowerConfig

    def __init__(self, config: BiSeeedB601FollowerConfig):
        self._park_on_disconnect = False
        super().__init__(config)
        self.config = config
        left, right = config.left_arm_config, config.right_arm_config
        if Path(left.port).resolve() == Path(right.port).resolve():
            raise ValueError("The two arms need separate ports")
        # The left driver manages every camera's connection, reads, and cleanup.
        self.left_arm = self._make_arm(left, "left", config)
        self.right_arm = self._make_arm(right, "right", config)
        occupied_names = set()
        for side, arm in (("left", self.left_arm), ("right", self.right_arm)):
            motor_keys = {f"{joint}.{kind}" for joint in arm.motor_names for kind in ("pos", "vel", "torque")}
            occupied_names.update(f"{side}_{key}" for key in motor_keys)
            if side == "left":
                occupied_names.update(motor_keys)
        collisions = set(config.cameras) & occupied_names
        if collisions:
            raise ValueError(f"Top-level camera names collide with arm features: {sorted(collisions)}")
        self.cameras = dict(self.left_arm.cameras)

    @staticmethod
    def _make_arm(arm_config: SeeedB601ArmConfig, side: str, config: BiSeeedB601FollowerConfig):
        if arm_config.motor_family == "rs":
            driver, driver_config = SeeedB601RSFollower, SeeedB601RSFollowerConfig
        else:
            driver, driver_config = SeeedB601DMFollower, SeeedB601DMFollowerConfig
        settings = driver_config(
            id=f"{config.id or 'bi_follower'}_{side}",
            calibration_dir=config.calibration_dir,
            port=arm_config.port,
            can_adapter=arm_config.can_adapter,
            dm_serial_baud=arm_config.dm_serial_baud,
            cameras=dict(config.cameras) if side == "left" else {},
            max_relative_target=arm_config.max_relative_target,
            safe_zero_on_disconnect=False,
            zero_missing_wrist_yaw=False,
            check_gripper_zero_on_connect=False,
        )
        # Reuse the HF coordinate specification, not its motor driver. Seeed
        # applies signs first and clips in motor degrees; HF limits are public.
        from lerobot.robots.rebot_b601_follower.motor_family import MOTOR_PROFILES, MotorFamily

        profile = MOTOR_PROFILES[MotorFamily(arm_config.motor_family)]
        settings.joint_directions = dict(profile.joint_directions)
        for joint, (low, high) in profile.joint_limits.items():
            sign = settings.joint_directions[joint]
            motor_low, motor_high = sorted((low * sign, high * sign))
            seeed_low, seeed_high = settings.joint_limits[joint]
            settings.joint_limits[joint] = max(motor_low, seeed_low), min(motor_high, seeed_high)
        return driver(settings)

    @staticmethod
    def _combine(left, right):
        return {
            **{f"left_{key}": value for key, value in left.items()},
            **{f"right_{key}": value for key, value in right.items()},
        }

    def _combine_observations(self, left, right):
        return {
            **{key if key in self.config.cameras else f"left_{key}": value for key, value in left.items()},
            **{f"right_{key}": value for key, value in right.items()},
        }

    @property
    def observation_features(self):
        return self._combine_observations(self.left_arm.observation_features, self.right_arm.observation_features)

    @property
    def action_features(self):
        return self._combine(self.left_arm.action_features, self.right_arm.action_features)

    @property
    def is_connected(self) -> bool:
        return self.left_arm.is_connected and self.right_arm.is_connected

    @property
    def is_calibrated(self) -> bool:
        return self.left_arm.is_calibrated and self.right_arm.is_calibrated

    def connect(self, calibrate: bool = True) -> None:
        if self.left_arm.bus is not None or self.right_arm.bus is not None:
            raise RuntimeError("Disconnect both arms before connecting again")
        with ExitStack() as cleanup:
            cleanup.callback(self.disconnect)
            self.left_arm.connect(calibrate)
            self.right_arm.connect(calibrate)
            cleanup.pop_all()
        self._park_on_disconnect = calibrate

    def calibrate(self) -> None:
        self._park_on_disconnect = False
        self.left_arm.calibrate()
        self.right_arm.calibrate()

    def configure(self) -> None:
        self.left_arm.configure()
        self.right_arm.configure()

    @staticmethod
    def _public_feedback(arm, values):
        # Both Seeed get_observation and send_action return motor-frame values.
        # Motor family directions are unit signs; torque/velocity use the same sign.
        result = values.copy()
        for joint, sign in arm.config.joint_directions.items():
            for field in ("pos", "vel", "torque"):
                key = f"{joint}.{field}"
                if key in values:
                    result[key] = values[key] / sign
        return result

    def get_observation(self) -> RobotObservation:
        try:
            return self._combine_observations(
                self._public_feedback(self.left_arm, self.left_arm.get_observation()),
                self._public_feedback(self.right_arm, self.right_arm.get_observation()),
            )
        except (Exception, MotorOverheatError):
            self._park_on_disconnect = False
            raise

    def send_action(self, action: RobotAction) -> RobotAction:
        left = {key.removeprefix("left_"): value for key, value in action.items() if key.startswith("left_")}
        right = {key.removeprefix("right_"): value for key, value in action.items() if key.startswith("right_")}
        try:
            if not left or not right:
                raise ValueError("Bimanual actions must contain targets for both arms")
            return self._combine(
                self._public_feedback(self.left_arm, self.left_arm.send_action(left)),
                self._public_feedback(self.right_arm, self.right_arm.send_action(right)),
            )
        except (Exception, MotorOverheatError):
            self._park_on_disconnect = False
            raise

    def park(self, first: Literal["left", "right"]) -> None:
        # Consume the request before starting, including when parking fails or
        # is interrupted. A later disconnect must never restart the motion.
        self._park_on_disconnect = False
        if first not in ("left", "right"):
            raise ValueError("Choose left or right as the first arm to park")
        order = (self.left_arm, self.right_arm)
        if first == "right":
            order = order[::-1]
        for arm in order:
            for candidate in order:
                candidate.check_parking_feedback()
            if not arm.safe_zero(exit_on_complete=False, verify=True):
                raise RuntimeError("Parking was aborted")

    def disconnect(self):
        park_requested = self._park_on_disconnect
        self._park_on_disconnect = False
        # The stock teleop loop uses finally for all exits and swallows Ctrl+C.
        # Preserve other in-flight exceptions without commanding a return motion.
        active_error = sys.exc_info()[1]
        with ExitStack() as cleanup:
            for arm in (self.right_arm, self.left_arm):
                if arm.bus is not None:
                    cleanup.callback(arm.disconnect)
            if (
                park_requested
                and self.config.park_first is not None
                and self.is_connected
                and (active_error is None or type(active_error) is KeyboardInterrupt)
            ):
                self.park(self.config.park_first)

    def __del__(self):
        # Garbage collection is resource cleanup, not an operator parking request.
        self._park_on_disconnect = False
        super().__del__()
