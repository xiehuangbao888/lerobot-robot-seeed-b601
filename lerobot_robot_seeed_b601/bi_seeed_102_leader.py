"""Two Seeed Arm 102 leaders publishing angles in LeRobot's B601 joint frame."""

import math
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from lerobot.teleoperators.config import TeleoperatorConfig
from lerobot.teleoperators.rebot_102_leader.config_rebot_102_leader import RebotArm102LeaderConfig
from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.utils.bimanual import BimanualMixin
from lerobot.utils.decorators import check_if_not_connected
from lerobot_teleoperator_rebot_arm_102 import RebotArm102Leader as SeeedArm102
from lerobot_teleoperator_rebot_arm_102 import RebotArm102LeaderConfig as SeeedArm102Config


@TeleoperatorConfig.register_subclass("bi_seeed_102_leader")
@dataclass
class BiSeeed102LeaderConfig(TeleoperatorConfig):
    # Only the numeric mapping and serial configuration are shared with HF.
    left_arm_config: RebotArm102LeaderConfig
    right_arm_config: RebotArm102LeaderConfig


class BiSeeed102Leader(BimanualMixin, Teleoperator):
    name = "bi_seeed_102_leader"
    config_class = BiSeeed102LeaderConfig

    def __init__(self, config: BiSeeed102LeaderConfig):
        super().__init__(config)
        self.config = config
        if Path(config.left_arm_config.port).resolve() == Path(config.right_arm_config.port).resolve():
            raise ValueError("The left and right leaders need different serial ports.")
        self.left_arm = self._make_arm("left", config.left_arm_config)
        self.right_arm = self._make_arm("right", config.right_arm_config)

    def _make_arm(self, side, mapping):
        if mapping.joint_ids.keys() != mapping.joint_directions.keys():
            raise ValueError("joint_directions must cover every leader servo")
        return SeeedArm102(SeeedArm102Config(
            port=mapping.port,
            baudrate=mapping.baudrate,
            joint_ids=mapping.joint_ids,
            joint_ranges=mapping.joint_ranges,
            calibration_dir=self.config.calibration_dir,
            id=f"{self.config.id or 'bi_leader'}_{side}",
        ))

    @property
    def action_features(self):
        return {
            **{f"left_{key}": value for key, value in self.left_arm.action_features.items()},
            **{f"right_{key}": value for key, value in self.right_arm.action_features.items()},
        }

    @property
    def feedback_features(self):
        return {}

    def connect(self, calibrate=True):
        if self.left_arm.is_connected or self.right_arm.is_connected:
            raise RuntimeError("Disconnect both leaders before connecting again")
        with ExitStack() as cleanup:
            cleanup.callback(self.disconnect)
            super().connect(calibrate)
            cleanup.pop_all()

    def disconnect(self):
        with ExitStack() as cleanup:
            for arm in (self.right_arm, self.left_arm):
                if arm.is_connected:
                    cleanup.callback(arm.disconnect)

    @check_if_not_connected
    def get_action(self):
        action = {}
        for side, arm, mapping in (
            ("left", self.left_arm, self.config.left_arm_config),
            ("right", self.right_arm, self.config.right_arm_config),
        ):
            # Read before the single-arm driver's raw-angle clipping. A failed
            # read propagates to the teleop loop instead of replaying cached data.
            raw = arm._read_raw_positions()
            for joint in arm.motor_names:
                angle = raw[joint]
                if not math.isfinite(angle):
                    raise ValueError(f"{side} leader returned an invalid angle for {joint}")
                low, high = mapping.joint_ranges[joint]
                direction = mapping.joint_directions[joint]
                center = (low + high) / 2 * (1 if direction >= 0 else -1)
                angle -= 360 * round((angle - center) / 360)
                action[f"{side}_{joint}.pos"] = max(low, min(high, angle * direction))
        return action

    def send_feedback(self, feedback):
        raise NotImplementedError("The reBot Arm 102 leader does not accept feedback.")
